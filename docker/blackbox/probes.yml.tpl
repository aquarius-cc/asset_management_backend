- targets: ["https://${DOMAIN}/health/"]
  labels:
    instance: "${DOMAIN}"
    probe: "https_health_2xx"
