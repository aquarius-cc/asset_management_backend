"""
Django base settings for asset_management project.
"""

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from decouple import config


# 项目根目录(asset_management_backend/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# W-2 修复: 确保日志目录存在（本地开发/CI/裸运行场景必需）
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# SECURITY WARNING: keep the secret key used in production secret!
# 安全: 不设弱默认值,各环境文件负责提供密钥
# - production.py: 从环境变量读取,缺失或弱密钥则抛异常
# - development.py: 从环境变量读取,缺失则用开发专用密钥
# - test.py: 硬编码测试密钥
# 若直接使用 base.py,须拒绝启动: base 为抽象基类,不提供可运行密钥,
# 直接部署会导致空 SECRET_KEY(SIGNING_KEY)被用于 JWT HMAC 签名,token 可被伪造。
# 守卫依据 DJANGO_SETTINGS_MODULE 判定(下方),环境变量为具体环境时零影响。
SECRET_KEY = config("SECRET_KEY", default="")

# 【SC-1 守卫】base.py 禁止直接部署: 模块加载即 fail-fast。
# 触发条件: DJANGO_SETTINGS_MODULE 恰好等于 config.settings.base。
# 三层环境(development/production/test/test_postgres)均不等于 base, 不触发;
# 误配 base 的部署在启动瞬间抛 ImproperlyConfigured, 空 SECRET_KEY 到不了 JWT 签名
# (即使绕过守卫, SIMPLE_JWT 已无物化 SIGNING_KEY, simplejwt 回落 settings.SECRET_KEY)。
if os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.base":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "config.settings.base is an abstract base settings and cannot be deployed directly. "
        "Use config.settings.development / config.settings.production / config.settings.test "
        "(or config.settings.test_postgres)."
    )

# 【修复 S3】DEBUG 默认值为 False,生产环境更安全
DEBUG = config("DEBUG", default=False, cast=bool)

# 【修复 S2】ALLOWED_HOSTS 默认空列表,仅允许配置的域名
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="")
if ALLOWED_HOSTS:
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS.split(",") if host.strip()]
else:
    ALLOWED_HOSTS = []

# 【SC 加固 #35】是否信任反向代理注入的 X-Forwarded-For(请求 IP 溯源)。
# False(默认):仅使用 REMOTE_ADDR——直连取真实 IP,代理后取代理 IP,攻击者无法伪造审计 IP;
# True:运维显式声明部署在可信反向代理(Nginx/ALB)之后,才解析 X-Forwarded-For 首值。
TRUST_PROXY_HEADERS = config("TRUST_PROXY_HEADERS", default=False, cast=bool)

# 【资源防护 #40】Excel 导出行数上限,超限拒绝导出(防止无界 queryset 全量迭代 OOM)
EXPORT_MAX_ROWS = config("EXPORT_MAX_ROWS", default=10000, cast=int)

# 自定义用户模型
AUTH_USER_MODEL = "authusermanagement.AuthUser"

INSTALLED_APPS = [
    "daphne",  # 必须在最前面,启用 ASGI 模式支持 WebSocket
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # 【新增】Token 黑名单应用,支持主动作废 Token
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "corsheaders",
    "django_filters",
    # 【P1-38 修复】移除无意义的条件判断,始终加载 django_extensions
    "django_extensions",
    "channels",  # P1-8 WebSocket 实时通知
    # Core app
    "core",
    # Local apps
    "apps.usermanagement",
    "apps.assetmanagement",
    "apps.authusermanagement",
    "apps.unregisteredasset",  # 未登记资产管理
    "apps.notification",  # P1-8 通知服务
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.csp_middleware.ContentSecurityPolicyMiddleware",  # L-2: CSP 安全头
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.prometheus_middleware.PrometheusMiddleware",  # OC-4: Prometheus 指标采集
    "core.request_context.RequestContextMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "apps.authusermanagement.backends.AuthUserBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="asset_management_backend"),
        "USER": config("DB_USER", default="postgres"),
        # 【P2-30 修复】默认值改为 None,生产环境必须配置,避免用占位符连接数据库
        "PASSWORD": config("DB_PASSWORD", default=None),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        # 【AGENTS 规范 - 性能优化】PostgreSQL 连接配置
        # CONN_MAX_AGE: 连接保持时间(秒),复用连接减少新建/断开开销
        # 600秒 = 10分钟,平衡连接复用与资源释放
        "CONN_MAX_AGE": 600,
        # CONN_HEALTH_CHECKS: 每次从连接池取出连接时检查可用性(Django 4.1+)
        # 防止连接超时断开导致的连接失效问题
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "core.password_validators.ComplexPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# 文件上传安全配置 (SC-5)
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB: 超过此大小写入临时文件
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB: 请求体大小限制
FILE_UPLOAD_PERMISSIONS = 0o644  # 文件权限: owner rw, group/others r
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755  # 目录权限: owner rwx, group/others rx

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.authusermanagement.authentication.JWTCookieAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    "DEFAULT_PAGINATION_CLASS": "core.pagination.CustomPageNumberPagination",  # 自定义分页类
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # 【修复】全局异常处理器,统一异常响应格式
    "EXCEPTION_HANDLER": "core.exception_handler.custom_exception_handler",
    # 【修复】全局速率限制,防止暴力破解和滥用
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",
        "user": "100/minute",
        "register": "5/minute",
        "login": "5/minute",
    },
}

