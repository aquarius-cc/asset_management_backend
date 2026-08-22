# =============================================================================
# Certbot 证书签发/续期 Sidecar
# =============================================================================
FROM certbot/certbot:latest

COPY docker/nginx/scripts/renew.sh /renew.sh
RUN chmod +x /renew.sh

VOLUME ["/etc/letsencrypt", "/var/www/certbot"]

ENTRYPOINT ["/renew.sh"]
