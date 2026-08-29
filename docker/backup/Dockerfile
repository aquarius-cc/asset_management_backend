# =============================================================================
# 备份容器: PostgreSQL 全量 + Redis RDB + 媒体文件 归档 + 恢复演练
# =============================================================================
FROM postgres:16-alpine

RUN apk add --no-cache dcron bash aws-cli

COPY asset_management_backend/scripts/backup.sh /backup.sh
COPY asset_management_backend/scripts/backup_verify.sh /verify.sh
COPY asset_management_backend/scripts/redis_backup.sh /redis_backup.sh
COPY asset_management_backend/scripts/media_backup.sh /media_backup.sh
COPY asset_management_backend/scripts/restore_test.sh /restore_test.sh
COPY asset_management_backend/docker/backup/crontab /etc/crontabs/root
RUN chmod +x /backup.sh /verify.sh /redis_backup.sh /media_backup.sh /restore_test.sh \
    && chmod 600 /etc/crontabs/root

ENTRYPOINT ["crond", "-f", "-l", "2"]
