"""
用户管理服务层

提供员工、部门、权限、角色的业务逻辑处理。
"""

from .department_service import DepartmentService
from .employee_service import EmployeeService
from .permission_service import PermissionService
from .role_service import RoleService


__all__ = [
    "DepartmentService",
    "EmployeeService",
    "PermissionService",
    "RoleService",
]
