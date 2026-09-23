"""
资产导出 RBAC 回归测试（矩阵 :148 / export 权限旁路修复）

锚定 ExportExcelMixin.export_excel 经 get_permissions 解析后的角色矩阵:
- regular_user → 403（矩阵 :148 regular ❌）
- auditor / asset_admin / dept_manager / system_admin → 200
- 未登录 → 401
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
class TestExportExcelRBAC:
    """assets-export 角色矩阵:regular 403,四角色 200,未登录 401"""

    def test_export_denied_for_regular_user(
        self, api_client: APIClient, department: Any, asset: Any
    ) -> None:
        """regular_user 导出资产 → 403（矩阵 :148 regular ❌）"""
        user = _make_role_user("ex_ru", "regular_user", department, "13800000401")
        api_client.force_authenticate(user=user)
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_export_allowed_for_auditor(self, api_client: APIClient, department: Any, asset: Any) -> None:
        """auditor 导出资产 → 200（矩阵 :148 auditor ✅ 全部）"""
        user = _make_role_user("ex_au", "auditor", department, "13800000402")
        api_client.force_authenticate(user=user)
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code == status.HTTP_200_OK

    def test_export_allowed_for_asset_admin(
        self, api_client: APIClient, department: Any, asset: Any
    ) -> None:
        """asset_admin 导出资产 → 200（矩阵 :148 asset_admin ✅ 本部门）"""
        user = _make_role_user("ex_aa", "asset_admin", department, "13800000403")
        api_client.force_authenticate(user=user)
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code == status.HTTP_200_OK

    def test_export_allowed_for_dept_manager(
        self, api_client: APIClient, department: Any, asset: Any
    ) -> None:
        """dept_manager 导出资产 → 200（矩阵 :148 dept_manager ✅ 本部门+下级）"""
        user = _make_role_user("ex_dm", "dept_manager", department, "13800000404")
        api_client.force_authenticate(user=user)
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code == status.HTTP_200_OK

    def test_export_allowed_for_system_admin(
        self, api_client: APIClient, admin_auth_user: Any, asset: Any
    ) -> None:
        """system_admin 导出资产 → 200（矩阵 :148 system ✅ 全部）"""
        api_client.force_authenticate(user=admin_auth_user)
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code == status.HTTP_200_OK

    def test_export_denied_for_anonymous(self, api_client: APIClient, asset: Any) -> None:
        """未登录导出资产 → 401"""
        resp = api_client.get(reverse("assets-export-excel"))
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_export_denied_for_regular_on_damaged(
        self, api_client: APIClient, department: Any, damaged_asset: Any
    ) -> None:
        """regular_user 导出待报废 → 403（MRO: 损坏视图集同样走公共解析）"""
        user = _make_role_user("ex_ru2", "regular_user", department, "13800000405")
        api_client.force_authenticate(user=user)
        resp = api_client.get(reverse("damaged-assets-export-excel"))
        assert resp.status_code == status.HTTP_403_FORBIDDEN
