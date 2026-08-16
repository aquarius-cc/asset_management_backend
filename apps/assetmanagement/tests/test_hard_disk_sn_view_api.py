"""
硬盘批量保存端点 API 回归测试

锚定 batch-save 全链路修复:
- 序列化器不再调用不存在的 AssetSelector.get_asset_by_recordcode
- 视图以字符串 recordcode 传参,Service 解析为 Asset 实例
- 编辑模式回传自身 SN 不再触发 DUPLICATE_SN_CODE
"""

from typing import Any, cast

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.assetmanagement.models import HardDiskSN
from apps.authusermanagement.models import AuthUser


@pytest.fixture
def admin_user(db: Any) -> AuthUser:
    return cast(AuthUser, AuthUser.objects.create_superuser(auth_username="ADMIN01", password="testpass123"))


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
class TestHardDiskSNBatchSaveAPI:
    def test_batch_save_create_success(self, api_client: APIClient, admin_user: AuthUser, asset: Any) -> None:
        api_client.force_authenticate(user=admin_user)
        url = reverse("harddisk-sn-batch-save")
        response = api_client.post(
            url,
            {
                "asset_recordcode": asset.recordcode,
                "disks": [{"harddisk_sn_code": "API_SN_1", "harddisk_type": "SSD"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["created"] == 1
        assert response.data["data"]["updated"] == 0
        assert response.data["data"]["total"] == 1

    def test_batch_save_update_with_own_sn(self, api_client: APIClient, admin_user: AuthUser, asset: Any) -> None:
        """编辑模式:回传自身 SN 应成功且保留(锚定前端编辑功能修复)"""
        hd = HardDiskSN.objects.create(
            asset_recordcode=asset, harddisk_sn_code="API_SN_3", harddisk_type="SSD"
        )
        api_client.force_authenticate(user=admin_user)
        url = reverse("harddisk-sn-batch-save")
        response = api_client.post(
            url,
            {
                "asset_recordcode": asset.recordcode,
                "disks": [
                    {"recordcode": hd.recordcode, "harddisk_sn_code": "API_SN_3", "harddisk_type": "NVMe"}
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["updated"] == 1
        hd.refresh_from_db()
        assert hd.harddisk_sn_code == "API_SN_3"
        assert hd.harddisk_type == "NVMe"

    def test_batch_save_nonexistent_asset_returns_400(self, api_client: APIClient, admin_user: AuthUser) -> None:
        api_client.force_authenticate(user=admin_user)
        url = reverse("harddisk-sn-batch-save")
        response = api_client.post(
            url,
            {"asset_recordcode": "ASSET-NOT-EXIST", "disks": [{"harddisk_sn_code": "API_SN_2"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
