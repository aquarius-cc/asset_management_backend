"""
用户管理应用配置
"""

from django.apps import AppConfig


class UsermanagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.usermanagement"
    verbose_name = "用户管理"
