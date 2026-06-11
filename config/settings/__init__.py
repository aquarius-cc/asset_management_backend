# d:\CodeDemo\Python\asset_management_backend\config\settings\__init__.py
"""
Django 设置模块
"""

from .base import *

# 根据环境变量加载相应配置
import os

env = os.getenv('DJANGO_ENV', 'development')

if env == 'production':
    from .production import *
elif env == 'test':
    from .test import *
else:
    from .development import *