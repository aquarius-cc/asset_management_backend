# blackbox 配置渲染边车: 从 DOMAIN 环境变量渲染 blackbox/probes 配置
# 与 nginx entrypoint 的 envsubst 惯例同构（N-3）
FROM busybox:1.36
# 【BF-166】compose context 指向仓根, COPY 源须以子仓路径为前缀
COPY asset_management_backend/docker/blackbox/entrypoint.sh /entrypoint.sh
COPY asset_management_backend/docker/blackbox/blackbox.yml.tpl /templates/blackbox.yml.tpl
COPY asset_management_backend/docker/blackbox/probes.yml.tpl /templates/probes.yml.tpl
ENTRYPOINT ["/entrypoint.sh"]
