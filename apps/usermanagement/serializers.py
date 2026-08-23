"""
用户管理序列化器

所有序列化器已按领域拆分至独立模块,本文件仅做向后兼容 re-export。
"""

from apps.usermanagement.department_serializers import (
    DepartmentBatchCreateSerializer,
    DepartmentBatchDeleteSerializer,
    DepartmentBatchItemSerializer,
    DepartmentBatchSortSerializer,
    DepartmentMoveSerializer,
    DepartmentSerializer,
    DepartmentSortSerializer,
    DepartmentTreeSerializer,
)
from apps.usermanagement.employee_serializers import (
    EmployeeBatchCreateSerializer,
    EmployeeBatchDeleteSerializer,
    EmployeeBatchItemSerializer,
    EmployeeBatchSortSerializer,
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeSerializer,
    EmployeeSortSerializer,
    EmployeeUpdateSerializer,
)


__all__ = [
    "DepartmentBatchCreateSerializer",
    "DepartmentBatchDeleteSerializer",
    "DepartmentBatchItemSerializer",
    "DepartmentBatchSortSerializer",
    "DepartmentMoveSerializer",
    "DepartmentSerializer",
    "DepartmentSortSerializer",
    "DepartmentTreeSerializer",
    "EmployeeBatchCreateSerializer",
    "EmployeeBatchDeleteSerializer",
    "EmployeeBatchItemSerializer",
    "EmployeeBatchSortSerializer",
    "EmployeeCreateSerializer",
    "EmployeeDetailSerializer",
    "EmployeeSerializer",
    "EmployeeSortSerializer",
    "EmployeeUpdateSerializer",
]
