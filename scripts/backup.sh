#!/bin/bash
# backup.sh - 每日凌晨 cron 执行
# 依据: Project_Requirements/03-安全与运维/08-数据备份恢复方案.md §2
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
DATE=$(date +%Y%m%d)
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-asset_management}"
DB_USER="${DB_USER:-backup_user}"

mkdir -p "$BACKUP_DIR"

# 全量备份
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
  --format=custom \
  "$DB_NAME" > "$BACKUP_DIR/full_$DATE.dump"

# 清理过期备份
find "$BACKUP_DIR" -name "full_*.dump" -mtime +$RETENTION_DAYS -delete

# S3 异地上传(需容器内安装 aws CLI 并配置凭证,当前环境未满足,静默跳过)
if command -v aws &> /dev/null; then
  aws s3 cp "$BACKUP_DIR/full_$DATE.dump" \
    s3://backup-bucket/postgres/ --storage-class STANDARD_IA
fi

# 日志输出(容器内由 cron 重定向到 /proc/1/fd/1,进入 docker logs)
echo "[$(date)] 备份完成: full_$DATE.dump"
echo "[$(date)] 备份文件大小: $(ls -lh "$BACKUP_DIR/full_$DATE.dump" 2>/dev/null | awk '{print $5}' || echo 'N/A')"
echo "[$(date)] 当前备份数: $(ls -1 "$BACKUP_DIR"/full_*.dump 2>/dev/null | wc -l)"
