#!/bin/sh
# =============================================================================
# Nginx 证书监视者 (M-37 三态状态机的态2/态3)
# =============================================================================
# 由 entrypoint.sh 作为后台子进程启动, 随容器生命周期同生共死。
#
# 职责:
#   态2 首现切换: 证书从无到有 → 重渲染完整 TLS 模板(default.conf.tpl) +
#                nginx -t + reload。仅 reload 不换已渲染的 HTTP-only 配置,
#                HTTPS 永远不会生效——重渲染是首现态的必经步骤。
#   态3 轮换续期: 证书指纹变化(certbot 续期写新文件) → nginx -t + reload。
#                nginx 将证书缓存在内存, 不 reload 会持续提供旧证书
#                (renew.sh 头注释的「自动读取新证书无需重启」为错误结论,
#                本脚本即 reload 责任方)。
#
# 约束:
#   - 指纹比对用 busybox sha256sum, 不引入 openssl 依赖
#   - 固定 30s 轮询间隔, 无失败立即重试(防 reload 风暴)
#   - nginx -t 失败不 reload, 留日志等下轮(坏配置不顶掉在跑服务)
# =============================================================================

set -u

CERT_PATH="${CERT_PATH:-/etc/nginx/letsencrypt}"
FULLCHAIN="${CERT_PATH}/fullchain.pem"
PRIVKEY="${CERT_PATH}/privkey.pem"
TPL_DIR=/etc/nginx/conf.d
RENDER_OUT="$TPL_DIR/default.conf"
INTERVAL=30

log() { echo "[cert-watch] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# 模板选择判定式与 entrypoint.sh 保持同一行逻辑(两处实现, 注释互指防分叉)
current_fingerprint() {
    if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ]; then
        # certbot live 目录下 fullchain/privkey 同批写入; 拼接哈希防止单文件回滚漏检
        (sha256sum "$FULLCHAIN" "$PRIVKEY" 2>/dev/null | sha256sum | cut -d' ' -f1)
    else
        echo "none"
    fi
}

# 渲染: 证书存在→TLS 模板, 不存在→HTTP-only 模板 (与 entrypoint.sh 同一判定)
render() {
    if [ -f "$FULLCHAIN" ]; then
        envsubst '${DOMAIN} ${CERT_PATH}' < "$TPL_DIR/default.conf.tpl" > "$RENDER_OUT"
    else
        envsubst '${DOMAIN} ${CERT_PATH}' < "$TPL_DIR/default-http.conf.tpl" > "$RENDER_OUT"
    fi
}

prev_fp="$(current_fingerprint)"
log "watcher started: cert_path=${CERT_PATH} initial_state=${prev_fp}"

while true; do
    sleep "$INTERVAL"

    fp="$(current_fingerprint)"

    if [ "$fp" = "$prev_fp" ]; then
        continue
    fi

    if [ "$fp" = "none" ]; then
        # 证书消失(卷被清/误删): 回落引导态, 保住 80 端口业务不断
        log "certificate disappeared: falling back to http-bootstrap template"
        if render && nginx -t 2>/dev/null; then
            nginx -s reload && log "reloaded with http-bootstrap config"
            prev_fp="$fp"
        else
            log "ERROR: render/nginx -t failed, keep running config until next cycle"
        fi
        continue
    fi

    if [ "$prev_fp" = "none" ]; then
        # 态2 首现: 必须重渲染切换到 TLS 模板(仅 reload 不换配置)
        log "certificate first seen: re-rendering TLS template"
        if render && nginx -t 2>/dev/null; then
            nginx -s reload && log "TLS enabled: reloaded with full TLS config"
            prev_fp="$fp"
        else
            log "ERROR: render/nginx -t failed, retry next cycle"
        fi
    else
        # 态3 轮换: 配置未变, 仅重载证书
        if nginx -t 2>/dev/null; then
            nginx -s reload && log "certificate rotated: reloaded (fp=${fp})"
            prev_fp="$fp"
        else
            log "ERROR: nginx -t failed on rotation, keep old cert until next cycle"
        fi
    fi
done
