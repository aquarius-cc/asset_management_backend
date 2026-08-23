FROM postgres:16-alpine

RUN apk add --no-cache dcron bash

COPY asset_management_backend/scripts/backup.sh /backup.sh
COPY asset_management_backend/scripts/backup_verify.sh /verify.sh
COPY asset_management_backend/docker/backup/crontab /etc/crontabs/root
RUN chmod +x /backup.sh /verify.sh && chmod 600 /etc/crontabs/root

ENTRYPOINT ["crond", "-f", "-l", "2"]
