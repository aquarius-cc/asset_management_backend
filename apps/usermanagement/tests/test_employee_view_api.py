"""
员工查询端点 API 测试

【P1-6 回归屏障】覆盖依赖 EmployeeSelector.get_employee_by_jobcode 的两个端点:
- get_department_by_jobcode: 前置修复(soft-delete 重复不再 500)的回归锚点
- get_employee_permissions: 同上,含权限检查分支
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, Permission


@pytest.fixture
def department(db):
    return Department.objects.create(
        department_code="DTEST",
        department_name="测试部门",
        department_information="测试信息员",
        parent=None,
        level=0,
        path="/DTEST",
    )


@pytest.fixture
def auth_user(db):
    return AuthUser.objects.create_user(auth_username="EMP001", password="testpass123")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestGetDepartmentByJobcode:
    def test_success(self, api_client, auth_user, department):
        Employee.objects.create(employee_jobcode="EMP001", employee_name="员工", employee_department=department)
        api_client.force_authenticate(user=auth_user)

        url = reverse("employees-get-department-by-jobcode", kwargs={"employee_jobcode": "EMP001"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["department_code"] == "DTEST"

    def test_nonexistent_employee_returns_404(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)

        url = reverse("employees-get-department-by-jobcode", kwargs={"employee_jobcode": "NO_SUCH"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_employee_without_department_returns_404(self, api_client, auth_user):
        Employee.objects.create(employee_jobcode="EMP001", employee_name="员工", employee_department=None)
        api_client.force_authenticate(user=auth_user)

        url = reverse("employees-get-department-by-jobcode", kwargs={"employee_jobcode": "EMP001"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestGetEmployeePermissions:
    def test_self_returns_view_only_permissions(self, api_client, auth_user):
        """无部门员工:最严兜底,仅返回查看(read)权限(新裁决 2026-08-14)"""
        Employee.objects.create(employee_jobcode="EMP001", employee_name="员工")
        api_client.force_authenticate(user=auth_user)

        url = reverse("employees-get-employee-permissions", kwargs={"employee_jobcode": "EMP001"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        read_codes = set(
            Permission.objects.filter(action="read", is_deleted=False).values_list(
                "permission_code", flat=True
            )
        )
        assert read_codes
        assert set(response.data["data"]["permissions"]) == read_codes

    def test_other_employee_forbidden_for_normal_user(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)

        url = reverse("employees-get-employee-permissions", kwargs={"employee_jobcode": "OTHER"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_superuser_other_returns_200(self, api_client, db):
        superuser = AuthUser.objects.create_superuser(
            auth_username="ADMIN001", password="testpass123", auth_phone="13800138001"
        )
        Employee.objects.create(employee_jobcode="OTHER", employee_name="他人")
        api_client.force_authenticate(user=superuser)

        url = reverse("employees-get-employee-permissions", kwargs={"employee_jobcode": "OTHER"})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
