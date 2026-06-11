"""
资产管理应用配置
"""
from django.apps import AppConfig


class AssetmanagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.assetmanagement'
    verbose_name = '资产管理'

    def ready(self):
        # 【AGENTS 规范 - 状态机解耦】Signal 已废弃，状态变更由 Service 层显式处理
        # import apps.assetmanagement.signals
        
        # 【AGENTS 规范 - 跨应用解耦】注册员工数据提供者
        # 【注意】导入放在方法内避免循环导入
        from apps.assetmanagement.interfaces import register_employee_provider
        from apps.usermanagement.providers import DjangoEmployeeProvider
        register_employee_provider(DjangoEmployeeProvider())
