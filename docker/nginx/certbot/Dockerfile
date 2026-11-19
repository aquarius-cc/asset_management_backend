# =============================================================================
# Certbot 证书签发/续期 Sidecar
# =============================================================================
FROM certbot/certbot:latest

# 【BF-166】compose context 指向仓根, COPY 源须以子仓路径为前缀
COPY asset_management_backend/docker/nginx/scripts/renew.sh /renew.sh
RUN chmod +x /renew.sh

VOLUME ["/etc/letsencrypt", "/var/www/certbot"]

ENTRYPOINT ["/renew.sh"]
