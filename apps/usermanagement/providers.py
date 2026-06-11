"""
用户管理模块提供者实现

【AGENTS 规范 - 跨应用解耦】
实现 EmployeeProvider 接口，为资产模块提供员工数据。

设计原则:
1. 依赖倒置 - 实现资产模块定义的接口契约
2. 单一职责 - 只负责员工数据的提供，不处理业务逻辑
3. 适配器模式 - 将 Employee 模型适配为 EmployeeDTO

使用方式:
    # apps/assetmanagement/apps.py
    from apps.assetmanagement.interfaces import register_employee_provider
    from apps.usermanagement.providers import DjangoEmployeeProvider
    
    class AssetmanagementConfig(AppConfig):
        def ready(self):
            register_employee_provider(DjangoEmployeeProvider())
"""

from typing import List, Optional, Type

from apps.assetmanagement.interfaces import EmployeeProvider, EmployeeDTO
from apps.usermanagement.models import Employee
from apps.usermanagement.serializers import EmployeeSerializer


class DjangoEmployeeProvider(EmployeeProvider):
    """
    Django ORM 实现的员工数据提供者
    
    【AGENTS 规范 - 接口实现】
    使用 Django ORM 查询员工数据，实现 EmployeeProvider 接口。
    
    这是生产环境的默认实现。
    """
    
    def get_all_employees(self) -> List[EmployeeDTO]:
        """
        获取所有在职员工列表
        
        Returns:
            List[EmployeeDTO]: 员工DTO列表
        """
        return [
            EmployeeDTO(
                jobcode=e.employee_jobcode,
                name=e.employee_name,
                department=e.employee_department,
                is_active=(e.employee_status == 'active')
            )
            for e in Employee.objects.filter(employee_status='active')
        ]
    
    def get_employee_by_jobcode(self, jobcode: str) -> Optional[EmployeeDTO]:
        """
        根据工号获取员工信息
        
        Args:
            jobcode: 员工工号
            
        Returns:
            Optional[EmployeeDTO]: 员工DTO，不存在时返回None
        """
        try:
            e = Employee.objects.get(employee_jobcode=jobcode, employee_status='active')
            return EmployeeDTO(
                jobcode=e.employee_jobcode,
                name=e.employee_name,
                department=e.employee_department,
                is_active=(e.employee_status == 'active')
            )
        except Employee.DoesNotExist:
            return None
    
    def get_employee_queryset(self):
        """
        获取员工QuerySet
        
        【DRF兼容】返回Django QuerySet，供序列化器使用。
        
        Returns:
            QuerySet: 员工模型QuerySet（已过滤 employee_status='active'）
        """
        return Employee.objects.filter(employee_status='active')
    
    def get_serializer_class(self) -> Type:
        """
        获取员工序列化器类
        
        Returns:
            Type: EmployeeSerializer 类
        """
        return EmployeeSerializer


class MockEmployeeProvider(EmployeeProvider):
    """
    Mock 实现的员工数据提供者
    
    【AGENTS 规范 - 可测试性】
    用于单元测试，不依赖数据库。
    
    Example:
        # 在测试中注册Mock提供者
        from apps.assetmanagement.interfaces import register_employee_provider
        from apps.usermanagement.providers import MockEmployeeProvider
        
        mock_data = [
            EmployeeDTO(jobcode='E001', name='张三', department='技术部'),
            EmployeeDTO(jobcode='E002', name='李四', department='财务部'),
        ]
        register_employee_provider(MockEmployeeProvider(mock_data))
    """
    
    def __init__(self, employees: List[EmployeeDTO] = None):
        """
        初始化Mock提供者
        
        Args:
            employees: 预设的员工数据列表
        """
        self._employees = employees or []
    
    def get_all_employees(self) -> List[EmployeeDTO]:
        """获取所有员工"""
        return self._employees.copy()
    
    def get_employee_by_jobcode(self, jobcode: str) -> Optional[EmployeeDTO]:
        """根据工号获取员工"""
        for e in self._employees:
            if e.jobcode == jobcode:
                return e
        return None
    
    def get_employee_queryset(self):
        """
        获取Mock QuerySet
        
        【注意】返回列表模拟QuerySet，仅支持基本的迭代和过滤。
        在复杂场景下，应使用 Django 的 QuerySet 或第三方库。
        """
        # 返回一个可迭代的列表，模拟QuerySet
        return MockQuerySet(self._employees)
    
    def get_serializer_class(self) -> Type:
        """获取Mock序列化器类"""
        return MockEmployeeSerializer


class MockQuerySet:
    """
    Mock QuerySet 实现
    
    模拟Django QuerySet的基本操作，用于单元测试。
    """
    
    def __init__(self, data: List[EmployeeDTO]):
        self._data = data
    
    def __iter__(self):
        return iter(self._data)
    
    def __len__(self):
        return len(self._data)
    
    def filter(self, **kwargs):
        """模拟filter方法"""
        # 简化实现，仅支持基本过滤
        result = self._data
        return MockQuerySet(result)
    
    def all(self):
        """模拟all方法"""
        return MockQuerySet(self._data.copy())


class MockEmployeeSerializer:
    """
    Mock 员工序列化器
    
    模拟 EmployeeSerializer 的基本行为，用于单元测试。
    """
    
    def __init__(self, instance=None, data=None, **kwargs):
        self.instance = instance
        self._data = data
    
    @property
    def data(self):
        """返回序列化后的数据"""
        if self.instance:
            return {
                'employee_jobcode': self.instance.jobcode,
                'employee_name': self.instance.name,
                'employee_department': self.instance.department,
            }
        return {}
