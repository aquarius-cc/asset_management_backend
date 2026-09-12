"""
公开扫码查看 API 测试

【R4-04 最小暴露】响应为 6 字段白名单,敏感字段(价格/仓库/分类/保管人/电话/使用地点/入库日期)禁止出现。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import AssetOperationLog

# R4-04 白名单:与 public_scan_view 的 data dict 严格对齐
PUBLIC_SCAN_FIELDS = {
    "asset_code",
    "asset_name",
    "asset_specification",
    "asset_brand",
    "asset_current_status",
    "physical_grade",
}

# 禁暴露的敏感键(收敛前曾返回的字段)
FORBIDDEN_FIELDS = {
    "asset_purchase_price",
    "asset_storage_name",
    "asset_type_name",
    "asset_manager_name",
    "asset_manager_phone",
    "asset_using_location",
    "asset_entry_date",
}


@pytest.mark.django_db
class TestPublicScanView:
    def test_scan_found(self, asset):
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        from rest_framework.test import APIClient

        client = APIClient()
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        data = resp.data["data"]
        assert data["asset_code"] == "A001"
        assert data["asset_name"] == "测试资产"
        # 严格白名单:键集合必须与 6 字段完全一致(拦截未来回归新增字段)
        assert set(data.keys()) == PUBLIC_SCAN_FIELDS

    def test_scan_minimal_fields(self, asset, employee):
        """即使保管人/仓库/分类数据齐全,敏感字段也不得出现在响应中"""
        asset.asset_manager_recordcode = employee
        asset.save(update_fields=["asset_manager_recordcode"])
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        for key in FORBIDDEN_FIELDS:
            assert key not in data

    def test_scan_audit_logged(self, asset):
        """成功查询记录 public_scan 审计日志(含客户端 IP)"""
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url, REMOTE_ADDR="10.1.1.1")
        assert resp.status_code == status.HTTP_200_OK

        log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="public_scan").first()
        assert log is not None
        assert log.ip_address == "10.1.1.1"
        assert log.asset_name == asset.asset_name

    def test_scan_not_found(self):
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": "nonexistent"})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.data["code"] == 404
        # 404 不记审计(匿名限流兜底防刷)
        assert not AssetOperationLog.objects.filter(asset_code="nonexistent", operation_type="public_scan").exists()

    def test_scan_deleted_asset(self, asset):
        asset.is_deleted = True
        asset.save(update_fields=["is_deleted"])
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