# Simple JWT
# 【SC-1】SIGNING_KEY 不在 base 物化: simplejwt 的 api_settings 无该用户键时回落
# DEFAULTS["SIGNING_KEY"] = settings.SECRET_KEY(运行时), 各环境文件已覆写 SECRET_KEY,
# 避免 base 加载时快照空值导致全部环境 JWT 用空密钥签名(详见审查报告 #20)。
SIMPLE_JWT = {
    # 【BF-010 A2】2h→30min 压缩改密后旧 access 残留窗口(报告原写"10 分钟"有误)；
    # test 环境单独 pin 5min(config/settings/test.py:110);前端纯 401 单飞刷新,零功能成本
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # 【修复】JWT 配置统一:启用 refresh token 轮换
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "auth_id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
}

# =============================================================================
# JWT Cookie 双通道配置 (PC 浏览器 Cookie 通道 / 移动端 Bearer 通道)
# 通道判定: 请求带 Authorization: Bearer 头 -> bearer; 否则 -> cookie
# =============================================================================
JWT_AUTH_COOKIE_ACCESS = "asset_access_token"
JWT_AUTH_COOKIE_REFRESH = "asset_refresh_token"
# access cookie 为 session cookie (浏览器关闭即失效)
JWT_AUTH_COOKIE_ACCESS_MAX_AGE = None
# refresh cookie 有效期 7 天 (与 JWT REFRESH_TOKEN_LIFETIME 一致)
JWT_AUTH_COOKIE_REFRESH_MAX_AGE = 60 * 60 * 24 * 7
JWT_AUTH_COOKIE_SECURE = config("JWT_AUTH_COOKIE_SECURE", default=False, cast=bool)
JWT_AUTH_COOKIE_SAMESITE = "Lax"

# CSRF 双通道配套: csrftoken 需 JS 可读 (写入 X-CSRFToken 请求头)
# 安全边界: csrf_token 为公开值(不含敏感信息), httpOnly=False 是 double-submit cookie 模式的必要配置
# 真正的安全依赖: SameSite=Lax + Secure(生产环境) + Origin 校验
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)

# CORS
# 【修复 S2】移除 CORS_ALLOW_ALL_ORIGINS,仅使用白名单
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
)
if CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True

# 【新增】导出接口自定义响应头。默认同源部署(vite proxy / 反向代理)下浏览器已可
# 读取 X-Export-*；此处显式暴露以支持前后端跨源部署的场景。
# 取值与 core.excel_export.streaming.HEADER_* 常量保持一致。
CORS_EXPOSE_HEADERS = [
    "X-Export-Max-Rows",
    "X-Export-Total-Count",
    "Content-Disposition",
]

# 【新增】前端基础URL, 用于生成二维码扫码链路
FRONTEND_BASE_URL = config("FRONTEND_BASE_URL", default="http://localhost:5173")

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]

# Content-Security-Policy (L-2)
# 开发环境自动使用 Report-Only 模式,生产环境强制执行
CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-eval'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "connect-src": "'self' ws: wss:",
    "font-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
}

# Logging
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
        "json": {"()": "core.json_formatter.StructuredJSONFormatter"},
    },
    "filters": {
        "trace_id": {"()": "core.logging_filters.TraceIDFilter"},
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 1024 * 1024 * 10,  # 10MB
            "backupCount": 5,
            "formatter": "json",
            "filters": ["trace_id"],
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "rest_framework": {"handlers": ["console", "file"], "level": "DEBUG"},
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
}

# drf-spectacular settings
SPECTACULAR_SETTINGS = {
    "TITLE": "资产管理系统 API",
    "DESCRIPTION": "资产管理系统接口文档(支持 JWT 认证、资产/合同/仓库等模块)",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY_SCHEMES": {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "格式:Bearer {access_token}(注意 Bearer 后有空格)",
        }
    },
    "SECURITY": [{"BearerAuth": []}],
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "SERVE_URLCONF": "config.urls",
    "EXPORT_FILE_NAME": "asset_api",
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "docExpansion": "none",
        "filter": True,
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

# 【SILENCED_SYSTEM_CHECKS 说明】
# auth.W004: Django 检测到 User.username 无 unique=True 约束。
# 本项目使用 auth_username 字段(非 Django 内置 username),
# 已通过 UniqueConstraint(fields=["auth_phone"], condition=Q(auth_is_active=True))
# 实现条件唯一。软删除(is_active=False)允许已删除用户保留用户名,
# 因此抑制此警告。修改此配置前须评估对用户注册唯一性的影响。
SILENCED_SYSTEM_CHECKS = ["auth.W004"]

# ============================
# P1-8 WebSocket 通道层配置
# 开发环境使用 InMemoryChannelLayer(无需 Redis)
# 生产环境切换为 RedisChannelLayer
# ============================
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
