#!/bin/bash
# redis_backup.sh - 每日 RDB 快照归档(错峰 2:30, 与 pg 全量备份 2:00 错开)
# 依据: 08-数据备份恢复方案.md; BF-003 终审 Step 2
#
# 范围声明(决策边界): 当前 Redis 仅作 WebSocket channel layer 与缓存,
# 持久化策略为默认 RDB(未启用 AOF), 业务口径 RPO=24h 且数据可重建。
# 秒级 RPO(AOF 流水归档)不在本期范围, 若业务要求另行立项。
set -euo pipefail

# N-2 备份可观测：source 备份状态管道（EXIT trap 中调用）
[ -f /backup_status.sh ] && . /backup_status.sh || true

# 退出处理：无论成功/失败/跳过，写入状态（跳过由 _BACKUP_SKIP 标记）
_backup_exit_handler () {
  local _rc=$?
  if [ -n "${_BACKUP_SKIP:-}" ]; then return 0; fi
  backup_status_write "$_rc"
}
trap _backup_exit_handler EXIT

BACKUP_DIR="${BACKUP_DIR_REDIS:-/data/backups/redis}"
DATE=$(date +%Y%m%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="redis/${DATE}"

mkdir -p "$BACKUP_DIR"

# --- 并发锁 ---
if command -v flock >/dev/null 2>&1; then
  exec 9>/tmp/redis_backup.lock
  if ! flock -n 9; then
    echo "[$(date)] ⚠️ 上一次 Redis 备份仍在执行, 本次跳过"
    _BACKUP_SKIP=1   # N-2: 跳过分支不计入成功/失败指标
    exit 0
  fi
fi

AUTH_ARGS=()
[ -n "$REDIS_PASSWORD" ] && AUTH_ARGS=(-a "$REDIS_PASSWORD" --no-auth-warning)

RDB_FILE="$BACKUP_DIR/redis_$DATE.rdb"

# 远程拉取快照: redis-cli --rdb 触发安全快照传输, 不进容器、不阻塞写
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "${AUTH_ARGS[@]}" --rdb "$RDB_FILE" >/dev/null
[ -s "$RDB_FILE" ] || { echo "❌ RDB 文件为空: $RDB_FILE"; exit 1; }

# --- 可读性验证: postgres 镜像无 redis-check-rdb, 改用魔数+尺寸双重校验 ---
# RDB v10+ 文件头固定为 "REDIS"
head -c 5 "$RDB_FILE" | grep -q "^REDIS" || { echo "❌ RDB 魔数校验失败(非合法 RDB 文件)"; exit 1; }

find "$BACKUP_DIR" -name "redis_*.rdb" -mtime +"$RETENTION_DAYS" -delete

# --- S3 异地上传(同一失败语义) ---
if [ -n "$S3_BUCKET" ]; then
  command -v aws >/dev/null || { echo "❌ S3 已配置但 aws CLI 缺失"; exit 1; }
  LOCAL_SIZE=$(stat -c %s "$RDB_FILE")
  S3_URI="s3://$S3_BUCKET/$S3_PREFIX/redis_$DATE.rdb"
  UPLOAD_OK=false
  for i in 1 2 3; do
    if aws s3 cp "$RDB_FILE" "$S3_URI" --storage-class STANDARD_IA; then
      UPLOAD_OK=true
      break
    fi
    sleep $((i * 10))
  done
  $UPLOAD_OK || { echo "❌ S3 上传失败(重试3次): $S3_URI"; exit 1; }
  REMOTE_SIZE=$(aws s3api head-object --bucket "$S3_BUCKET" --key "$S3_PREFIX/redis_$DATE.rdb" \
    --query 'ContentLength' --output text)
  [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] || { echo "❌ S3 完整性校验失败: $LOCAL_SIZE vs $REMOTE_SIZE"; exit 1; }
  echo "[$(date)] ✅ Redis RDB 已上传: $S3_URI ($LOCAL_SIZE bytes)"
fi

echo "[$(date)] ✅ Redis 备份完成: $RDB_FILE ($(du -h "$RDB_FILE" | cut -f1))"
