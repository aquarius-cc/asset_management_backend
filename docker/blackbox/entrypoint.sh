#!/bin/sh
# N-3 blackbox 配置渲染边车（fail-fast: DOMAIN 空则退出）
set -eu
[ -n "${DOMAIN:-}" ] || { echo "❌ DOMAIN 未设置，blackbox 配置无法渲染"; exit 1; }
umask 022
mkdir -p /rendered
esc=$(printf '%s' "$DOMAIN" | sed "s/'/'\\''/g")
sed "s|\${DOMAIN}|$esc|g" /templates/blackbox.yml.tpl > /rendered/blackbox.yml.tmp
sed "s|\${DOMAIN}|$esc|g" /templates/probes.yml.tpl    > /rendered/probes.yml.tmp
mv /rendered/blackbox.yml.tmp /rendered/blackbox.yml
mv /rendered/probes.yml.tmp    /rendered/probes.yml
chmod 644 /rendered/*.yml
echo "blackbox config rendered for DOMAIN=$DOMAIN"
