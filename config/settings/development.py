# =============================================================================
# development.py - 开发环境配置
# =============================================================================
# ⚠️⚠️⚠️ 【安全警告】⚠️⚠️⚠️
#
# 此文件包含开发环境的配置,请勿在生产环境使用!
#
# 生产环境要求:
# 1. DEBUG 必须设为 False
# 2. SECRET_KEY 必须设置强随机密钥
# 3. ALLOWED_HOSTS 必须限制为具体域名
# 4. 数据库密码必须使用复杂密码
#
# 查看 docs/DEPLOYMENT.md 了解生产部署最佳实践
# =============================================================================

from .base import *

# 开发环境密钥（本地使用，可提交到版本控制）
# 如需更强密钥，通过环境变量 SECRET_KEY 或 .env 文件覆盖
import os

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-only-key-!@#$%^&*()_+-=[]{}|;:,.<>?-not-for-production-2026",
)

# C-2: 验证密钥安全性 — 防止 base.py placeholder 泄漏到此环境
from django.core.exceptions import ImproperlyConfigured

_INSECURE_KEYS = frozenset({
    "django-insecure-placeholder-see-env-settings",
    "django-insecure-dev-only-key-change-in-production-1234567890",
    "change-me-in-production",
    "your-secret-key-here-change-in-production",
    "change-this-to-a-real-secret-key-before-running",
    "changeme",
    "",
})
if SECRET_KEY in _INSECURE_KEYS:
    raise ImproperlyConfigured(
        "SECRET_KEY is insecure. Set a strong key via env var or .env file.\n"
        "Generate: python -c \"from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())\""
    )


# =============================================================================
# 【安全配置 - 开发专用】
# =============================================================================

# 【⚠️ 安全风险】调试模式开启,会暴露详细错误信息和调试数据
# 【生产要求】必须设为 False
DEBUG = True

# 【⚠️ 安全风险】允许所有主机访问
# 【生产要求】限制为具体域名,如:['api.example.com', 'www.example.com']
ALLOWED_HOSTS = ["*"]

# =============================================================================
# 【邮件配置 - 开发专用】
# =============================================================================

# 开发环境使用控制台邮件后端,不真实发送邮件
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# =============================================================================
# 【开发工具配置】
# =============================================================================

# Django Debug Toolbar(可选,取消注释以启用)
# 【注意】仅开发环境使用,生产环境不要启用
# INSTALLED_APPS += [
#     'debug_toolbar',
# ]
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# =============================================================================
# 【数据库配置 - 开发专用】
# =============================================================================

# 默认使用 PostgreSQL(与 base.py 保持一致)
# 如需使用 SQLite 进行快速开发,取消注释以下配置:

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# =============================================================================
# 【密钥配置说明】
# =============================================================================

# 【易错点】开发环境使用 base.py 中定义的默认 SECRET_KEY
# 【生产要求】必须通过环境变量设置强随机密钥:
#   SECRET_KEY=<使用 python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"> 生成
# =============================================================================
