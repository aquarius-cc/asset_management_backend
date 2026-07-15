import os

from django.core.exceptions import ImproperlyConfigured

from .base import *


# 生产环境关闭调试
DEBUG = False

# 【修复】从环境变量强制读取密钥，缺失时抛出异常
# 统一使用 SECRET_KEY 变量名，与 base.py 保持一致
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY environment variable is required in production')

# 【修复】ALLOWED_HOSTS 缺失时抛出异常
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '')
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS environment variable is required in production')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS.split(',') if host.strip()]

# 生产数据库（通过环境变量配置）
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'asset_management'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        # 【修复】补充连接池配置
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }
}

# 安全设置
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
# 【新增】HTTPS 安全头
SECURE_HSTS_SECONDS = 31536000  # 1年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True

# 静态文件收集（由 Nginx 代管）
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'

# 限制 CORS（从环境变量读取）
CORS_ALLOW_ALL_ORIGINS = False
cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]

# 日志级别提升
LOGGING['handlers']['console']['level'] = 'WARNING'
LOGGING['loggers']['django']['level'] = 'WARNING'
LOGGING['loggers']['rest_framework']['level'] = 'WARNING'
