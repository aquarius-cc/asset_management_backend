"""报废批量删除行级隔离测试（BF-170 OP-03，P1 安全，不可回退）。

【锁定的不变量】
cancel_waste_asset / batch_delete_waste_assets 必须携带调用者身份（kw-only user 必填），
逐条经 AssetSelector.ensure_asset_visible 校验（B14 逐条校验、可能部分成功）：

- 跨部门条目 → 进 fail_items（error_code=ASSET_NOT_VISIBLE），记录保留
- 同部门条目 → 正常删除
- 混合批次 → 1 成 1 败（不整体拒绝、不越权删除）
- auditor（低于 IsAssetAdminOrAbove）→ 端点层 403

与 asset/recycle/damaged 三链同口径（DR-1）。
"""

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, DamagedAsset, WasteAsset
from apps.assetmanagement.services.waste_asset_service import WasteAssetService
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db


def _phone_seq():
    n = 100
    while True:
        n += 1
        yield f"137{n:08d}"


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


@pytest.fixture
def dept_a():
    return Department.objects.create(department_code="DEPT-RB-A", department_name="甲部门", path="/DEPT-RB-A")


@pytest.fixture
def dept_b():
    return Department.objects.create(department_code="DEPT-RB-B", department_name="乙部门", path="/DEPT-RB-B")


@pytest.fixture
def manager_a(dept_a):
    return _make_manager("MGR-RB-A", dept_a)


@pytest.fixture
def manager_b(dept_b):
    return _make_manager("MGR-RB-B", dept_b)


def _make_scoped_waste(storage, asset_type, manager_user, code: str) -> WasteAsset:
    """按 entry_person 归属部门的已报废记录（三路径解析第一优先级为保管人,此处用入库人锚定）。

    manager_user 为 AuthUser；asset_entry_person_recordcode 关联 Employee（同名 jobcode 隐式关联）。
    """
    entry_person = Employee.objects.get(employee_jobcode=manager_user.auth_username)
    asset = Asset.objects.create(
        recordcode=f"ASSET-WRB-{code}",
        asset_code=f"WRB-{code}",
        asset_name=f"报废隔离{code}",
        asset_purchase_price=1,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_entry_person_recordcode=entry_person,
        asset_current_status="scrapped",
    )
    damaged = DamagedAsset.objects.create(
        asset_recordcode=asset,
        damaged_asset_number=1,
        approval_status="approved",
    )
    return WasteAsset.objects.create(
        asset_recordcode=asset,
        damaged_recordcode=damaged,
        waste_asset_number=1,
        waste_asset_date="2024-02-01",
    )


class TestWasteAssetBatchDeleteRBAC:
    def test_cross_department_batch_all_fail(self, storage, asset_type, manager_a, manager_b, dept_b):
        """甲经理批量删乙部门编码：全部进 fail_items（ASSET_NOT_VISIBLE），记录保留。"""
        waste_b = _make_scoped_waste(storage, asset_type, manager_b, "B01")

        result = WasteAssetService.batch_delete_waste_assets(
            [waste_b.asset_recordcode.asset_code],
            operator_jobcode="MGR-RB-A",
            operator_name="甲经理",
            user=manager_a,
        )

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert WasteAsset.objects.filter(recordcode=waste_b.recordcode, is_deleted=False).exists()

    def test_same_department_batch_all_success(self, storage, asset_type, manager_a, dept_a):
        """甲经理批量删本部门编码：全部成功，记录删除。"""
        waste_a = _make_scoped_waste(storage, asset_type, manager_a, "A01")

        result = WasteAssetService.batch_delete_waste_assets(
            [waste_a.asset_recordcode.asset_code],
            operator_jobcode="MGR-RB-A",
            operator_name="甲经理",
            user=manager_a,
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert not WasteAsset.objects.filter(recordcode=waste_a.recordcode, is_deleted=False).exists()

    def test_mixed_batch_one_success_one_fail(self, storage, asset_type, manager_a, manager_b):
        """混合批次：本部门成、他部门败（B14 逐条校验，不整体拒绝）。"""
        waste_a = _make_scoped_waste(storage, asset_type, manager_a, "A02")
        waste_b = _make_scoped_waste(storage, asset_type, manager_b, "B02")

        result = WasteAssetService.batch_delete_waste_assets(
            [waste_a.asset_recordcode.asset_code, waste_b.asset_recordcode.asset_code],
            operator_jobcode="MGR-RB-A",
            operator_name="甲经理",
            user=manager_a,
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert WasteAsset.objects.filter(recordcode=waste_a.recordcode, is_deleted=False).exists() is False
        assert WasteAsset.objects.filter(recordcode=waste_b.recordcode, is_deleted=False).exists() is True


class TestWasteAssetBatchDeleteEndpointRBAC:
    def test_auditor_batch_delete_403(self, storage, asset_type, manager_a):
        """auditor 低于 IsAssetAdminOrAbove → 端点层 403（写类权限降级）。"""
        waste_a = _make_scoped_waste(storage, asset_type, manager_a, "A03")
        auditor_user = AuthUser.objects.create_user(
            auth_username="AUD-RB", password=TEST_PASSWORD, auth_phone=next(_phones)
        )
        Employee.objects.create(
            employee_jobcode="AUD-RB",
            employee_name="审计员",
            employee_department=None,
            role=EmployeeRole.AUDITOR,
            employee_phone=next(_phones),
        )

        client = APIClient()
        client.force_authenticate(user=auditor_user)
        response = client.post(
            "/api/v1/assets/waste-assets/batch-delete/",
            {"ids": [waste_a.recordcode]},
            format="json",
        )
        assert response.status_code == 403, response.status_code
