# d:\CodeDemo\Python\asset_management_backend\config\settings\__init__.py
"""
Django 设置模块
"""

# 【P2-34 修复】移除顶层 base import，由环境配置文件统一导入 base
# 避免 base.py 被重复导入两次

# 根据环境变量加载相应配置
import os


env = os.getenv('DJANGO_ENV', 'development')

if env == 'production':
    from .production import *
elif env == 'test':
    from .test import *
else:
    from .development import *
