"""
用户管理测试配置
"""
import pytest
from rest_framework.test import APIClient
from apps.usermanagement.models import Employee, Department


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def department(db):
    """测试部门（根部门）"""
    return Department.objects.create(
        department_code='DTEST',
        department_name='测试部门',
        department_information='测试信息员',
        parent_code=None,  # 根部门
        level=0  # 层级为 0
    )


@pytest.fixture
def child_department(db, department):
    """测试子部门"""
    return Department.objects.create(
        department_code='DTEST_CHILD',
        department_name='测试子部门',
        department_information='测试子部门信息员',
        parent_code=department.department_code,
        level=1
    )


@pytest.fixture
def test_employee(db, department):
    """测试员工"""
    return Employee.objects.create(
        employee_jobcode='UTEST',
        employee_name='测试员工',
        employee_department=department
    )