"""
Django base settings for asset_management project.
"""
from datetime import timedelta
from pathlib import Path

from decouple import config


# 项目根目录（asset_management_backend/）
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
# 【修复 S1】生产环境必须从环境变量读取
# 开发环境会使用下面的默认值，但生产部署时必须通过环境变量设置
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-dev-only-key-change-in-production-1234567890'
)

# 【修复 S3】DEBUG 默认值为 False，生产环境更安全
DEBUG = config('DEBUG', default=False, cast=bool)

# 【修复 S2】ALLOWED_HOSTS 默认空列表，仅允许配置的域名
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='')
if ALLOWED_HOSTS:
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS.split(',') if host.strip()]
else:
    ALLOWED_HOSTS = []

# 自定义用户模型
AUTH_USER_MODEL = 'authusermanagement.AuthUser'

INSTALLED_APPS = [
    'daphne',  # 必须在最前面，启用 ASGI 模式支持 WebSocket
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # 【新增】Token 黑名单应用，支持主动作废 Token
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'corsheaders',
    'django_filters',
    # 【P1-38 修复】移除无意义的条件判断，始终加载 django_extensions
    'django_extensions',
    'channels',  # P1-8 WebSocket 实时通知

    # Core app
    'core',

    # Local apps
    'apps.usermanagement',
    'apps.assetmanagement',
    'apps.authusermanagement',
    'apps.unregisteredasset',  # 未登记资产管理
    'apps.notification',  # P1-8 通知服务
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.request_context.RequestContextMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'apps.authusermanagement.backends.AuthUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='asset_management_backend'),
        'USER': config('DB_USER', default='root'),
        # 【P2-30 修复】默认值改为 None，生产环境必须配置，避免用占位符连接数据库
        'PASSWORD': config('DB_PASSWORD', default=None),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        # 【AGENTS 规范 - 性能优化】MySQL 连接池配置
        # CONN_MAX_AGE: 连接保持时间（秒），复用连接减少新建/断开开销
        # 600秒 = 10分钟，平衡连接复用与资源释放
        'CONN_MAX_AGE': 600,
        # CONN_HEALTH_CHECKS: 每次从连接池取出连接时检查可用性（Django 4.1+）
        # 防止连接超时断开导致的 "MySQL server has gone away" 错误
        'CONN_HEALTH_CHECKS': True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'core.password_validators.ComplexPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.CustomPageNumberPagination',   # 自定义分页类
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # 【修复】全局异常处理器，统一异常响应格式
    'EXCEPTION_HANDLER': 'core.exception_handler.custom_exception_handler',
    # 【修复】全局速率限制，防止暴力破解和滥用
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '100/minute',
        'register': '5/minute',
    },
}

# Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    # 【修复】JWT 配置统一：启用 refresh token 轮换
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'auth_id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
}

# CORS
# 【修复 S2】移除 CORS_ALLOW_ALL_ORIGINS，仅使用白名单
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173'
)
if CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(',') if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {message}', 'style': '{'},
        'json': {'()': 'core.json_formatter.StructuredJSONFormatter'},
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            # 【修复】使用 RotatingFileHandler 替代 FileHandler，支持日志轮转
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'django.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        'django.server': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'rest_framework': {'handlers': ['console'], 'level': 'DEBUG'},
    },
}

# drf-spectacular settings
SPECTACULAR_SETTINGS = {
    'TITLE': '资产管理系统 API',
    'DESCRIPTION': '资产管理系统接口文档（支持 JWT 认证、资产/合同/仓库等模块）',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY_SCHEMES': {
        'BearerAuth': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': '格式：Bearer {access_token}（注意 Bearer 后有空格）',
        }
    },
    'SECURITY': [{'BearerAuth': []}],
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'SERVE_URLCONF': 'config.urls',
    'EXPORT_FILE_NAME': 'asset_api',
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
        'docExpansion': 'none',
        'filter': True,
    },
    # 【修复】ENUM_NAME_OVERRIDES 使用正确的模型路径
    "ENUM_NAME_OVERRIDES": {
        # "CurrentStateEnum": "apps.assetmanagement.models.ASSET_STATUS_CHOICES",
        "AssetStatusEnum": "apps.assetmanagement.models.Asset.ASSET_STATUS_CHOICES",
        "OutAssetTypeEnum": "apps.assetmanagement.models.OutAsset.OUTASSET_TYPE_CHOICES",
        "OutassetStatusEnum": "apps.assetmanagement.models.OutAsset.OUTASSET_STATUS_CHOICES",
        "UserStatusEnum": "apps.usermanagement.models.Employee.EMPLOYEE_STATUS_CHOICES",
    },
    # 【修复】开发环境显示 schema 警告
    "WARNINGS": True if DEBUG else False,
}

# 【修复 auth.W004】auth_username 使用条件唯一约束(仅激活用户唯一)，
# 软删除场景下允许已删除用户保留用户名，因此抑制该警告
SILENCED_SYSTEM_CHECKS = ['auth.W004']

# ============================
# P1-8 WebSocket 通道层配置
# 开发环境使用 InMemoryChannelLayer（无需 Redis）
# 生产环境切换为 RedisChannelLayer
# ============================
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
