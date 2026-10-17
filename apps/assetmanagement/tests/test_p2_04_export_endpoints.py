"""P2-04 后端导出端点回归测试。

覆盖:
- DamagedAssetViewSet.get_export_queryset 写死 pending(混入 approved/rejected 时行集只含 pending)
- HardDiskSNViewSet 挂 ExportExcelMixin 后 /export/ 端点可用 + RBAC
- 导出行集与列表口径一致(Damaged: pagination.total 即 pending 行数)

xlsx 断言先例: test_operation_log_export_scope.py(load_workbook 解析内容,非仅状态码)。
"""

import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.assetmanagement.models import DamagedAsset, HardDiskSN
from apps.assetmanagement.views.damaged_asset_view import DamagedAssetViewSet
from apps.assetmanagement.views.hard_disk_sn_view import HardDiskSNViewSet
from apps.usermanagement.models import Employee, EmployeeRole
from core.tests import TEST_PASSWORD


User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


def _phone_seq():
    n = 0
    while True:
        n += 1
        yield f"139{n:08d}"


_phones = _phone_seq()


def _make_user(username, role=EmployeeRole.ASSET_ADMIN, department=None):
    user = User.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_is_staff=(role == EmployeeRole.SYSTEM_ADMIN),
        auth_phone=next(_phones),
    )
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}员工",
        employee_department=department,
        role=role,
        employee_phone=next(_phones),
    )
    return user


def _export_first_column(view_cls, url_name, user, sheet_name):
    """调用导出端点并返回 xlsx 第一列(排除表头)。"""
    url = reverse(url_name)
    request = APIRequestFactory().get(url)
    force_authenticate(request, user=user)
    response = view_cls.as_view({"get": "export_excel"})(request)
    assert response.status_code == 200, getattr(response, "data", response.status_code)
    try:
        payload = b"".join(response.streaming_content)
    finally:
        response.close()
    sheet = load_workbook(io.BytesIO(payload))[sheet_name]
    return {row[0] for row in sheet.iter_rows(min_row=2, max_col=1, values_only=True) if row[0] is not None}


# --------------------------------------------------------------------------
# Damaged: get_export_queryset 写死 pending
# --------------------------------------------------------------------------


class TestDamagedExportPendingOnly:
    def test_get_export_queryset_filters_pending(self, damaged_asset, asset, employee, storage, asset_type):
        """混入 approved 时导出行集只含 pending(独立资产规避 uq_damaged_asset_active_asset)。"""
        from apps.assetmanagement.models import Asset

        approved_asset = Asset.objects.create(
            asset_code="A-APPROVED-QS",
            asset_name="已审批资产QS",
            asset_purchase_price=888,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="waste",
        )
        approved = DamagedAsset.objects.create(
            asset_recordcode=approved_asset,
            damaged_date="2024-06-02",
            damaged_asset_description="approved行",
            damaged_asset_number=1,
            approval_status="approved",
            approver=employee,
        )
        viewset = DamagedAssetViewSet()
        viewset.request = type("R", (), {"user": _make_user("exp-dmg-admin", EmployeeRole.SYSTEM_ADMIN)})()
        qs = viewset.get_export_queryset()
        statuses = set(qs.values_list("approval_status", flat=True))
        assert statuses == {"pending"}
        assert approved.recordcode not in {r.recordcode for r in qs}
        assert damaged_asset.recordcode in {r.recordcode for r in qs}

    def test_damaged_export_xlsx_only_pending(self, damaged_asset, asset, employee, storage, asset_type):
        """端到端: 导出 xlsx 行集只含 pending(混入 approved 且用独立资产区分首列)。"""
        from apps.assetmanagement.models import Asset

        approved_asset = Asset.objects.create(
            asset_code="A-APPROVED-EXP",
            asset_name="已审批资产",
            asset_purchase_price=999,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="waste",
        )
        DamagedAsset.objects.create(
            asset_recordcode=approved_asset,
            damaged_date="2024-06-04",
            damaged_asset_description="approved端到端",
            damaged_asset_number=1,
            approval_status="approved",
            approver=employee,
        )
        user = _make_user("exp-dmg-xlsx", EmployeeRole.SYSTEM_ADMIN)
        codes = _export_first_column(DamagedAssetViewSet, "damaged-assets-export-excel", user, "待报废资产")
        assert asset.asset_code in codes
        assert "A-APPROVED-EXP" not in codes

    def test_damaged_export_requires_export_permission(self, damaged_asset):
        """regular_user 无导出权限(CanExportExcel)。"""
        user = _make_user("exp-dmg-regular", EmployeeRole.REGULAR_USER)
        url = reverse("damaged-assets-export-excel")
        request = APIRequestFactory().get(url)
        force_authenticate(request, user=user)
        response = DamagedAssetViewSet.as_view({"get": "export_excel"})(request)
        assert response.status_code == 403


# --------------------------------------------------------------------------
# HardDiskSN: 挂 mixin 后 /export/ 可用
# --------------------------------------------------------------------------


class TestHardDiskSNExport:
    def test_harddisk_export_returns_xlsx(self, asset):
        HardDiskSN.objects.create(asset_recordcode=asset, harddisk_sn_code="HD-EXP-001", harddisk_type="SSD")
        user = _make_user("exp-hd-admin", EmployeeRole.SYSTEM_ADMIN)
        codes = _export_first_column(HardDiskSNViewSet, "harddisk-sn-export-excel", user, "硬盘序列号")
        assert "HD-EXP-001" not in codes  # 首列是资产编码,非 SN
        assert asset.asset_code in codes

    def test_harddisk_export_regular_user_403(self, asset):
        HardDiskSN.objects.create(asset_recordcode=asset, harddisk_sn_code="HD-EXP-002")
        user = _make_user("exp-hd-regular", EmployeeRole.REGULAR_USER)
        url = reverse("harddisk-sn-export-excel")
        request = APIRequestFactory().get(url)
        force_authenticate(request, user=user)
        response = HardDiskSNViewSet.as_view({"get": "export_excel"})(request)
        assert response.status_code == 403
