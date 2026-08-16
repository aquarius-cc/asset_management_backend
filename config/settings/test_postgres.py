# =============================================================================
# test_postgres.py - 测试环境配置(PostgreSQL)
# =============================================================================
"""
测试环境专用配置(PostgreSQL)

【配置说明】
- 复用 test.py 的测试加速配置(密码哈希/缓存/邮件)
- 数据库引擎使用 PostgreSQL(与生产/开发保持一致)
- 连接参数通过真实环境变量注入(os.environ),不读取 .env,
  避免仓库内 .env 的历史配置串入本模块
- 运行方式: pytest --ds config.settings.test_postgres
"""

import os

from .test import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "asset_management_backend"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
    }
}
