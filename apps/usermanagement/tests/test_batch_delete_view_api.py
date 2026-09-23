"""
员工/部门批量删除端点(employees-batch-delete / departments-batch-delete)行为测试

【CT-4 回归锚,2026-09-23 补】锁定 A-32 BatchDeleteViewMixin 收敛后的端点级接线:
成功路径、空 ids noop、非 system_admin 权限门禁。
Service 层细节(失败结构/内部错误)已由 test_service_coverage / test_department_service 覆盖,
此处仅锁定"视图→Mixin→Service"接线层,防止各端差异挂载回归。
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


_phone_seq = 0


def _phone():
    global _phone_seq
    _phone_seq += 1
    return f"138{_phone_seq:08d}"


def _make_user(username, role, department=None):
    global _phone_seq
    _phone_seq += 1
    user = AuthUser.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_phone=f"137{_phone_seq:08d}",
    )
    if role:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
            employee_phone=_phone(),
        )
    return user


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def dept(db):
    return Department.objects.create(department_code="BDV_DEPT", department_name="批量删除视图部门")


@pytest.fixture
def sys_admin(db, dept):
    api_client = APIClient()
    api_client.force_authenticate(user=_make_user("bdv_sys", EmployeeRole.SYSTEM_ADMIN))
    return api_client


@pytest.fixture
def regular_client(db, dept):
    api_client = APIClient()
    api_client.force_authenticate(user=_make_user("bdv_ru", EmployeeRole.REGULAR_USER, department=dept))
    return api_client


@pytest.fixture
def leaf_dept(db, dept):
    return Department.objects.create(
        department_code="BDV_LEAF",
        department_name="待删叶部门",
        parent=dept,
        level=1,
        path=f"{dept.path}/BDV_LEAF",
    )


@pytest.mark.django_db
class TestEmployeeBatchDeleteView:
    def test_batch_delete_success(self, sys_admin, dept):
        Employee.objects.create(
            employee_jobcode="BDV001",
            employee_name="待删员工",
            employee_department=dept,
            employee_phone=_phone(),
        )

        resp = sys_admin.post(
            reverse("employees-batch-delete"), {"ids": ["BDV001"]}, format="json"
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        data = resp.data["data"]
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert data["fail_count"] == 0
        assert data["success_ids"] == ["BDV001"]
        assert data["fail_items"] == []
        employee = Employee.all_objects.get(employee_jobcode="BDV001")
        assert employee.is_deleted is True

    def test_batch_delete_empty_ids_noop(self, sys_admin):
        resp = sys_admin.post(reverse("employees-batch-delete"), {"ids": []}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        data = resp.data["data"]
        assert data["total"] == 0
        assert data["success_count"] == 0
        assert data["fail_count"] == 0

    def test_batch_delete_denied_for_regular_user(self, regular_client, dept):
        Employee.objects.create(
            employee_jobcode="BDV002",
            employee_name="普通员工删除目标",
            employee_department=dept,
            employee_phone=_phone(),
        )

        resp = regular_client.post(
            reverse("employees-batch-delete"), {"ids": ["BDV002"]}, format="json"
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestDepartmentBatchDeleteView:
    def test_batch_delete_success(self, sys_admin, leaf_dept):
        resp = sys_admin.post(
            reverse("departments-batch-delete"),
            {"ids": [leaf_dept.department_code]},
            format="json",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        data = resp.data["data"]
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert data["fail_count"] == 0
        assert data["success_ids"] == [leaf_dept.department_code]
        assert data["fail_items"] == []
        assert Department.objects.filter(department_code="BDV_LEAF").count() == 0

    def test_batch_delete_empty_ids_noop(self, sys_admin):
        resp = sys_admin.post(reverse("departments-batch-delete"), {"ids": []}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        data = resp.data["data"]
        assert data["total"] == 0
        assert data["success_count"] == 0
        assert data["fail_count"] == 0

    def test_batch_delete_denied_for_regular_user(self, regular_client, leaf_dept):
        resp = regular_client.post(
            reverse("departments-batch-delete"),
            {"ids": [leaf_dept.department_code]},
            format="json",
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
