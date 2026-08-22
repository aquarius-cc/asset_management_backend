import os

from django.core.exceptions import ImproperlyConfigured

from .base import *


# 生产环境关闭调试
DEBUG = False

# 安全断言:生产环境 CSRF cookie 必须标记为 Secure
assert CSRF_COOKIE_SECURE is True, "生产环境 CSRF_COOKIE_SECURE 必须为 True"

# 【修复】从环境变量强制读取密钥,缺失时抛出异常
# 统一使用 SECRET_KEY 变量名,与 base.py 保持一致
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY environment variable is required in production")

# C-2: 额外验证 — 拒绝已知弱密钥（belt-and-suspenders）
_INSECURE_KEYS = frozenset({
    "django-insecure-placeholder-see-env-settings",
    "django-insecure-dev-only-key-change-in-production-1234567890",
    "change-me-in-production",
    "your-secret-key-here-change-in-production",
    "change-this-to-a-real-secret-key-before-running",
    "changeme",
})
if SECRET_KEY in _INSECURE_KEYS or len(SECRET_KEY) < 20:
    raise ImproperlyConfigured(
        "SECRET_KEY is too weak for production. Must be ≥20 characters.\n"
        "Generate: python -c \"from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())\""
    )

# 【修复】ALLOWED_HOSTS 缺失时抛出异常
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS environment variable is required in production")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS.split(",") if host.strip()]

# 生产数据库(通过环境变量配置)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "asset_management"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        # 【修复】补充连接池配置
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
    }
}

# 安全设置
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
# JWT 认证 Cookie (access/refresh/csrftoken) 仅通过 HTTPS 传输
JWT_AUTH_COOKIE_SECURE = True
# 以下3个安全头由 Nginx add_header 统一设置,避免重复头
# SECURE_BROWSER_XSS_FILTER / SECURE_CONTENT_TYPE_NOSNIFF / X_FRAME_OPTIONS
# 【新增】HTTPS 安全头
SECURE_HSTS_SECONDS = 31536000  # 1年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
# 【修复】Nginx 反向代理：Django 通过此头识别原始 HTTPS 协议
# 缺失会导致 SECURE_SSL_REDIRECT=True 引发无限重定向循环
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 静态文件收集(由 Nginx 代管)
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

# 限制 CORS(从环境变量读取)
CORS_ALLOW_ALL_ORIGINS = False
cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

# 日志级别提升
LOGGING["handlers"]["console"]["level"] = "WARNING"
LOGGING["loggers"]["django"]["level"] = "WARNING"
LOGGING["loggers"]["rest_framework"]["level"] = "WARNING"

# WebSocket 通道层:生产环境必须使用 Redis
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")]},
    },
}
assert CHANNEL_LAYERS["default"]["BACKEND"] != "channels.layers.InMemoryChannelLayer", \
    "生产环境禁止使用 InMemoryChannelLayer"
