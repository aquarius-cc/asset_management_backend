#!/bin/bash
# backup.sh - 每日凌晨 cron 执行
# 依据: Project_Requirements/03-安全与运维/08-数据备份恢复方案.md §2
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
DATE=$(date +%Y%m%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_NAME="${DB_NAME:-asset_management}"
DB_USER="${DB_USER:-backup_user}"

mkdir -p "$BACKUP_DIR"

# 全量备份
PGPASSWORD="$DB_PASSWORD" pg_dump -U "$DB_USER" \
  --format=custom \
  "$DB_NAME" > "$BACKUP_DIR/full_$DATE.dump"

# 清理过期备份
find "$BACKUP_DIR" -name "full_*.dump" -mtime +$RETENTION_DAYS -delete

# 上传到异地存储(S3,可选)
if command -v aws &> /dev/null; then
  aws s3 cp "$BACKUP_DIR/full_$DATE.dump" \
    s3://backup-bucket/postgres/ --storage-class STANDARD_IA
fi

echo "[$(date)] 备份完成: full_$DATE.dump"
