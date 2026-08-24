"""
资产模块接口契约定义

【AGENTS 规范 - 跨应用解耦】
通过抽象接口定义员工数据契约,资产模块不直接依赖员工模块的具体实现。

使用方式:
    from apps.assetmanagement.interfaces import get_employee_queryset, get_employee_serializer_class
"""

from typing import Any
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmployeeDTO:
    """
    员工数据传输对象

    Attributes:
        jobcode: 员工工号(唯一标识)
        name: 员工姓名
        department: 所属部门
        is_active: 是否在职
    """

    jobcode: str
    name: str
    department: str | None = None
    is_active: bool = True

    def __str__(self) -> str:
        return f"{self.name}({self.jobcode})"


class EmployeeProvider(ABC):
    """
    员工数据提供者接口

    实现类:
        - DjangoEmployeeProvider: Django ORM实现(生产环境)
        - MockEmployeeProvider: Mock实现(单元测试)
    """

    @abstractmethod
    def get_employee_queryset(self) -> Any:
        """获取员工QuerySet(用于DRF SlugRelatedField)"""
        pass

    @abstractmethod
    def get_serializer_class(self) -> type:
        """获取员工序列化器类"""
        pass


# ===================================================================
# 模块级依赖注册(简约至上,避免过度设计)
# ===================================================================

_employee_provider: EmployeeProvider | None = None


def register_employee_provider(provider: EmployeeProvider) -> None:
    """
    注册员工数据提供者

    【AGENTS 规范 - 模块级注册】
    在应用启动时注册具体的提供者实现。

    Args:
        provider: 员工数据提供者实例

    Example:
        # apps/assetmanagement/apps.py
        from apps.assetmanagement.interfaces import register_employee_provider
        from apps.usermanagement.providers import DjangoEmployeeProvider

        class AssetmanagementConfig(AppConfig):
            def ready(self):
                register_employee_provider(DjangoEmployeeProvider())
    """
    global _employee_provider
    _employee_provider = provider


def get_employee_provider() -> EmployeeProvider:
    """
    获取员工数据提供者

    【AGENTS 规范 - 显式获取】
    通过此函数获取已注册的员工数据提供者。

    Returns:
        EmployeeProvider: 已注册的员工数据提供者

    Raises:
        RuntimeError: 如果提供者未注册

    Example:
        provider = get_employee_provider()
        employee = provider.get_employee_by_jobcode('E001')
    """
    if _employee_provider is None:
        raise RuntimeError("EmployeeProvider 未注册。请在应用启动时调用 register_employee_provider()。")
    return _employee_provider


def get_employee_queryset():
    """
    获取员工QuerySet的快捷方法

    【DRF兼容】供序列化器直接使用。

    Returns:
        QuerySet: 员工模型QuerySet

    Example:
        class AssetCreateSerializer(serializers.ModelSerializer):
            asset_management_person = serializers.SlugRelatedField(
                slug_field='employee_jobcode',
                queryset=get_employee_queryset(),  # 使用快捷方法
                required=False,
                allow_null=True
            )
    """
    return get_employee_provider().get_employee_queryset()


def get_employee_serializer_class():
    """
    获取员工序列化器类的快捷方法

    【DRF兼容】供序列化器直接使用。

    Returns:
        Type: 员工序列化器类

    Example:
        class AssetDetailSerializer(serializers.ModelSerializer):
            asset_entry_person = get_employee_serializer_class()(source='...', read_only=True)
    """
    return get_employee_provider().get_serializer_class()
