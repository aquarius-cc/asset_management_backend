#!/bin/bash
# backup.sh - 每日凌晨 cron 执行
# 依据: Project_Requirements/03-安全与运维/08-数据备份恢复方案.md §2
# BF-003 改造: flock 防并发 / S3 三分支失败语义 / 上传完整性校验 / 日期分片
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
DATE=$(date +%Y%m%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-asset_management}"
DB_USER="${DB_USER:-backup_user}"
DB_PASSWORD="${DB_PASSWORD:-}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="postgres/${DATE}"

mkdir -p "$BACKUP_DIR"

# --- 并发锁: 上一次备份未完成(大文件/网络慢)时本次直接退出, 防重叠 ---
# 防御性降级: 环境缺失 flock 时照常执行(宁重复勿漏备)
if command -v flock >/dev/null 2>&1; then
  exec 9>/tmp/backup.lock
  if ! flock -n 9; then
    echo "[$(date)] ⚠️ 上一次备份仍在执行, 本次跳过"
    exit 0
  fi
fi

DUMP_FILE="$BACKUP_DIR/full_$DATE.dump"

# 全量备份
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
  --format=custom \
  "$DB_NAME" > "$DUMP_FILE"

# 清理过期备份
find "$BACKUP_DIR" -name "full_*.dump" -mtime +"$RETENTION_DAYS" -delete

# --- S3 异地上传(三分支失败语义): 配置了 S3 就必须成功, 未配置则跳过 ---
if [ -n "$S3_BUCKET" ]; then
  command -v aws >/dev/null || { echo "❌ S3 已配置(S3_BUCKET=$S3_BUCKET)但 aws CLI 缺失"; exit 1; }
  LOCAL_SIZE=$(stat -c %s "$DUMP_FILE")
  S3_URI="s3://$S3_BUCKET/$S3_PREFIX/full_$DATE.dump"
  UPLOAD_OK=false
  for i in 1 2 3; do
    if aws s3 cp "$DUMP_FILE" "$S3_URI" --storage-class STANDARD_IA; then
      UPLOAD_OK=true
      break
    fi
    echo "[$(date)] S3 上传失败(第 $i/3 次), ${i}0 秒后重试..."
    sleep $((i * 10))
  done
  # AR-3 重试策略: 3 次指数退避后仍失败则报错退出(cron 日志可见, 可接告警)
  $UPLOAD_OK || { echo "❌ S3 上传失败(重试3次): $S3_URI"; exit 1; }
  # 完整性校验: 对比远端 ContentLength 与本地字节数
  # 注: 分片上传的 ETag 非 MD5, 故用尺寸比对而非哈希
  REMOTE_SIZE=$(aws s3api head-object --bucket "$S3_BUCKET" --key "$S3_PREFIX/full_$DATE.dump" \
    --query 'ContentLength' --output text)
  [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] || { echo "❌ S3 完整性校验失败: 本地 $LOCAL_SIZE vs 远端 $REMOTE_SIZE"; exit 1; }
  echo "[$(date)] ✅ S3 上传成功且完整性校验通过: $S3_URI ($LOCAL_SIZE bytes)"
else
  echo "[$(date)] S3_BUCKET 未配置, 跳过异地上传(仅本地保留)"
fi

# 日志输出(容器内由 cron 重定向到 /proc/1/fd/1,进入 docker logs)
echo "[$(date)] 备份完成: full_$DATE.dump"
echo "[$(date)] 备份文件大小: $(ls -lh "$BACKUP_DIR/full_$DATE.dump" 2>/dev/null | awk '{print $5}' || echo 'N/A')"
echo "[$(date)] 当前备份数: $(ls -1 "$BACKUP_DIR"/full_*.dump 2>/dev/null | wc -l)"
