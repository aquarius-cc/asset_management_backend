"""
用户管理测试配置
"""

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.usermanagement.models import Department, Employee


@pytest.fixture(scope="session")
def api_schema():
    """整份 OpenAPI schema，**全 session 只生成一次**。

    提到 conftest 且放宽到 session 级的原因：``SchemaGenerator().get_schema()`` 会
    introspect 全量视图，成本高；BF-051 的护栏需要看**全量 operation** 的 security
    引用（不止员工域），与员工护栏消费的是同一份产物，重复生成纯属浪费（DR-1）。

    session 级安全前提：schema 生成不查库、不读模块级可变状态，且当前两个消费方
    （``test_employee_openapi_contract`` / ``test_openapi_security_schema``）都不
    改动 schema 相关 settings。若将来出现会改 ``SPECTACULAR_SETTINGS`` 的用例，
    需把本 fixture 降回 module 级。
    """
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def department(db):
    """测试部门(根部门)"""
    return Department.objects.create(
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
    return Department.objects.create(
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
    return Employee.objects.create(
        employee_jobcode="UTEST",
        employee_name="测试员工",
        employee_department=department,
        employee_phone="13800139001",
    )
