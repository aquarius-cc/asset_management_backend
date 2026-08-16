"""
资产读操作 RBAC 回归测试

锚定 AssetViewSet 非 list 动作行级数据隔离(get_queryset 收权 + 自定义动作 _scoped):
- retrieve / getassetbyname / getassetbyrecordcode / combine_search / search
- search_available / statistics / combined_details / contract_by_asset
- 写动作 get_object 预检:update / destroy / change_outasset_employee
"""

from typing import Any, cast

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee


def _make_dept(code: str, name: str) -> Department:
    return Department.objects.create(department_code=code, department_name=name)


def _make_employee(dept: Department, jobcode: str, name: str) -> Employee:
    phone = f"13{abs(sum(map(ord, jobcode))) % 100000000:08d}"
    return Employee.objects.create(
        employee_jobcode=jobcode, employee_name=name, employee_department=dept, employee_phone=phone
    )


def _make_asset(
    storage: Storage,
    asset_type: AssetType,
    manager: Employee,
    code: str,
    name: str,
    contract: Contract | None = None,
) -> Asset:
    return Asset.objects.create(
        asset_code=code,
        asset_name=name,
        asset_purchase_price=1000.0,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_contract_recordcode=contract,
        asset_current_status="in_store",
        asset_manager_recordcode=manager,
    )


def _codes(payload: dict) -> list[str]:
    return [item["asset_code"] for item in payload["results"]]


@pytest.mark.django_db
class TestAssetViewReadScope:
    @pytest.fixture
    def dept_a(self, db: Any) -> Department:
        return _make_dept("D-RB-A", "部门A")

    @pytest.fixture
    def dept_b(self, db: Any) -> Department:
        return _make_dept("D-RB-B", "部门B")

    @pytest.fixture
    def emp_a(self, db: Any, dept_a: Department) -> Employee:
        return _make_employee(dept_a, "EMP-RB-A", "甲")

    @pytest.fixture
    def emp_b(self, db: Any, dept_b: Department) -> Employee:
        return _make_employee(dept_b, "EMP-RB-B", "乙")

    @pytest.fixture
    def user_a(self, db: Any, emp_a: Employee) -> AuthUser:
        return cast(
            AuthUser, AuthUser.objects.create_user(auth_username="EMP-RB-A", password="p", auth_phone="13800000011")
        )

    @pytest.fixture
    def asset_a(self, db: Any, storage: Storage, asset_type: AssetType, emp_a: Employee, contract: Contract) -> Asset:
        return _make_asset(storage, asset_type, emp_a, "A-RB-001", "RB-ASSET-A", contract=contract)

    @pytest.fixture
    def asset_b(self, db: Any, storage: Storage, asset_type: AssetType, emp_b: Employee) -> Asset:
        return _make_asset(storage, asset_type, emp_b, "A-RB-002", "RB-ASSET-B")

    def test_retrieve_in_scope(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/{asset_a.recordcode}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["asset_code"] == "A-RB-001"

    def test_retrieve_out_of_scope_404(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/{asset_b.recordcode}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_getassetbyname_scoped(
        self, api_client: APIClient, user_a: AuthUser, asset_a: Asset, asset_b: Asset
    ) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/assets/getassetbyname/RB-ASSET/")
        assert resp.status_code == status.HTTP_200_OK
        assert _codes(resp.data["data"]) == ["A-RB-001"]

    def test_getassetbyrecordcode_scoped(
        self, api_client: APIClient, user_a: AuthUser, asset_a: Asset, asset_b: Asset
    ) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/getassetbyrecordcode/x/?recordcode={asset_b.recordcode}")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"] == []

    def test_combine_search_scoped(
        self, api_client: APIClient, user_a: AuthUser, asset_a: Asset, asset_b: Asset
    ) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/assets/combine_search/?asset_name=RB-ASSET")
        assert resp.status_code == status.HTTP_200_OK
        assert _codes(resp.data["data"]) == ["A-RB-001"]

    def test_search_scoped(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset, asset_b: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/assets/search/?keyword=RB-ASSET")
        assert resp.status_code == status.HTTP_200_OK
        assert _codes(resp.data["data"]) == ["A-RB-001"]

    def test_search_available_scoped(
        self, api_client: APIClient, user_a: AuthUser, asset_a: Asset, asset_b: Asset
    ) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/assets/search_available/?asset_name=RB-ASSET")
        assert resp.status_code == status.HTTP_200_OK
        assert _codes(resp.data["data"]) == ["A-RB-001"]

    def test_statistics_scoped(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/assets/statistics/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["total_count"] == 1

    def test_combined_details_in_scope(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/combined_details/?asset_code={asset_a.asset_code}")
        assert resp.status_code == status.HTTP_200_OK

    def test_combined_details_out_of_scope_404(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/combined_details/?asset_code={asset_b.asset_code}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_contract_by_asset_in_scope(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/contract_by_asset/{asset_a.asset_code}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["contract_code"] == "C001"

    def test_contract_by_asset_out_of_scope_404(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/assets/contract_by_asset/{asset_b.asset_code}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_update_by_regular_user_denied(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        """写动作仅系统管理员可执行,普通用户(即使有部门范围)一律拒绝"""
        api_client.force_authenticate(user=user_a)
        resp = api_client.patch(f"/api/v1/assets/assets/{asset_b.recordcode}/", {"asset_name": "越权修改"}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_destroy_by_regular_user_denied(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        """写动作仅系统管理员可执行,普通用户(即使有部门范围)一律拒绝"""
        api_client.force_authenticate(user=user_a)
        resp = api_client.delete(f"/api/v1/assets/assets/{asset_b.recordcode}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unrestricted_user_sees_all(self, api_client: APIClient, auth_user: AuthUser, asset_b: Asset) -> None:
        api_client.force_authenticate(user=auth_user)
        resp = api_client.get(f"/api/v1/assets/assets/{asset_b.recordcode}/")
        assert resp.status_code == status.HTTP_200_OK
