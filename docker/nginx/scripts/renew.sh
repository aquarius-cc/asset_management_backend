#!/bin/sh
# =============================================================================
# Certbot 自动续期守护进程
# =============================================================================
# 每12小时检查一次, 仅在证书到期前30天内续期
# 续期后 Nginx 通过共享卷自动读取新证书 (无需重启)
set -e

DOMAIN="${DOMAIN:-localhost}"

echo "Certbot renewal daemon started: domain=${DOMAIN}"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Checking certificate renewal..."

    # 仅在证书存在时尝试续期
    if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
        certbot renew \
            --webroot \
            --webroot-path=/var/www/certbot \
            --quiet \
            2>&1 || echo "[$(date '+%Y-%m-%d %H:%M:%S')] Renewal check failed (non-fatal)"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] No certificate found for ${DOMAIN}, skipping"
    fi

    # 每12小时检查一次 (43200秒)
    sleep 43200
done
