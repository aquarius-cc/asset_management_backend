#!/bin/sh
# =============================================================================
# Certbot 证书签发/续期守护进程 (M-37)
# =============================================================================
# 每12小时一轮; 双路径:
#   有证书 → certbot renew --webroot 续期(到期前30天内实际执行)
#   无证书 → certbot certonly --webroot 首签(打破无证死锁的签发主体)
# reload 责任方: nginx 容器内 cert-watch.sh(nginx 缓存证书于内存, 本容器
# 写入新证书后不会自动生效——旧注释「Nginx 自动读取新证书无需重启」为错误
# 结论, 已随 M-37 订正)。
#
# 退避约束(Let's Encrypt 速率限制): 首签失败按 1h→2h→4h…翻倍退避, 上限 24h;
# 续期检查失败不翻倍(本身即 12h 低频)。禁止「失败即立刻重试」——会撞 429。
set -u

DOMAIN="${DOMAIN:-localhost}"
EMAIL="${EMAIL:-}"
LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"
FULLCHAIN="${LIVE_DIR}/fullchain.pem"
INTERVAL=43200   # 12h
BACKOFF_MAX=86400  # 24h
backoff=3600       # 首签失败退避起点 1h

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

issue_if_missing() {
    log "No certificate found for ${DOMAIN}, requesting first issuance (webroot HTTP-01)..."
    # 邮箱注册优先(compose 可注入 EMAIL); 未提供则无邮箱注册(仅收不到 LE 到期提醒)
    if [ -n "$EMAIL" ]; then
        EMAIL_ARGS="--email=${EMAIL}"
    else
        EMAIL_ARGS="--register-unsafely-without-email"
    fi
    if certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --non-interactive \
        --agree-tos \
        ${EMAIL_ARGS} \
        -d "${DOMAIN}" \
        2>&1; then
        log "First issuance OK for ${DOMAIN}; nginx cert-watch will reload shortly"
        backoff=3600
    else
        log "First issuance FAILED for ${DOMAIN}, backing off ${backoff}s (next attempt delayed; prevents LE 429 rate-limit)"
        sleep "$backoff"
        backoff=$((backoff * 2))
        [ "$backoff" -gt "$BACKOFF_MAX" ] && backoff=$BACKOFF_MAX
    fi
}

renew_if_present() {
    if certbot renew \
        --webroot \
        --webroot-path=/var/www/certbot \
        --quiet \
        2>&1; then
        log "Renewal check finished for ${DOMAIN}"
    else
        # 续期失败仅记录: 证书仍在有效期内, 12h 后自然重查, 不进入退避
        log "Renewal check failed for ${DOMAIN} (non-fatal, retry next cycle)"
    fi
}

log "Certbot daemon started: domain=${DOMAIN}"

while true; do
    if [ -f "$FULLCHAIN" ]; then
        renew_if_present
    else
        issue_if_missing
    fi
    sleep "$INTERVAL"
done
