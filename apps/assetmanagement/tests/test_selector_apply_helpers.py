"""M-LAY-01/02: View 内联过滤下沉后的 Selector 唯一实现契约。

夹具在本模块内自带（根/各 app conftest 均未提供 user_a/asset_a/asset_b）。
双部门口径对齐 test_asset_selector_isolation.py:30-103：普通用户只看本部门资产。
"""

from datetime import date

import pytest

from apps.assetmanagement.models import Asset, DamagedAsset, HardDiskSN, OutAsset, RecycleAsset, WasteAsset
from apps.assetmanagement.selectors import (
    AssetSelector,
    DamagedAssetSelector,
    HardDiskSNSelector,
    OutAssetSelector,
    RecycleAssetSelector,
    WasteAssetSelector,
)
from apps.assetmanagement.tests.factories import AssetFactory
from apps.authusermanagement.tests.factories import AuthUserFactory
from apps.usermanagement.tests.factories import DepartmentFactory, EmployeeFactory


@pytest.fixture
def lay_dept_a(db):
    return DepartmentFactory(department_code="DLAY01", department_name="分层部门A")


@pytest.fixture
def lay_dept_b(db):
    return DepartmentFactory(department_code="DLAY02", department_name="分层部门B")


@pytest.fixture
def lay_emp_a(db, lay_dept_a):
    return EmployeeFactory(
        employee_jobcode="layEmpA",
        employee_name="分层员工A",
        employee_department=lay_dept_a,
    )


@pytest.fixture
def lay_emp_b(db, lay_dept_b):
    return EmployeeFactory(
        employee_jobcode="layEmpB",
        employee_name="分层员工B",
        employee_department=lay_dept_b,
    )


@pytest.fixture
def lay_user_a(db, lay_emp_a):
    # get_employee_for_user 按 employee_jobcode == auth_username 解析部门，不写 auth_user FK。
    return AuthUserFactory(auth_username=lay_emp_a.employee_jobcode)


@pytest.fixture
def lay_asset_a(db, lay_emp_a):
    return AssetFactory(asset_code="LAY-A001", asset_manager_recordcode=lay_emp_a)


@pytest.fixture
def lay_asset_b(db, lay_emp_b):
    return AssetFactory(asset_code="LAY-B001", asset_manager_recordcode=lay_emp_b)


@pytest.mark.django_db
def test_out_asset_status_filter_preserves_inline_predicate():
    base = OutAsset.objects.for_list().filter(is_deleted=False)
    got = OutAssetSelector.apply_asset_status_filter(base, "in_use")
    # expected 写原 View 字面谓词，证明逐字保留而非同义反复。
    assert str(got.query) == str(base.filter(asset_recordcode__asset_current_status="in_use").query)
    assert OutAssetSelector.apply_asset_status_filter(base, "") is base


@pytest.mark.django_db
def test_date_range_filters_preserve_inline_predicates():
    waste_base = WasteAsset.objects.filter(is_deleted=False)
    got = WasteAssetSelector.apply_date_range_filter(
        waste_base, date(2024, 1, 1), date(2024, 12, 31)
    )
    expected = waste_base.filter(waste_asset_date__gte=date(2024, 1, 1)).filter(
        waste_asset_date__lte=date(2024, 12, 31)
    )
    assert str(got.query) == str(expected.query)

    recycle_base = RecycleAsset.objects.for_list().filter(is_deleted=False)
    got = RecycleAssetSelector.apply_date_range_filter(recycle_base, "2024-01-01", "2024-12-31")
    expected = recycle_base.filter(recycle_asset_date__gte="2024-01-01").filter(
        recycle_asset_date__lte="2024-12-31"
    )
    assert str(got.query) == str(expected.query)


@pytest.mark.django_db
def test_pending_filter_uses_text_choices_enum():
    base = DamagedAsset.objects.filter(is_deleted=False)
    got = DamagedAssetSelector.apply_pending_approval_filter(base)
    # 原 View 字面谓词 "pending"，与 BR-3 枚举锚点双重锁定。
    assert str(got.query) == str(base.filter(approval_status="pending").query)
    assert DamagedAsset.ApprovalStatus.PENDING == "pending"


@pytest.mark.django_db
def test_hard_disk_helpers_preserve_scope_and_order():
    base = HardDiskSN.objects.filter(is_deleted=False)
    assert str(HardDiskSNSelector.apply_sn_filter(base, "SN-1").query) == str(
        base.filter(harddisk_sn_code="SN-1").query
    )
    assert str(HardDiskSNSelector.apply_asset_code_filter(base, "A001").query) == str(
        base.filter(asset_recordcode__asset_code="A001").order_by("harddisk_sn_code").query
    )


@pytest.mark.django_db
def test_asset_visibility_helpers_enforce_row_scope(lay_user_a, lay_asset_a, lay_asset_b):
    assert AssetSelector.exists_by_code_for_user(lay_asset_a.asset_code, user=lay_user_a) is True
    assert AssetSelector.exists_by_code_for_user(lay_asset_b.asset_code, user=lay_user_a) is False

    visible = AssetSelector.get_visible_asset_by_code(lay_asset_a.asset_code, user=lay_user_a)
    assert visible is not None
    assert visible.pk == lay_asset_a.pk
    assert AssetSelector.get_visible_asset_by_code(lay_asset_b.asset_code, user=lay_user_a) is None


@pytest.mark.django_db
def test_get_visible_asset_codes_filters_and_dedups(lay_user_a, lay_asset_a, lay_asset_b):
    queryset = AssetSelector.get_queryset_for_user(lay_user_a)
    codes = AssetSelector.get_visible_asset_codes(
        queryset,
        [lay_asset_a.asset_code, lay_asset_b.asset_code, lay_asset_a.asset_code],
    )
    assert codes == {lay_asset_a.asset_code}


def test_apply_recordcode_filter_empty_short_circuits():
    queryset = Asset.objects.for_list().all()
    assert AssetSelector.apply_recordcode_filter(queryset, "") is queryset
    assert str(AssetSelector.apply_recordcode_filter(queryset, "RC-1").query) == str(
        queryset.filter(recordcode="RC-1").query
    )
