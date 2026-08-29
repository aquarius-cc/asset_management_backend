#!/bin/bash
# media_backup.sh - 每日归档用户上传文件(media_volume)
# 依据: 08-数据备份恢复方案.md; 补齐"数据库之外媒体文件无备份"缺口(BF-003 终审新增)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR_MEDIA:-/data/backups/media}"
DATE=$(date +%Y%m%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
MEDIA_SRC="${MEDIA_SRC:-/data/media}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="media/${DATE}"

[ -d "$MEDIA_SRC" ] || { echo "❌ 媒体目录不存在: $MEDIA_SRC (请确认 compose 已挂载 media_volume)"; exit 1; }
mkdir -p "$BACKUP_DIR"

# --- 并发锁(与 backup.sh 独立锁文件) ---
if command -v flock >/dev/null 2>&1; then
  exec 9>/tmp/media_backup.lock
  if ! flock -n 9; then
    echo "[$(date)] ⚠️ 上一次媒体备份仍在执行, 本次跳过"
    exit 0
  fi
fi

ARCHIVE="$BACKUP_DIR/media_$DATE.tar.gz"

# 打包媒体文件(增量优化空间有限, 文件量级下全量 tar 足够)
tar -czf "$ARCHIVE" -C "$MEDIA_SRC" .

# 清理过期归档
find "$BACKUP_DIR" -name "media_*.tar.gz" -mtime +"$RETENTION_DAYS" -delete

# --- S3 异地上传(与 backup.sh 同一失败语义) ---
if [ -n "$S3_BUCKET" ]; then
  command -v aws >/dev/null || { echo "❌ S3 已配置但 aws CLI 缺失"; exit 1; }
  LOCAL_SIZE=$(stat -c %s "$ARCHIVE")
  S3_URI="s3://$S3_BUCKET/$S3_PREFIX/media_$DATE.tar.gz"
  UPLOAD_OK=false
  for i in 1 2 3; do
    if aws s3 cp "$ARCHIVE" "$S3_URI" --storage-class STANDARD_IA; then
      UPLOAD_OK=true
      break
    fi
    sleep $((i * 10))
  done
  $UPLOAD_OK || { echo "❌ S3 上传失败(重试3次): $S3_URI"; exit 1; }
  REMOTE_SIZE=$(aws s3api head-object --bucket "$S3_BUCKET" --key "$S3_PREFIX/media_$DATE.tar.gz" \
    --query 'ContentLength' --output text)
  [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ] || { echo "❌ S3 完整性校验失败: $LOCAL_SIZE vs $REMOTE_SIZE"; exit 1; }
  echo "[$(date)] ✅ 媒体备份已上传: $S3_URI ($LOCAL_SIZE bytes)"
fi

echo "[$(date)] ✅ 媒体备份完成: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
