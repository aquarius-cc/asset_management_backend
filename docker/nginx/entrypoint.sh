#!/bin/sh
# =============================================================================
# Nginx 入口脚本 - 环境变量渲染 + 启动
# =============================================================================
set -e

# 渲染配置模板: 仅替换 ${DOMAIN} 和 ${CERT_PATH}, 不触碰 nginx 的 $变量
export DOMAIN="${DOMAIN:-localhost}"
export CERT_PATH="${CERT_PATH:-/etc/nginx/letsencrypt}"

envsubst '${DOMAIN} ${CERT_PATH}' \
    < /etc/nginx/conf.d/default.conf.tpl \
    > /etc/nginx/conf.d/default.conf

# 确保 ACME challenge 目录存在
mkdir -p /var/www/certbot

echo "Nginx started: domain=${DOMAIN} cert_path=${CERT_PATH}"
exec nginx -g "daemon off;"
