# =============================================================================
# test.py - 测试环境配置
# =============================================================================
"""
测试环境专用配置

【配置说明】
- 使用 SQLite 内存数据库,避免依赖外部 PostgreSQL,适合本地快速跑测试
- 完整门禁请使用 PostgreSQL(默认 development 配置或 config.settings.test_postgres)
- 简化缓存配置
- 禁用密码哈希以加速测试
- 配置邮件后端为 locmem(内存存储)

【易错点】
- 不要在此文件中设置敏感信息
- 确保测试不会影响生产数据
"""

from datetime import timedelta

from .base import *


# 测试环境密钥（固定值，确保测试可重复执行）
SECRET_KEY = "test-only-key-not-for-production-use-1234567890!@#$"

# C-2: 验证密钥安全性
from django.core.exceptions import ImproperlyConfigured


_INSECURE_KEYS = frozenset(
    {
        "django-insecure-placeholder-see-env-settings",
        "django-insecure-dev-only-key-change-in-production-1234567890",
        "change-me-in-production",
        "changeme",
        "dev-only-key-!@#$%^&*()_+-=[]{}|;:,.<>?-not-for-production-2026",
        "",
    }
)
if SECRET_KEY in _INSECURE_KEYS:
    raise ImproperlyConfigured("SECRET_KEY is insecure in test environment.")


# =============================================================================
# 【数据库配置 - 测试专用】
# =============================================================================
# 使用 SQLite 内存数据库,不依赖外部数据库(本地快速验证用)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

# =============================================================================
# 【密码哈希加速 - 测试专用】
# =============================================================================
# 【易错点】生产环境绝对不能使用此配置!
# 使用快速哈希算法,将测试速度提升 10 倍以上
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# =============================================================================
# 【缓存配置 - 测试专用】
# =============================================================================
# 使用本地内存缓存
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# =============================================================================
# 【邮件配置 - 测试专用】
# =============================================================================
# 使用内存缓存存储邮件,不真实发送
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# =============================================================================
# 【日志配置 - 测试专用】
# =============================================================================
# 减少日志输出,避免测试干扰
LOGGING["handlers"]["console"]["level"] = "WARNING"

# =============================================================================
# 【调试模式 - 测试专用】
# =============================================================================
DEBUG = False

# =============================================================================
# 【模板调试 - 测试专用】
# =============================================================================
TEMPLATES[0]["OPTIONS"]["debug"] = False  # type: ignore[index]

# =============================================================================
# 【CORS 配置 - 测试专用】
# =============================================================================
# 允许所有来源,方便测试
CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# 【覆盖 base.py 中的 JWT 配置 - 测试专用】
# =============================================================================
# 使用更短的 token 有效期,方便测试
# 必须 merge 而非整替: 整替会丢掉 base 的 USER_ID_FIELD=auth_id,
# simplejwt 回落默认 id -> AuthUser 无 id 字段 -> issue_tokens 崩溃。
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=1),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
}

# =============================================================================
# 【DRF 覆盖 - 测试专用】
# =============================================================================
# 关闭默认限流类: 全量 suite / mutmut 反复跑会撞 anon 20/minute 触发 429 假红。
# 保留 rates: 带 throttle_scope 的 View(如 public scan)仍查 rates, 空 dict 会 ImproperlyConfigured。
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000000/minute",
        "user": "10000000/minute",
        "register": "10000000/minute",
        "login": "10000000/minute",
    },
}
