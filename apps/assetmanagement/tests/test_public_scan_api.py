"""
公开扫码查看 API 测试
"""

import pytest
from django.urls import reverse
from rest_framework import status


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
        assert data["asset_purchase_price"] == "****"

    def test_scan_not_found(self):
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": "nonexistent"})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.data["code"] == 404

    def test_scan_masked_phone(self, asset, employee):
        asset.asset_manager_recordcode = employee
        asset.save(update_fields=["asset_manager_recordcode"])
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        phone = resp.data["data"]["asset_manager_phone"]
        assert "****" in phone

    def test_scan_no_manager(self, asset):
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["asset_manager_name"] is None
        assert resp.data["data"]["asset_manager_phone"] == ""

    def test_scan_deleted_asset(self, asset):
        asset.is_deleted = True
        asset.save(update_fields=["is_deleted"])
        from rest_framework.test import APIClient

        client = APIClient()
        url = reverse("public-scan", kwargs={"recordcode": asset.recordcode})
        resp = client.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
