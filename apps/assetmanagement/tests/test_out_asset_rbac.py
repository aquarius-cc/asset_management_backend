"""出库批量删除/单条删除行级隔离测试（BF-170 OP-02，P1 安全，不可回退）。

【锁定的不变量】
batch_delete_outasset / _delete_one 必须携带调用者身份（kw-only user 必填），
锁内逐条经 AssetSelector.ensure_asset_visible 校验（B14 + TOCTOU 模板）：

- 跨部门条目 → 进 fail_items（error_code=ASSET_NOT_VISIBLE），出库记录保留
- 同部门条目 → 正常删除并回退资产状态
- 混合批次 → 1 成 1 败（不整体拒绝、不越权删除）
- 单条 destroy / cancel 跨部门 → get_object()（scoped）404，不泄露存在性

与 asset/recycle/damaged/waste 四链同口径（DR-1）。
"""

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, OutAsset
from apps.assetmanagement.services.out_asset_service import OutAssetService
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db


def _phone_seq():
    n = 300
    while True:
        n += 1
        yield f"136{n:08d}"


_phones = _phone_seq()


def _make_manager(username: str, department: Department) -> AuthUser:
    """部门经理（AuthUser + Employee 同名关联）。"""
    user = AuthUser.objects.create_user(auth_username=username, password=TEST_PASSWORD, auth_phone=next(_phones))
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}经理",
        employee_department=department,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone=next(_phones),
    )
    return user


def _make_scoped_outasset(storage, asset_type, manager_user, code: str) -> OutAsset:
    """按 entry_person 归属部门的在用资产 + 其出库记录（status=in_use 才允许删除出库单）。"""
    entry_person = Employee.objects.get(employee_jobcode=manager_user.auth_username)
    asset = Asset.objects.create(
        recordcode=f"ASSET-ORB-{code}",
        asset_code=f"ORB-{code}",
        asset_name=f"出库隔离{code}",
        asset_purchase_price=1,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_entry_person_recordcode=entry_person,
        asset_current_status="in_use",
    )
    return OutAsset.objects.create(
        asset_recordcode=asset,
        outasset_date="2024-02-01",
        outasset_previous_status="in_store",
    )


@pytest.fixture
def dept_a():
    return Department.objects.create(department_code="DEPT-ORB-A", department_name="甲部门", path="/DEPT-ORB-A")


@pytest.fixture
def dept_b():
    return Department.objects.create(department_code="DEPT-ORB-B", department_name="乙部门", path="/DEPT-ORB-B")


@pytest.fixture
def manager_a(dept_a):
    return _make_manager("MGR-ORB-A", dept_a)


@pytest.fixture
def manager_b(dept_b):
    return _make_manager("MGR-ORB-B", dept_b)


class TestOutAssetBatchDeleteRBAC:
    def test_cross_department_batch_all_fail(self, storage, asset_type, manager_a, manager_b):
        """甲经理批量删乙部门编码：全部进 fail_items（ASSET_NOT_VISIBLE），出库记录保留。"""
        out_b = _make_scoped_outasset(storage, asset_type, manager_b, "B01")

        result = OutAssetService.batch_delete_outasset(
            [out_b.recordcode], operator_jobcode="MGR-ORB-A", operator_name="甲经理", user=manager_a
        )

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert OutAsset.objects.filter(recordcode=out_b.recordcode, is_deleted=False).exists()
        out_b.asset_recordcode.refresh_from_db()
        assert out_b.asset_recordcode.asset_current_status == "in_use"

    def test_same_department_batch_all_success(self, storage, asset_type, manager_a):
        """甲经理批量删本部门编码：全部成功，资产状态回退 in_store。"""
        out_a = _make_scoped_outasset(storage, asset_type, manager_a, "A01")

        result = OutAssetService.batch_delete_outasset(
            [out_a.recordcode], operator_jobcode="MGR-ORB-A", operator_name="甲经理", user=manager_a
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert not OutAsset.objects.filter(recordcode=out_a.recordcode, is_deleted=False).exists()
        out_a.asset_recordcode.refresh_from_db()
        assert out_a.asset_recordcode.asset_current_status == "in_store"

    def test_mixed_batch_one_success_one_fail(self, storage, asset_type, manager_a, manager_b):
        """混合批次：本部门成、他部门败（B14 逐条校验，不整体拒绝）。"""
        out_a = _make_scoped_outasset(storage, asset_type, manager_a, "A02")
        out_b = _make_scoped_outasset(storage, asset_type, manager_b, "B02")

        result = OutAssetService.batch_delete_outasset(
            [out_a.recordcode, out_b.recordcode],
            operator_jobcode="MGR-ORB-A",
            operator_name="甲经理",
            user=manager_a,
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert not OutAsset.objects.filter(recordcode=out_a.recordcode, is_deleted=False).exists()
        assert OutAsset.objects.filter(recordcode=out_b.recordcode, is_deleted=False).exists()


class TestOutAssetSingleEndpointRBAC:
    def _client(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_cross_department_destroy_404(self, storage, asset_type, manager_a, manager_b):
        """跨部门单条 DELETE → get_object()（scoped）404，不泄露存在性。"""
        out_b = _make_scoped_outasset(storage, asset_type, manager_b, "B03")
        response = self._client(manager_a).delete(f"/api/v1/assets/out-assets/{out_b.recordcode}/")
        assert response.status_code == 404, response.status_code
        assert OutAsset.objects.filter(recordcode=out_b.recordcode, is_deleted=False).exists()

    def test_cross_department_cancel_404(self, storage, asset_type, manager_a, manager_b):
        """跨部门单条 cancel → get_object()（scoped）404（存在性不泄露）。"""
        out_b = _make_scoped_outasset(storage, asset_type, manager_b, "B04")
        response = self._client(manager_a).post(f"/api/v1/assets/out-assets/{out_b.recordcode}/cancel/")
        assert response.status_code == 404, response.status_code
        assert OutAsset.objects.filter(recordcode=out_b.recordcode, is_deleted=False).exists()
