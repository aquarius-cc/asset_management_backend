"""
未登记资产管理应用配置

该模块定义 Django 应用配置类，遵循 Django 应用规范。

【AGENTS 规范 - 应用配置】
- 使用显式 AppConfig 类
- 定义应用元数据（名称、标签、verbose_name）
- 在 ready() 中注册信号（如需要）

【跨应用说明】
本应用依赖 assetmanagement 的状态机和审计功能，
通过服务层延迟导入避免循环依赖。
"""

from django.apps import AppConfig


class UnregisteredAssetConfig(AppConfig):
    """
    未登记资产管理应用配置类
    
    Attributes:
        default_auto_field: 默认主键类型
        name: 应用完整 Python 路径
        verbose_name: 管理后台显示名称
        label: 应用标签（用于反向解析URL）
    """
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.unregisteredasset'
    verbose_name = '未登记资产管理'
    label = 'unregisteredasset'
    
    def ready(self) -> None:
        """
        应用启动时的初始化方法
        
        【AGENTS 规范 - 信号注册】
        - 在此处导入并注册信号处理器
        - 避免在模块顶层导入导致循环依赖
        
        【当前实现】
        暂不注册信号，保持简单。如需审计信号可在此扩展。
        """
        # 延迟导入避免循环依赖
        # from . import signals  # noqa: F401
        pass
