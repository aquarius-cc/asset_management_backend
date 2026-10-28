"""
R-1 行级隔离收口回归测试(M-RC-01/03/04 + reissue + batch_delete)

跨部门越权写入口收口:
- hard_disk PATCH/DELETE 经 get_object() 走部门作用域 → 跨部门 404
- recycle PATCH / reissue 同上
- hard_disk create 对 asset_recordcode 做可见性校验 → 跨部门 400 + ASSET_NOT_FOUND
- recycle batch_delete service 对跨部门不可见记录按不存在处理 → fail_count=1

部门内正对照组用于防止"整体 404/400"掩盖权限配置错误。
"""

from typing import Any, cast

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse

from apps.assetmanagement.models import Asset, AssetType, HardDiskSN, OutAsset, RecycleAsset, Storage
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee


def _make_dept(code: str, name: str) -> Department:
    return Department.objects.create(department_code=code, department_name=name)


def _make_employee(dept: Department, jobcode: str, name: str, role: str = "asset_admin") -> Employee:
    phone = f"13{abs(sum(map(ord, jobcode))) % 100000000:08d}"
    return Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=name,
        employee_department=dept,
        employee_phone=phone,
        role=role,
    )


def _make_auth_user(jobcode: str, phone: str) -> AuthUser:
    return cast(AuthUser, AuthUser.objects.create_user(auth_username=jobcode, password="p", auth_phone=phone))


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
class TestRowLevelIsolationWriteScope:
    """R-1: 跨部门写操作收口(M-RC-01/03/04 + reissue + batch_delete)"""

    @pytest.fixture
    def dept_a(self, db: Any) -> Department:
        return _make_dept("D-RI-A", "隔离部门A")

    @pytest.fixture
    def dept_b(self, db: Any) -> Department:
        return _make_dept("D-RI-B", "隔离部门B")

    @pytest.fixture
    def admin_a(self, db: Any, dept_a: Department) -> AuthUser:
        """部门A的 asset_admin:可写本部门,跨部门数据不可见"""
        _make_employee(dept_a, "EMP-RI-A", "甲", role="asset_admin")
        return _make_auth_user("EMP-RI-A", "13800002101")

    @pytest.fixture
    def emp_b(self, db: Any, dept_b: Department) -> Employee:
        return _make_employee(dept_b, "EMP-RI-B", "乙", role="asset_admin")

    @pytest.fixture
    def asset_a(self, db: Any, storage: Storage, asset_type: AssetType, admin_a: AuthUser, dept_a: Department) -> Asset:
        manager = Employee.objects.get(employee_jobcode="EMP-RI-A")
        return _make_asset(storage, asset_type, manager, "A-RI-001")

    @pytest.fixture
    def asset_b(self, db: Any, storage: Storage, asset_type: AssetType, emp_b: Employee) -> Asset:
        return _make_asset(storage, asset_type, emp_b, "A-RI-002")

    @pytest.fixture
    def disk_a(self, db: Any, asset_a: Asset) -> HardDiskSN:
        return HardDiskSN.objects.create(asset_recordcode=asset_a, harddisk_sn_code="SN-RI-A1", harddisk_type="SSD")

    @pytest.fixture
    def disk_b(self, db: Any, asset_b: Asset) -> HardDiskSN:
        return HardDiskSN.objects.create(asset_recordcode=asset_b, harddisk_sn_code="SN-RI-B1", harddisk_type="SSD")

    @pytest.fixture
    def outasset_b(self, db: Any, asset_b: Asset) -> OutAsset:
        return OutAsset.objects.create(asset_recordcode=asset_b, outasset_date="2024-01-01")

    @pytest.fixture
    def recycle_b(self, db: Any, asset_b: Asset, outasset_b: OutAsset, emp_b: Employee) -> RecycleAsset:
        return RecycleAsset.objects.create(
            asset_recordcode=asset_b,
            outasset_recordcode=outasset_b,
            recycle_asset_date="2024-02-01",
            operator_employee=emp_b,
        )

    # ---------- M-RC-01: hard_disk PATCH/DELETE 跨部门 404 ----------

    def test_hard_disk_cross_dept_patch_404(
        self, api_client: APIClient, admin_a: AuthUser, disk_b: HardDiskSN
    ) -> None:
        api_client.force_authenticate(user=admin_a)
        url = reverse("harddisk-sn-detail", kwargs={"recordcode": disk_b.recordcode})
        resp = api_client.patch(url, {"harddisk_description": "越权"}, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        disk_b.refresh_from_db()
        assert disk_b.harddisk_description != "越权"

    def test_hard_disk_cross_dept_delete_404(
        self, api_client: APIClient, admin_a: AuthUser, disk_b: HardDiskSN
    ) -> None:
        api_client.force_authenticate(user=admin_a)
        url = reverse("harddisk-sn-detail", kwargs={"recordcode": disk_b.recordcode})
        resp = api_client.delete(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert HardDiskSN.objects.filter(recordcode=disk_b.recordcode).exists()

    def test_hard_disk_in_scope_patch_ok(
        self, api_client: APIClient, admin_a: AuthUser, disk_a: HardDiskSN
    ) -> None:
        """正对照:部门内 PATCH 正常,防止整体 404 掩盖权限问题"""
        api_client.force_authenticate(user=admin_a)
        url = reverse("harddisk-sn-detail", kwargs={"recordcode": disk_a.recordcode})
        resp = api_client.patch(url, {"harddisk_description": "部门内更新"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        disk_a.refresh_from_db()
        assert disk_a.harddisk_description == "部门内更新"

    # ---------- M-RC-03: recycle PATCH 跨部门 404 ----------

    def test_recycle_cross_dept_patch_404(
        self, api_client: APIClient, admin_a: AuthUser, recycle_b: RecycleAsset
    ) -> None:
        api_client.force_authenticate(user=admin_a)
        url = reverse("recycle-assets-detail", kwargs={"recordcode": recycle_b.recordcode})
        resp = api_client.patch(url, {"recycle_asset_description": "越权"}, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    # ---------- reissue: 跨部门 404 ----------

    def test_recycle_cross_dept_reissue_404(
        self, api_client: APIClient, admin_a: AuthUser, recycle_b: RecycleAsset
    ) -> None:
        api_client.force_authenticate(user=admin_a)
        url = reverse("recycle-assets-reissue", kwargs={"recordcode": recycle_b.recordcode})
        resp = api_client.post(url, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    # ---------- M-RC-04: hard_disk create 跨部门资产 → 400 ASSET_NOT_FOUND ----------

    def test_hard_disk_create_cross_dept_asset_400(
        self, api_client: APIClient, admin_a: AuthUser, asset_b: Asset
    ) -> None:
        api_client.force_authenticate(user=admin_a)
        resp = api_client.post(
            reverse("harddisk-sn-list"),
            {
                "asset_recordcode": asset_b.recordcode,
                "harddisk_sn_code": "SN-RI-NEW1",
                "harddisk_type": "SSD",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "ASSET_NOT_FOUND" in str(resp.data)
        assert not HardDiskSN.objects.filter(harddisk_sn_code="SN-RI-NEW1").exists()

    def test_hard_disk_create_in_scope_ok(
        self, api_client: APIClient, admin_a: AuthUser, asset_a: Asset
    ) -> None:
        """正对照:部门内创建正常"""
        api_client.force_authenticate(user=admin_a)
        resp = api_client.post(
            reverse("harddisk-sn-list"),
            {
                "asset_recordcode": asset_a.recordcode,
                "harddisk_sn_code": "SN-RI-NEW2",
                "harddisk_type": "SSD",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert HardDiskSN.objects.filter(harddisk_sn_code="SN-RI-NEW2").exists()

    # ---------- batch_delete: service 层跨部门拒绝 ----------

    def test_recycle_batch_delete_cross_dept_rejected(
        self, db: Any, admin_a: AuthUser, recycle_b: RecycleAsset
    ) -> None:
        from apps.assetmanagement.services import RecycleAssetService

        result = RecycleAssetService.batch_delete_recycle_asset(
            [recycle_b.recordcode], user=admin_a
        )
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
        assert RecycleAsset.objects.filter(recordcode=recycle_b.recordcode).exists()
