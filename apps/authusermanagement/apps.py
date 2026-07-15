"""
认证与用户管理应用配置
"""

from django.apps import AppConfig


class AuthusermanagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authusermanagement"
    verbose_name = "认证与用户管理"
