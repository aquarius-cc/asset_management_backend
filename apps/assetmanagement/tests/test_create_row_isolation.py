"""
报废/损坏/遗失创建入口行级隔离回归测试(BEQ-02 / SC-4)

验证创建侧与查询侧(by_asset)同口径:
- 跨部门用户对不可见资产提交报废/损坏/遗失申请 → 400/404 语义(AppValidationError ASSET_NOT_VISIBLE)
- 本部门资产正常创建(防误伤)
- superuser 无限制
"""

from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def _create_scoped_auth(jobcode: str, name: str, dept: Any, role: str, phone: str) -> Any:
    """创建与 Employee 关联的认证用户(与 test_dashboard_view_api 同款)"""
    from apps.authusermanagement.models import AuthUser
    from apps.usermanagement.models import Employee
    from core.tests import TEST_PASSWORD

    AuthUser.objects.create_user(auth_username=jobcode, password=TEST_PASSWORD, auth_phone=phone[:-1] + "1")
    Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=name,
        employee_department=dept,
        role=role,
        employee_phone=phone,
    )
    return AuthUser.objects.get(auth_username=jobcode)


@pytest.fixture
def api_client() -> APIClient:
    from rest_framework.test import APIClient as _APIClient

    return _APIClient()


@pytest.fixture
def department_b(db: Any) -> Any:
    from apps.usermanagement.models import Department

    return Department.objects.create(department_code="D002", department_name="乙部门")


@pytest.fixture
def dept_b_asset(db: Any, storage: Any, asset_type: Any, department_b: Any) -> Any:
    """乙部门(D002)资产 A002(应被甲部门用户隔离)"""
    from apps.assetmanagement.models import Asset
    from apps.usermanagement.models import Employee

    emp_b = Employee.objects.create(
        employee_jobcode="USR_B",
        employee_name="乙部门员工",
        employee_department=department_b,
        employee_phone="13800131881",
    )
    return Asset.objects.create(
        asset_code="A002",
        asset_name="乙部门资产",
        asset_purchase_price=500.00,
        asset_purchase_date="2024-02-01",
        asset_entry_date="2024-02-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_store",
        asset_manager_recordcode=emp_b,
    )


@pytest.fixture
def owned_asset(db: Any, asset: Any, user: Any) -> Any:
    """甲部门(D001)资产 A001:补 manager 归属"""
    asset.asset_manager_recordcode = user
    asset.save(update_fields=["asset_manager_recordcode"])
    return asset


@pytest.fixture
def owned_asset_recyclable(db: Any, asset: Any, user: Any) -> Any:
    """甲部门(D001)资产 A001,状态 recycled_pending(FSM 允许 to_damaged 的入边)"""
    asset.asset_manager_recordcode = user
    asset.asset_current_status = "recycled_pending"
    asset.save(update_fields=["asset_manager_recordcode", "asset_current_status"])
    return asset


@pytest.fixture
def dept_b_asset_recyclable(db: Any, dept_b_asset: Any) -> Any:
    """乙部门资产 A002,状态 recycled_pending(FSM 允许 to_damaged 的入边)"""
    dept_b_asset.asset_current_status = "recycled_pending"
    dept_b_asset.save(update_fields=["asset_current_status"])
    return dept_b_asset


@pytest.fixture
def regular_a_user(db: Any, department: Any) -> Any:
    return _create_scoped_auth("REGA", "甲部门员工", department, "regular_user", "13800131902")


@pytest.fixture
def dept_manager_a_user(db: Any, department: Any) -> Any:
    """甲部门经理:单条 create 已收紧至 IsDeptManagerOrAbove(规则 :142 / BF-037)"""
    return _create_scoped_auth("DMAA", "甲部门经理", department, "dept_manager", "13800131903")


@pytest.fixture
def admin_auth_user(db: Any) -> Any:
    from apps.authusermanagement.models import AuthUser
    from core.tests import TEST_PASSWORD

    return AuthUser.objects.create_superuser(
        auth_username="adminuser", password=TEST_PASSWORD, auth_phone="13800138001"
    )


