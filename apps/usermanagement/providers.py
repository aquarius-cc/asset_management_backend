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

批次5 M-45 批C：Mock 三件套（MockEmployeeProvider/MockQuerySet/
MockEmployeeSerializer）删除——docstring 声称"用于单元测试"，实际全仓
零引用（YAGNI；测试直接用真实 ORM 夹具）。
"""

from typing import Any

from apps.assetmanagement.interfaces import EmployeeProvider
from apps.usermanagement.models import Employee, EmployeeStatus
from apps.usermanagement.serializers import EmployeeSerializer


class DjangoEmployeeProvider(EmployeeProvider):
    """
    Django ORM 实现的员工数据提供者
    """

    def get_employee_queryset(self) -> Any:
        """获取员工QuerySet(已过滤 employee_status='active')"""
        return Employee.objects.filter(employee_status=EmployeeStatus.ACTIVE)

    def get_serializer_class(self) -> type:
        """获取员工序列化器类"""
        return EmployeeSerializer
