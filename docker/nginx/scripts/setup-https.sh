#!/bin/bash
# =============================================================================
# HTTPS 初始化脚本 (一次性执行)
# =============================================================================
# 用法: ./setup-https.sh <domain> <email>
# 示例: ./setup-https.sh example.com admin@example.com
#
# 执行流程:
#   1. 生成自签名证书 (临时占位, 让 Nginx 启动 HTTPS server 块)
#   2. 请求 Let's Encrypt 正式证书
#   3. Nginx 通过共享卷自动加载新证书
set -euo pipefail

DOMAIN="${1:?用法: $0 <domain> <email>}"
EMAIL="${2:?用法: $0 <domain> <email>}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

echo "============================================"
echo " HTTPS 初始化: ${DOMAIN}"
echo "============================================"

echo ""
echo "=== [1/4] 生成自签名证书 (临时占位) ==="
docker compose exec nginx sh -c "
    mkdir -p ${CERT_DIR} && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ${CERT_DIR}/privkey.pem \
        -out ${CERT_DIR}/fullchain.pem \
        -subj '/CN=${DOMAIN}' && \
    cp ${CERT_DIR}/fullchain.pem ${CERT_DIR}/chain.pem
"
echo "自签名证书已生成, 重启 Nginx 加载..."
docker compose restart nginx
echo "等待 Nginx 就绪..."
sleep 5

echo ""
echo "=== [2/4] 请求 Let's Encrypt 正式证书 ==="
docker compose run --rm certbot certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --force-renewal \
    -d "${DOMAIN}"

echo ""
echo "=== [3/4] 验证证书已签发 ==="
docker compose exec nginx ls -la "${CERT_DIR}/"

echo ""
echo "=== [4/4] 验证 HTTPS 访问 ==="
echo "测试命令: curl -kI https://${DOMAIN}/health/"
echo "期望结果: HTTP/2 200 (而非 301 重定向循环)"

echo ""
echo "============================================"
echo " HTTPS 初始化完成"
echo "============================================"
echo ""
echo "验证清单:"
echo "  1. curl -I http://${DOMAIN}/.well-known/acme-challenge/test → 404 (非 index.html)"
echo "  2. curl -I https://${DOMAIN}/health/ → 200"
echo "  3. curl -I https://${DOMAIN}/ | grep strict-transport-security"
echo ""
echo "后续: Certbot sidecar 每12小时自动检查续期"
