"""
用户管理模块提供者实现

【AGENTS 规范 - 跨应用解耦】
实现 EmployeeProvider 接口,为资产模块提供员工数据。

设计原则:
1. 依赖倒置 - 实现资产模块定义的接口契约
2. 单一职责 - 只负责员工数据的提供,不处理业务逻辑
3. 适配器模式 - 将 Employee 模型适配为 EmployeeDTO

使用方式:
    # apps/assetmanagement/apps.py
    from apps.assetmanagement.interfaces import register_employee_provider
    from apps.usermanagement.providers import DjangoEmployeeProvider

    class AssetmanagementConfig(AppConfig):
        def ready(self):
            register_employee_provider(DjangoEmployeeProvider())
"""

from collections.abc import Iterator
from typing import Any

from apps.assetmanagement.interfaces import EmployeeDTO, EmployeeProvider
from apps.usermanagement.models import Employee
from apps.usermanagement.serializers import EmployeeSerializer


class DjangoEmployeeProvider(EmployeeProvider):
    """
    Django ORM 实现的员工数据提供者
    """

    def get_employee_queryset(self) -> Any:
        """获取员工QuerySet(已过滤 employee_status='active')"""
        return Employee.objects.filter(employee_status="active")

    def get_serializer_class(self) -> type:
        """获取员工序列化器类"""
        return EmployeeSerializer


class MockEmployeeProvider(EmployeeProvider):
    """
    Mock 实现的员工数据提供者,用于单元测试
    """

    def __init__(self, employees: list[EmployeeDTO] | None = None):
        self._employees = employees or []

    def get_employee_queryset(self) -> Any:
        """获取Mock QuerySet"""
        return MockQuerySet(self._employees)

    def get_serializer_class(self) -> type:
        """获取Mock序列化器类"""
        return MockEmployeeSerializer


class MockQuerySet:
    """
    Mock QuerySet 实现

    模拟Django QuerySet的基本操作,用于单元测试。
    """

    def __init__(self, data: list[EmployeeDTO]):
        self._data = data

    def __iter__(self) -> Iterator[EmployeeDTO]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def filter(self, **kwargs: Any) -> "MockQuerySet":
        """模拟filter方法"""
        # 简化实现,仅支持基本过滤
        result = self._data
        return MockQuerySet(result)

    def all(self) -> "MockQuerySet":
        """模拟all方法"""
        return MockQuerySet(self._data.copy())


class MockEmployeeSerializer:
    """
    Mock 员工序列化器

    模拟 EmployeeSerializer 的基本行为,用于单元测试。
    """

    def __init__(self, instance: Any = None, data: Any = None, **kwargs: Any) -> None:
        self.instance = instance
        self._data = data

    @property
    def data(self) -> dict[str, Any]:
        """返回序列化后的数据"""
        if self.instance:
            return {
                "employee_jobcode": self.instance.jobcode,
                "employee_name": self.instance.name,
                "employee_department": self.instance.department,
            }
        return {}
