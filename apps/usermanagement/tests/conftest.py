"""
用户管理测试配置

MA-23 包 1b（单域试点）：造数改走 factory_boy 工厂（`tests/factories.py`），
**fixture 签名与返回值保持不变**，既有调用方零改动。
"""

import pytest
from rest_framework.test import APIClient

from apps.usermanagement.tests.factories import DepartmentFactory, EmployeeFactory


# OP-09 批次 8 提交 3：api_schema fixture 上提至根 conftest.py（跨域共享，DR-1）。


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def department(db):
    """测试部门(根部门)"""
    return DepartmentFactory(
        department_code="DTEST",
        department_name="测试部门",
        department_information="测试信息员",
        parent=None,  # 根部门
        level=0,
        path="/DTEST",
    )


@pytest.fixture
def child_department(db, department):
    """测试子部门"""
    return DepartmentFactory(
        department_code="DTEST_CHILD",
        department_name="测试子部门",
        department_information="测试子部门信息员",
        parent=department,
        level=1,
        path=f"{department.path}/DTEST_CHILD",
    )


@pytest.fixture
def test_employee(db, department):
    """测试员工"""
    return EmployeeFactory(
        employee_jobcode="UTEST",
        employee_name="测试员工",
        employee_department=department,
        employee_phone="13800139001",
    )
