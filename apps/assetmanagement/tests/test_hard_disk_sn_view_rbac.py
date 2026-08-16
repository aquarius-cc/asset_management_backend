"""
硬盘序列号读操作 RBAC 回归测试

锚定 search_by_serial_number / by-asset 端点行级数据隔离:
- 部门内员工只能查询本部门资产的硬盘
- 越部门/不存在 → 404,不泄露存在性
- 无限制用户(superuser / 无 Employee)全量可见
"""

from typing import Any, cast

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetType, HardDiskSN, Storage
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee


def _make_dept(code: str, name: str) -> Department:
    return Department.objects.create(department_code=code, department_name=name)


def _make_employee(dept: Department, jobcode: str, name: str) -> Employee:
    phone = f"13{abs(sum(map(ord, jobcode))) % 100000000:08d}"
    return Employee.objects.create(
        employee_jobcode=jobcode, employee_name=name, employee_department=dept, employee_phone=phone
    )


def _make_asset(storage: Storage, asset_type: AssetType, manager: Employee, code: str) -> Asset:
    return Asset.objects.create(
        asset_code=code,
        asset_name=f"资产-{code}",
        asset_purchase_price=1000.0,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_store",
        asset_manager_recordcode=manager,
    )


@pytest.mark.django_db
class TestHardDiskSNReadScope:
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
            AuthUser, AuthUser.objects.create_user(auth_username="EMP-RB-A", password="p", auth_phone="13800000001")
        )

    @pytest.fixture
    def user_b(self, db: Any, emp_b: Employee) -> AuthUser:
        return cast(
            AuthUser, AuthUser.objects.create_user(auth_username="EMP-RB-B", password="p", auth_phone="13800000002")
        )

    @pytest.fixture
    def asset_a(self, db: Any, storage: Storage, asset_type: AssetType, emp_a: Employee) -> Asset:
        return _make_asset(storage, asset_type, emp_a, "A-RB-001")

    @pytest.fixture
    def asset_b(self, db: Any, storage: Storage, asset_type: AssetType, emp_b: Employee) -> Asset:
        return _make_asset(storage, asset_type, emp_b, "A-RB-002")

    @pytest.fixture
    def disk_a(self, db: Any, asset_a: Asset) -> HardDiskSN:
        return HardDiskSN.objects.create(
            asset_recordcode=asset_a, harddisk_sn_code="SN-RB-A1", harddisk_type="SSD"
        )

    @pytest.fixture
    def disk_b(self, db: Any, asset_b: Asset) -> HardDiskSN:
        return HardDiskSN.objects.create(
            asset_recordcode=asset_b, harddisk_sn_code="SN-RB-B1", harddisk_type="SSD"
        )

    def test_search_in_scope(self, api_client: APIClient, user_a: AuthUser, disk_a: HardDiskSN) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.post(
            "/api/v1/assets/harddisk-sn/search_by_serial_number/",
            {"harddisk_sn_code": "SN-RB-A1"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        assert resp.data["data"]["harddisk_sn_code"] == "SN-RB-A1"

    def test_search_out_of_scope_404(self, api_client: APIClient, user_a: AuthUser, disk_b: HardDiskSN) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.post(
            "/api/v1/assets/harddisk-sn/search_by_serial_number/",
            {"harddisk_sn_code": "SN-RB-B1"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_search_nonexistent_404(self, api_client: APIClient, user_a: AuthUser) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.post(
            "/api/v1/assets/harddisk-sn/search_by_serial_number/",
            {"harddisk_sn_code": "SN-NOPE"},
            format="json",
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_by_asset_in_scope(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        HardDiskSN.objects.create(asset_recordcode=asset_a, harddisk_sn_code="SN-RB-A1", harddisk_type="SSD")
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/harddisk-sn/by-asset/{asset_a.asset_code}/")
        assert resp.status_code == status.HTTP_200_OK
        codes = [item["harddisk_sn_code"] for item in resp.data["data"]["results"]]
        assert codes == ["SN-RB-A1"]

    def test_by_asset_out_of_scope_404(self, api_client: APIClient, user_a: AuthUser, asset_b: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/harddisk-sn/by-asset/{asset_b.asset_code}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_by_asset_nonexistent_asset_404(self, api_client: APIClient, user_a: AuthUser) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get("/api/v1/assets/harddisk-sn/by-asset/NO-SUCH-ASSET/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_by_asset_in_scope_no_disks_empty(self, api_client: APIClient, user_a: AuthUser, asset_a: Asset) -> None:
        api_client.force_authenticate(user=user_a)
        resp = api_client.get(f"/api/v1/assets/harddisk-sn/by-asset/{asset_a.asset_code}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["count"] == 0
        assert resp.data["data"]["results"] == []

    def test_unrestricted_user_sees_all(self, api_client: APIClient, auth_user: AuthUser, disk_b: HardDiskSN) -> None:
        api_client.force_authenticate(user=auth_user)
        resp = api_client.post(
            "/api/v1/assets/harddisk-sn/search_by_serial_number/",
            {"harddisk_sn_code": "SN-RB-B1"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_superuser_sees_all(self, api_client: APIClient, admin_auth_user: AuthUser, disk_b: HardDiskSN) -> None:
        api_client.force_authenticate(user=admin_auth_user)
        resp = api_client.get("/api/v1/assets/harddisk-sn/by-asset/A-RB-002/")
        assert resp.status_code == status.HTTP_200_OK
