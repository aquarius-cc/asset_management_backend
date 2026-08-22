# =============================================================================
# Nginx 虚拟主机配置模板
# =============================================================================
# 变量由 entrypoint.sh 通过 envsubst 渲染:
#   ${DOMAIN}    - 域名 (如 example.com)
#   ${CERT_PATH} - TLS 证书路径 (如 /etc/nginx/letsencrypt)

# --- HTTP: ACME Challenge + HTTPS 重定向 ---
server {
    listen 80;
    server_name ${DOMAIN};

    # Let's Encrypt ACME HTTP-01 验证
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        allow all;
    }

    # HTTPS 启用后: 所有非 ACME 请求 301 到 HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# --- HTTPS: 主服务 ---
server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    # TLS 证书
    ssl_certificate     ${CERT_PATH}/fullchain.pem;
    ssl_certificate_key ${CERT_PATH}/privkey.pem;
    ssl_trusted_certificate ${CERT_PATH}/chain.pem;

    # TLS 协议与加密套件
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 1.1.1.1 valid=300s;
    resolver_timeout 5s;

    # --- 安全响应头 ---
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    # CSP 由 Django 中间件 core.csp_middleware 统一设置(支持按路径差异化, 如排除 /admin/)
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    # --- API 代理 (30 req/s + burst 50) ---
    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;

        proxy_pass http://asset_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        proxy_buffering on;
        proxy_buffer_size 8k;
        proxy_buffers 8 8k;
    }

    # --- 登录接口加强限流 (5 req/min + burst 3) ---
    location /api/v1/auth/token/ {
        limit_req zone=login_limit burst=3 nodelay;

        proxy_pass http://asset_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # --- WebSocket 代理 (通知系统) ---
    location /ws/ {
        proxy_pass http://asset_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # --- 健康检查 (无限流, 无日志) ---
    location /health/ {
        proxy_pass http://asset_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        access_log off;
    }

    location /ready/ {
        proxy_pass http://asset_backend;
        proxy_set_header Host $host;
        access_log off;
    }

    # --- 静态文件 (30天缓存 + immutable 指纹) ---
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        # 安全头必须显式重复 (nginx add_header 在 location 块中覆盖 server 级定义)
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        access_log off;
    }

    # --- 媒体文件 (30天缓存) ---
    location /media/ {
        alias /app/media/;
        expires 30d;
        add_header Cache-Control "public";
        # 安全头必须显式重复 (nginx add_header 在 location 块中覆盖 server 级定义)
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        access_log off;
    }

    # --- 前端 SPA (Vue Router History 模式 fallback) ---
    location / {
        root /app/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
