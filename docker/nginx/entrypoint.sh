#!/bin/sh
# =============================================================================
# Nginx 入口脚本 - 三态渲染 + 启动 (M-37)
# =============================================================================
# 三态状态机(与 cert-watch.sh 协作):
#   态1 引导态   : 证书不存在 → 渲染 default-http.conf.tpl (80 端口承载全部业务,
#                  仅缺 TLS), certbot sidecar 可经 webroot 完成 HTTP-01 首签
#   态2 首现切换 : 证书出现 → cert-watch 重渲染 default.conf.tpl + nginx -t + reload
#   态3 轮换续期 : 证书指纹变化 → cert-watch nginx -t + reload (修「续期后旧证书」)
#
# set -e: 渲染失败必须阻止启动 (模板/变量缺失属部署错误, 静默起 HTTP 服务更危险)
set -e

# 渲染配置模板: 仅替换 ${DOMAIN} 和 ${CERT_PATH}, 不触碰 nginx 的 $变量
export DOMAIN="${DOMAIN:-localhost}"
export CERT_PATH="${CERT_PATH:-/etc/nginx/letsencrypt}"

TPL_DIR=/etc/nginx/conf.d
RENDER_OUT="$TPL_DIR/default.conf"

# 按证书存在性选模板渲染 (DR-1: 渲染逻辑唯一入口, cert-watch 复用本函数文件不可行——
# sh 无 source 共享常量约束, 故此处与 cert-watch 各自实现同一判定, 判定式一行,
# 以注释互指防分叉)
if [ -f "${CERT_PATH}/fullchain.pem" ]; then
    TPL="$TPL_DIR/default.conf.tpl"
else
    TPL="$TPL_DIR/default-http.conf.tpl"
fi

envsubst '${DOMAIN} ${CERT_PATH}' \
    < "$TPL" \
    > "$RENDER_OUT"

nginx -t || exit 1

# 确保 ACME challenge 目录存在
mkdir -p /var/www/certbot

# 启动证书监视者(后台子进程, exec nginx 后由 init 进程收养; 容器退出即随亡)
# 职责: 态2 首现重渲染切换 TLS / 态3 轮换 reload, 详见 docker/nginx/scripts/cert-watch.sh
sh /etc/nginx/scripts/cert-watch.sh &
CERT_WATCH_PID=$!
trap 'kill "$CERT_WATCH_PID" 2>/dev/null || true' TERM INT

echo "Nginx started: domain=${DOMAIN} cert_path=${CERT_PATH} tpl=$(basename "$TPL") state=$( [ -f "${CERT_PATH}/fullchain.pem" ] && echo tls || echo http-bootstrap )"
exec nginx -g "daemon off;"
