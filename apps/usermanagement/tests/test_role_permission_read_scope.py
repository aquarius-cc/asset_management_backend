"""[P3-9] 角色/权限点读面收口回归（IsAuthenticated → IsSystemAdmin）。

矩阵依据:规则文档 §4.2.1 读面豁免登记——roles/permissions 读面收口后
一般登录用户不可枚举角色/权限配置面;豁免表(departments tree /
asset-types / storages)不受本文件约束(消费方与理由见 §4.2.1)。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole, Role
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

ROLES_URL = reverse("roles-list")
PERMISSIONS_URL = reverse("permissions-list")

_NON_ADMIN_ROLES = (
    EmployeeRole.REGULAR_USER,
    EmployeeRole.ASSET_ADMIN,
    EmployeeRole.DEPT_MANAGER,
    EmployeeRole.AUDITOR,
)


@pytest.fixture
def department(db):
    """测试部门(部门级角色须带部门,排除 get_user_role 无部门 None 降级干扰)"""
    return Department.objects.create(department_code="D-RP", department_name="读面收口测试部门")


def _user_with_role(username: str, role: EmployeeRole, department) -> AuthUser:
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}用户",
        employee_department=department,
        role=role,
        employee_phone=f"1391000{abs(hash(username)) % 10000:04d}",
    )
    return AuthUser.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_phone=f"1381000{abs(hash(username)) % 10000:04d}",
    )


def test_anonymous_roles_and_permissions_401(api_client):
    """匿名读角色/权限:401(JWT 挑战头;IsSystemAdmin 匿名恒拒)"""
    assert api_client.get(ROLES_URL).status_code == status.HTTP_401_UNAUTHORIZED
    assert api_client.get(PERMISSIONS_URL).status_code == status.HTTP_401_UNAUTHORIZED


def test_system_admin_read_200(api_client, department):
    """正例锚:system_admin 可读两读面"""
    user = _user_with_role("rp_sysadmin", EmployeeRole.SYSTEM_ADMIN, department)
    api_client.force_authenticate(user=user)
    assert api_client.get(ROLES_URL).status_code == status.HTTP_200_OK
    assert api_client.get(PERMISSIONS_URL).status_code == status.HTTP_200_OK


def test_superuser_read_200(api_client):
    """正例锚:is_superuser 经 get_user_role 映射 system_admin,可读两读面"""
    user = AuthUser.objects.create_user(auth_username="rp_superuser", password=TEST_PASSWORD, is_superuser=True)
    api_client.force_authenticate(user=user)
    assert api_client.get(ROLES_URL).status_code == status.HTTP_200_OK
    assert api_client.get(PERMISSIONS_URL).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("role", _NON_ADMIN_ROLES)
def test_non_admin_read_403(api_client, department, role):
    """regular_user/asset_admin/dept_manager/auditor:roles/permissions 读面均 403"""
    user = _user_with_role(f"rp_{role.value}", role, department)
    api_client.force_authenticate(user=user)
    assert api_client.get(ROLES_URL).status_code == status.HTTP_403_FORBIDDEN
    assert api_client.get(PERMISSIONS_URL).status_code == status.HTTP_403_FORBIDDEN


def test_retrieve_role_403_for_regular_user(api_client, department):
    """retrieve(主键可枚举面)同样 403"""
    role = Role.objects.create(role_code="ROLE-RP", role_name="读面测试角色")
    user = _user_with_role("rp_regular2", EmployeeRole.REGULAR_USER, department)
    api_client.force_authenticate(user=user)
    resp = api_client.get(reverse("roles-detail", kwargs={"pk": role.pk}))
    assert resp.status_code == status.HTTP_403_FORBIDDEN
