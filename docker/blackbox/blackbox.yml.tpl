modules:
  https_health_2xx:
    prober: http
    timeout: 10s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      valid_status_codes: [200]
      method: GET
      no_follow_redirects: true
      fail_if_ssl: true
      fail_if_not_ssl: true
      tls_config:
        server_name: "${DOMAIN}"
        insecure: false
      headers:
        Host: ["${DOMAIN}"]
