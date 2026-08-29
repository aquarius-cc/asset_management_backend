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

# 开发环境密钥（本地使用，可提交到版本控制）
# 如需更强密钥，通过环境变量 SECRET_KEY 或 .env 文件覆盖
import os

from .base import *


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

# 限制为常见开发主机,可通过 ALLOWED_HOSTS 环境变量覆盖
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,[::1]").split(",") if h.strip()]

# CSRF: 开发环境 HTTP 不需要 Secure 标志
CSRF_COOKIE_SECURE = False

# 【Bug修复 2026-XX】Vite 代理(5173→8000)导致请求 Origin 与 Host 不一致,
# Django ≥4.0 的 Origin 校验拒绝跨源 POST, 使 cookie 通道的 token/refresh 端点
# 返回 403(CSRF Failed: Origin checking failed), 前端误判会话失效并跳转登录页。
# 仅将已知开发前端源加入白名单; X-CSRFToken/cookie 对比检查不受影响, 生产配置不变。
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

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
