"""
资产管理应用配置
"""

from django.apps import AppConfig


class AssetmanagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assetmanagement"
    verbose_name = "资产管理"

    def ready(self) -> None:
        # 【AGENTS 规范 - 跨应用解耦】注册员工数据提供者
        # 【注意】导入放在方法内避免循环导入
        from apps.assetmanagement.interfaces import register_employee_provider
        from apps.usermanagement.providers import DjangoEmployeeProvider

        register_employee_provider(DjangoEmployeeProvider())
