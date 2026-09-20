"""B12 行级隔离加固回归测试

锚定场景(部门 D010 / D020):
- 普通用户 user_a(regular_user, 归属部门 D010)仅能看见归属 D010 的资产;
- 归属 D020 的资产对 user_a 必须完全不可见(与不存在同义):
  单条 Selector 返回 None,列表 Selector 为空,Service 写入口抛 ASSET_NOT_FOUND。

覆盖矩阵(CT-4 回归屏障):
- Selector 列表方法: get_queryset_for_user / get_available_assets / get_assets_by_status /
  search_assets / get_assets_by_type / get_assets_by_storage
- Selector 单条方法: get_asset_by_code / get_asset_by_recordcode / get_asset_detail_by_code
- Service 写入口: update_asset / delete_asset / batch_delete_asset /
  change_asset_status / change_outasset_employee / HardDiskSNService.batch_save

依赖: AssetService / HardDiskSNService 的 user 必填参数(B12)在此场景下必须拒绝越权访问。
"""

import pytest

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.services.asset_service import AssetService
from apps.assetmanagement.services.hard_disk_sn_service import HardDiskSNService
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.exceptions import AppValidationError
from core.tests import TEST_PASSWORD


@pytest.fixture
def dept_a(db):
    return Department.objects.create(department_code="D010", department_name="部门A")


@pytest.fixture
def dept_b(db):
    return Department.objects.create(department_code="D020", department_name="部门B")


@pytest.fixture
def emp_a(db, dept_a):
    return Employee.objects.create(
        employee_jobcode="empA",
        employee_name="员工A",
        employee_department=dept_a,
        employee_phone="13800001001",
        role="regular_user",
    )


@pytest.fixture
def emp_b(db, dept_b):
    return Employee.objects.create(
        employee_jobcode="empB",
        employee_name="员工B",
        employee_department=dept_b,
        employee_phone="13800001002",
        role="regular_user",
    )


@pytest.fixture
def user_a(db, emp_a):
    return AuthUser.objects.create_user(
        auth_username=emp_a.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002001"
    )


@pytest.fixture
def user_b(db, emp_b):
    return AuthUser.objects.create_user(
        auth_username=emp_b.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002002"
    )


@pytest.fixture
def asset_a(db, storage, asset_type, emp_a):
    return Asset.objects.create(
        asset_code="ISO-A001",
        asset_name="部门A资产",
        asset_purchase_price=1000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_manager_recordcode=emp_a,
        asset_current_status="in_store",
    )


@pytest.fixture
def asset_b(db, storage, asset_type, emp_b):
    return Asset.objects.create(
        asset_code="ISO-B001",
        asset_name="部门B资产",
        asset_purchase_price=2000.00,
        asset_purchase_date="2024-02-01",
        asset_entry_date="2024-02-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_manager_recordcode=emp_b,
        asset_current_status="in_store",
    )


def _codes(qs):
    return set(qs.values_list("asset_code", flat=True))


@pytest.mark.django_db
class TestSelectorListIsolation:
    def test_get_queryset_for_user_only_own_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.get_queryset_for_user(user_a)) == {"ISO-A001"}

    def test_get_available_assets_excludes_other_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.get_available_assets(user=user_a)) == {"ISO-A001"}

    def test_get_assets_by_status_excludes_other_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.get_assets_by_status("in_store", user=user_a)) == {"ISO-A001"}

    def test_search_assets_excludes_other_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.search_assets(keyword="资产", user=user_a)) == {"ISO-A001"}

    def test_get_assets_by_type_excludes_other_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.get_assets_by_type("AT001", user=user_a)) == {"ISO-A001"}

    def test_get_assets_by_storage_excludes_other_department(self, user_a, asset_a, asset_b):
        assert _codes(AssetSelector.get_assets_by_storage("S001", user=user_a)) == {"ISO-A001"}


@pytest.mark.django_db
class TestSelectorSingleIsolation:
    def test_get_asset_by_code_other_department_returns_none(self, user_a, asset_a, asset_b):
        assert AssetSelector.get_asset_by_code("ISO-A001", user=user_a) is not None
        assert AssetSelector.get_asset_by_code("ISO-B001", user=user_a) is None

    def test_get_asset_by_recordcode_other_department_returns_none(self, user_a, asset_a, asset_b):
        assert AssetSelector.get_asset_by_recordcode(asset_a.recordcode, user=user_a) is not None
        assert AssetSelector.get_asset_by_recordcode(asset_b.recordcode, user=user_a) is None

    def test_get_asset_detail_by_code_other_department_returns_none(self, user_a, asset_a, asset_b):
        assert AssetSelector.get_asset_detail_by_code("ISO-A001", user=user_a) is not None
        assert AssetSelector.get_asset_detail_by_code("ISO-B001", user=user_a) is None


@pytest.mark.django_db
class TestServiceWriteIsolation:
    def test_update_asset_other_department_raises_not_found(self, user_a, asset_b):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset("ISO-B001", {"asset_name": "越权改名"}, user=user_a)
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_delete_asset_other_department_raises_not_found(self, user_a, asset_b):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset("ISO-B001", user=user_a)
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_change_asset_status_other_department_raises_not_found(self, user_a, asset_b):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status("ISO-B001", "in_use", user=user_a)
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_change_outasset_employee_other_department_raises_not_found(self, user_a, asset_b):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_outasset_employee("ISO-B001", "X", "Y", user=user_a)
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_batch_save_hard_disk_other_department_raises_not_found(self, user_a, asset_b):
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(
                asset_b.recordcode, [{"harddisk_sn_code": "ISO-SN-1", "harddisk_type": "SSD"}], user=user_a
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_batch_delete_mixes_own_and_other_department(self, user_a, asset_a, asset_b):
        result = AssetService.batch_delete_asset(["ISO-A001", "ISO-B001"], user=user_a)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert "ISO-A001" in result["success_ids"]
        assert "ISO-B001" in [item["id"] for item in result["fail_items"]]
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_own_department_write_still_succeeds(self, user_a, asset_a):
        """对照用例: 越权拒绝不代表部门内写入口被误伤(B12 不破坏正常路径)"""
        result = AssetService.update_asset("ISO-A001", {"asset_name": "部门A改名"}, user=user_a)
        result.refresh_from_db()
        assert result.asset_name == "部门A改名"


@pytest.mark.django_db
class TestCrossUserSymmetry:
    def test_each_user_sees_only_own_department(self, user_a, user_b, asset_a, asset_b):
        assert _codes(AssetSelector.get_queryset_for_user(user_a)) == {"ISO-A001"}
        assert _codes(AssetSelector.get_queryset_for_user(user_b)) == {"ISO-B001"}
