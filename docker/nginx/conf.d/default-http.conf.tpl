# =============================================================================
# Nginx 虚拟主机配置模板 —— HTTP-only 引导态（M-37 三态状态机·态1）
# =============================================================================
# 使用场景: ${CERT_PATH}/fullchain.pem 不存在时（全新首装 / 证书卷丢失）由
# entrypoint.sh 选择本模板渲染, 打破「nginx 依赖证书、certbot 依赖 nginx」死锁。
# 与完整 TLS 模板(default.conf.tpl)的差异:
#   - 无 443 server 块(证书不存在, 引用即启动失败)
#   - 80 端口直接承载全部业务路由(API/health/ws/静态/SPA), 签发窗口业务不断
#   - 无 HSTS 头(避免 TLS 前污染浏览器缓存; 其余安全头保留)
#   - 保留 acme-challenge 路由供 certbot webroot HTTP-01 验证
# 证书首现后由 cert-watch.sh 重渲染 default.conf.tpl 并 reload 切入 TLS 态。
#
# 变量由 entrypoint.sh 通过 envsubst 渲染: ${DOMAIN} ${CERT_PATH}

server {
    listen 80;
    server_name ${DOMAIN};

    # Let's Encrypt ACME HTTP-01 验证 (webroot 卷与 certbot sidecar 共享)
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        allow all;
    }

    # --- API 代理 (30 req/s + burst 50) ---
    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;

        proxy_pass http://asset_backend;
        # 安全头防御护栏: 剥离 Django 可能返回的安全头, 由 server 级 add_header 唯一下发
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
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
    location /api/v1/auth/login/ {
        limit_req zone=login_brute burst=3 nodelay;

        proxy_pass http://asset_backend;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    location /api/v1/auth/token/ {
        limit_req zone=login_limit burst=3 nodelay;

        proxy_pass http://asset_backend;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
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
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # --- 健康检查 (无限流, 无日志) ---
    location /health/ {
        proxy_pass http://asset_backend;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_set_header Host $host;
        access_log off;
    }

    location /ready/ {
        proxy_pass http://asset_backend;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_set_header Host $host;
        access_log off;
    }

    # --- Prometheus 指标 (OC-4): 仅内网可抓取 ---
    location = /metrics/ {
        allow 10.0.0.0/8;
        deny all;

        proxy_pass http://asset_backend;
        proxy_hide_header Strict-Transport-Security;
        proxy_hide_header X-Content-Type-Options;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Referrer-Policy;
        proxy_hide_header Permissions-Policy;
        proxy_set_header Host $host;
        access_log off;
    }

    # --- 静态文件 (30天缓存 + immutable 指纹) ---
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        # 安全头必须显式重复 (nginx add_header 在 location 块中覆盖 server 级定义)
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        access_log off;
    }

    # --- 媒体文件 (30天缓存) ---
    location /media/ {
        alias /app/media/;
        expires 30d;
        add_header Cache-Control "public";
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
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
