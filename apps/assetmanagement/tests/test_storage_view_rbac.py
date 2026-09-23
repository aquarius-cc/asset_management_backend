"""
仓库 ViewSet RBAC 回归测试(F-P1-2 / F-P2-5)

锚定 StorageViewSet 批量写权限:
- regular_user / dept_manager → batch-create / batch-delete 403(矩阵 :144 仅 system_admin)
- system_admin → 双端点 200
"""

from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def _make_role_user(jobcode: str, role: str, department: Any, phone: str) -> Any:
    from apps.authusermanagement.models import AuthUser
    from apps.usermanagement.models import Employee
    from core.tests import TEST_PASSWORD

    AuthUser.objects.create_user(auth_username=jobcode, password=TEST_PASSWORD, auth_phone=phone[:-1] + "1")
    Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=jobcode,
        employee_department=department,
        role=role,
        employee_phone=phone,
    )
    return AuthUser.objects.get(auth_username=jobcode)


@pytest.mark.django_db
class TestStorageBatchRBAC:
    """仓库批量写权限矩阵:regular/dept_manager 403,system_admin 200"""

    def test_batch_create_denied_for_regular_user(self, api_client: APIClient, department: Any) -> None:
        """regular_user 批量建仓 → 403(矩阵 :144 regular ❌)"""
        user = _make_role_user("st_ru", "regular_user", department, "13800000301")
        api_client.force_authenticate(user=user)
        url = reverse("storages-batch-create")
        resp = api_client.post(
            url,
            {
                "items": [
                    {
                        "storage_code": "ST-RU-1",
                        "storage_name": "越权仓库",
                        "storage_address": "地址",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_delete_denied_for_regular_user(self, api_client: APIClient, department: Any) -> None:
        """regular_user 批量删仓 → 403(矩阵 :144 regular ❌)"""
        user = _make_role_user("st_ru2", "regular_user", department, "13800000302")
        api_client.force_authenticate(user=user)
        url = reverse("storages-batch-delete")
        resp = api_client.post(url, {"ids": ["ST-ANY"]}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_create_denied_for_dept_manager(self, api_client: APIClient, department: Any) -> None:
        """dept_manager 批量建仓 → 403(矩阵 :144 仓库仅 system_admin)"""
        user = _make_role_user("st_dm", "dept_manager", department, "13800000303")
        api_client.force_authenticate(user=user)
        url = reverse("storages-batch-create")
        resp = api_client.post(
            url,
            {
                "items": [
                    {
                        "storage_code": "ST-DM-1",
                        "storage_name": "经理仓库",
                        "storage_address": "地址",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_create_allowed_for_system_admin(self, api_client: APIClient, admin_auth_user: Any) -> None:
        """system_admin 批量建仓 → 200(batch_create 走 success_response 默认 200)"""
        api_client.force_authenticate(user=admin_auth_user)
        url = reverse("storages-batch-create")
        resp = api_client.post(
            url,
            {
                "items": [
                    {
                        "storage_code": "ST-SA-1",
                        "storage_name": "管理员仓库",
                        "storage_address": "地址",
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        assert resp.data["data"]["success_count"] == 1

    def test_batch_delete_allowed_for_system_admin(
        self, api_client: APIClient, admin_auth_user: Any, storage: Any
    ) -> None:
        """system_admin 批量删仓 → 200"""
        api_client.force_authenticate(user=admin_auth_user)
        url = reverse("storages-batch-delete")
        resp = api_client.post(url, {"ids": [storage.storage_code]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        assert resp.data["data"]["success_count"] == 1
