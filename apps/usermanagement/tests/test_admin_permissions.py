"""
系统管理写权限门禁回归测试(P7-3)

验证 IsAdminUser → IsSystemAdmin 迁移后的门禁语义:
- 员工/部门/用户管理写操作仅 system_admin(role,含 is_superuser)可访问
- role-based system_admin 不依赖遗留 is_staff 通道
- 本人账号自维护(update/partial_update/destroy)不受影响

【权限矩阵依据】backend-business-rules.md §4.2"系统配置:类型/仓库/合同/员工/部门/用户"仅 system_admin ✅;
B11 要求写操作必须通过角色权限类,禁止仅用 IsAdminUser。
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole


def _make_user(username, role, department=None):
    user = AuthUser.objects.create_user(auth_username=username, password="test1234")
    if role:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
        )
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def dept(db):
    return Department.objects.create(department_code="ADM_DEPT", department_name="管理部门")


@pytest.fixture
def sys_admin(db, dept):
    """role-based system_admin,无部门且无 is_staff(纯角色通道)"""
    return _make_user("adm_sys", EmployeeRole.SYSTEM_ADMIN, department=None)


@pytest.fixture
def dept_manager(db, dept):
    return _make_user("adm_dm", EmployeeRole.DEPT_MANAGER, department=dept)


@pytest.fixture
def regular_user(db, dept):
    return _make_user("adm_ru", EmployeeRole.REGULAR_USER, department=dept)


@pytest.fixture
def other_user(db):
    return AuthUser.objects.create_user(auth_username="adm_other", password="test1234")


@pytest.mark.django_db
class TestDepartmentManagementGate:
    """部门管理写操作:仅 system_admin"""

    def test_create_denied_for_dept_manager(self, api_client, dept_manager):
        api_client.force_authenticate(user=dept_manager)
        response = api_client.post(
            reverse("departments-list"),
            {"department_code": "NEW001", "department_name": "新部门"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_denied_for_regular_user(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        response = api_client.post(
            reverse("departments-list"),
            {"department_code": "NEW002", "department_name": "新部门"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_allowed_for_system_admin(self, api_client, sys_admin):
        api_client.force_authenticate(user=sys_admin)
        response = api_client.post(
            reverse("departments-list"),
            {"department_code": "NEW003", "department_name": "新部门", "department_information": "info"},
            format="json",
        )
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert Department.objects.filter(department_code="NEW003").exists()


@pytest.mark.django_db
class TestUserManagementGate:
    """用户账号管理:列表/详情仅 system_admin"""

    def test_list_denied_for_regular_user(self, api_client, regular_user, other_user):
        api_client.force_authenticate(user=regular_user)
        response = api_client.get(reverse("users-list"))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_allowed_for_system_admin(self, api_client, sys_admin, other_user):
        api_client.force_authenticate(user=sys_admin)
        response = api_client.get(reverse("users-list"))
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestUserObjectPermission:
    """账号对象级权限:本人自维护 + system_admin 可管理他人"""

    def test_self_update_allowed_for_regular_user(self, api_client, regular_user):
        api_client.force_authenticate(user=regular_user)
        response = api_client.patch(
            reverse("users-detail", kwargs={"auth_id": regular_user.auth_id}),
            {"auth_phone": "13900139011"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_update_other_denied_for_regular_user(self, api_client, regular_user, other_user):
        api_client.force_authenticate(user=regular_user)
        response = api_client.patch(
            reverse("users-detail", kwargs={"auth_id": other_user.auth_id}),
            {"auth_phone": "13900139012"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_other_allowed_for_system_admin(self, api_client, sys_admin, other_user):
        api_client.force_authenticate(user=sys_admin)
        response = api_client.patch(
            reverse("users-detail", kwargs={"auth_id": other_user.auth_id}),
            {"auth_phone": "13900139013"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