@pytest.mark.django_db
class TestDamagedCreateRowIsolation:
    """报废申请创建行级隔离"""

    def url(self) -> str:
        return reverse("damaged-assets-list")

    def test_cross_dept_create_rejected(
        self, api_client: APIClient, dept_b_asset_recyclable: Any, dept_manager_a_user: Any
    ) -> None:
        """甲部门 dept_manager 对乙部门资产提交报废申请 → 400/404(行级隔离层,非 403)"""
        api_client.force_authenticate(user=dept_manager_a_user)
        response = api_client.post(
            self.url(),
            {"asset_recordcode": dept_b_asset_recyclable.recordcode, "damaged_asset_description": "测试报废"},
            format="json",
        )
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND)

    def test_own_dept_create_allowed(
        self, api_client: APIClient, owned_asset_recyclable: Any, dept_manager_a_user: Any
    ) -> None:
        """本部门 dept_manager 正常提交报废申请(防误伤)"""
        api_client.force_authenticate(user=dept_manager_a_user)
        response = api_client.post(
            self.url(),
            {"asset_recordcode": owned_asset_recyclable.recordcode, "damaged_asset_description": "测试报废"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_regular_create_denied(
        self, api_client: APIClient, owned_asset_recyclable: Any, regular_a_user: Any
    ) -> None:
        """regular 单条 create → 403(规则 :142 / BF-037 收紧锚)"""
        api_client.force_authenticate(user=regular_a_user)
        response = api_client.post(
            self.url(),
            {"asset_recordcode": owned_asset_recyclable.recordcode, "damaged_asset_description": "测试报废"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cross_dept_allowed(
        self, api_client: APIClient, dept_b_asset_recyclable: Any, admin_auth_user: Any
    ) -> None:
        """superuser 无限制"""
        api_client.force_authenticate(user=admin_auth_user)
        response = api_client.post(
            self.url(),
            {"asset_recordcode": dept_b_asset_recyclable.recordcode, "damaged_asset_description": "测试报废"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestLifecycleBatchCreateRowIsolation:
    """损坏/遗失批量创建:角色权限(F-P1-8)+ 行级隔离(矩阵 :141 regular ❌)"""

    @pytest.fixture
    def asset_admin_a_user(self, db: Any, department: Any) -> Any:
        return _create_scoped_auth("ASTA", "甲部门资产管理员", department, "asset_admin", "13800131905")

    @pytest.fixture
    def auditor_a_user(self, db: Any, department: Any) -> Any:
        return _create_scoped_auth("AUDA", "甲部门审计员", department, "auditor", "13800131906")

    def test_broken_batch_create_denied_for_regular(
        self, api_client: APIClient, owned_asset: Any, regular_a_user: Any
    ) -> None:
        """regular_user 批量标记损坏(本部门) → 403(矩阵 :141 regular ❌,F-P1-8)"""
        api_client.force_authenticate(user=regular_a_user)
        url = reverse("broken-assets-batch-create")
        response = api_client.post(
            url, {"items": [{"asset_code": "A001", "broken_reason": "测试损坏"}]}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lost_batch_create_denied_for_regular(
        self, api_client: APIClient, owned_asset: Any, regular_a_user: Any
    ) -> None:
        """regular_user 批量标记遗失(本部门) → 403(矩阵 :141 regular ❌,F-P1-8)"""
        api_client.force_authenticate(user=regular_a_user)
        url = reverse("lost-assets-batch-create")
        response = api_client.post(
            url,
            {"items": [{"asset_code": "A001", "lost_date": "2026-09-17", "lost_reason": "测试遗失"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_broken_batch_create_denied_for_auditor(
        self, api_client: APIClient, owned_asset: Any, auditor_a_user: Any
    ) -> None:
        """auditor 批量标记损坏 → 403(矩阵 :141 auditor ❌,F-P1-8)"""
        api_client.force_authenticate(user=auditor_a_user)
        url = reverse("broken-assets-batch-create")
        response = api_client.post(
            url, {"items": [{"asset_code": "A001", "broken_reason": "测试损坏"}]}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lost_batch_create_denied_for_auditor(
        self, api_client: APIClient, owned_asset: Any, auditor_a_user: Any
    ) -> None:
        """auditor 批量标记遗失 → 403(矩阵 :141 auditor ❌,F-P1-8)"""
        api_client.force_authenticate(user=auditor_a_user)
        url = reverse("lost-assets-batch-create")
        response = api_client.post(
            url,
            {"items": [{"asset_code": "A001", "lost_date": "2026-09-17", "lost_reason": "测试遗失"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_broken_cross_dept_rejected(
        self, api_client: APIClient, dept_b_asset: Any, asset_admin_a_user: Any
    ) -> None:
        """asset_admin 对乙部门资产批量标记损坏 → 记入 fail_items(行隔离层拒绝)"""
        api_client.force_authenticate(user=asset_admin_a_user)
        url = reverse("broken-assets-batch-create")
        response = api_client.post(
            url, {"items": [{"asset_code": "A002", "broken_reason": "测试损坏"}]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 0
        assert response.data["data"]["fail_count"] == 1

    def test_lost_cross_dept_rejected(
        self, api_client: APIClient, dept_b_asset: Any, asset_admin_a_user: Any
    ) -> None:
        """asset_admin 对乙部门资产批量标记遗失 → 记入 fail_items(行隔离层拒绝)"""
        api_client.force_authenticate(user=asset_admin_a_user)
        url = reverse("lost-assets-batch-create")
        response = api_client.post(
            url,
            {"items": [{"asset_code": "A002", "lost_date": "2026-09-17", "lost_reason": "测试遗失"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 0
        assert response.data["data"]["fail_count"] == 1

    def test_broken_own_dept_allowed_for_asset_admin(
        self, api_client: APIClient, owned_asset: Any, asset_admin_a_user: Any
    ) -> None:
        """asset_admin 对本部门资产批量标记损坏 → 200 success_count=1(矩阵 :141 asset_admin ✅)"""
        api_client.force_authenticate(user=asset_admin_a_user)
        url = reverse("broken-assets-batch-create")
        response = api_client.post(
            url, {"items": [{"asset_code": "A001", "broken_reason": "测试损坏"}]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 1

    def test_lost_own_dept_allowed_for_asset_admin(
        self, api_client: APIClient, owned_asset: Any, asset_admin_a_user: Any
    ) -> None:
        """asset_admin 对本部门资产批量标记遗失 → 200 success_count=1(矩阵 :141 asset_admin ✅)"""
        api_client.force_authenticate(user=asset_admin_a_user)
        url = reverse("lost-assets-batch-create")
        response = api_client.post(
            url,
            {"items": [{"asset_code": "A001", "lost_date": "2026-09-17", "lost_reason": "测试遗失"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 1
