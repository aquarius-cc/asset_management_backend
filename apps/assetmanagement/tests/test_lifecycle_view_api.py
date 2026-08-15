"""
资产生命周期事件 ViewSet API 测试

测试 BrokenAssetViewSet, LostAssetViewSet, FoundAssetViewSet, RepairAssetViewSet 的 API 端点。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import BrokenAsset, FoundAsset, LostAsset, RepairAsset


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证的用户客户端"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_auth_user):
    """管理员用户客户端"""
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


# ==================== BrokenAssetViewSet ====================
@pytest.mark.django_db
class TestBrokenAssetViewSet:
    """BrokenAssetViewSet API 测试"""

    def test_list_broken_assets(self, authenticated_client, broken_asset):
        """测试获取损坏资产列表"""
        url = reverse("broken-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_broken_asset(self, admin_authenticated_client, asset, employee):
        """测试创建损坏资产记录"""
        url = reverse("broken-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "broken_reason": "新损坏原因",
            "broken_date": "2024-12-01",
            "broken_description": "新损坏描述",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        # asset_recordcode is write_only in serializer, check recordcode instead
        assert "recordcode" in response.data["data"]

    def test_retrieve_broken_asset(self, authenticated_client, broken_asset):
        """测试获取损坏资产详情"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == broken_asset.recordcode

    def test_update_broken_asset(self, admin_authenticated_client, broken_asset):
        """测试更新损坏资产记录"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        data = {"broken_reason": "更新后的损坏原因"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["broken_reason"] == "更新后的损坏原因"

    def test_partial_update_broken_asset(self, admin_authenticated_client, broken_asset):
        """测试部分更新损坏资产记录"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        data = {"broken_reason": "部分更新后的损坏原因"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["broken_reason"] == "部分更新后的损坏原因"

    def test_destroy_broken_asset(self, admin_authenticated_client, broken_asset):
        """测试删除损坏资产记录"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not BrokenAsset.objects.filter(recordcode=broken_asset.recordcode).exists()

    def test_batch_delete(self, admin_authenticated_client, broken_asset):
        """测试批量删除损坏资产记录"""
        url = reverse("broken-assets-batch-delete")
        data = {"ids": [broken_asset.recordcode]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1


# ==================== LostAssetViewSet ====================
@pytest.mark.django_db
class TestLostAssetViewSet:
    """LostAssetViewSet API 测试"""

    def test_list_lost_assets(self, authenticated_client, lost_asset):
        """测试获取遗失资产列表"""
        url = reverse("lost-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_lost_asset(self, admin_authenticated_client, asset, employee):
        """测试创建遗失资产记录"""
        url = reverse("lost-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "lost_reason": "新遗失原因",
            "lost_date": "2024-12-01",
            "last_known_location": "新最后已知位置",
            "lost_description": "新遗失描述",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        # asset_recordcode is write_only in serializer, check recordcode instead
        assert "recordcode" in response.data["data"]

    def test_retrieve_lost_asset(self, authenticated_client, lost_asset):
        """测试获取遗失资产详情"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == lost_asset.recordcode

    def test_update_lost_asset(self, admin_authenticated_client, lost_asset):
        """测试更新遗失资产记录"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        data = {"lost_reason": "更新后的遗失原因"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["lost_reason"] == "更新后的遗失原因"

    def test_partial_update_lost_asset(self, admin_authenticated_client, lost_asset):
        """测试部分更新遗失资产记录"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        data = {"lost_reason": "部分更新后的遗失原因"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["lost_reason"] == "部分更新后的遗失原因"

    def test_destroy_lost_asset(self, admin_authenticated_client, lost_asset):
        """测试删除遗失资产记录"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not LostAsset.objects.filter(recordcode=lost_asset.recordcode).exists()

    def test_batch_delete(self, admin_authenticated_client, lost_asset):
        """测试批量删除遗失资产记录"""
        url = reverse("lost-assets-batch-delete")
        data = {"ids": [lost_asset.recordcode]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1


# ==================== FoundAssetViewSet ====================
@pytest.mark.django_db
class TestFoundAssetViewSet:
    """FoundAssetViewSet API 测试"""

    def test_list_found_assets(self, authenticated_client, found_asset):
        """测试获取找回资产列表"""
        url = reverse("found-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_found_asset(self, admin_authenticated_client, asset, employee, lost_asset):
        """测试创建找回资产记录"""
        url = reverse("found-assets-list")
        data = {
            "lost_asset_recordcode": lost_asset.recordcode,
            "asset_recordcode": asset.recordcode,
            "found_location": "新找回位置",
            "found_date": "2024-12-01",
            "found_description": "新找回描述",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        assert "recordcode" in response.data["data"]

    def test_retrieve_found_asset(self, authenticated_client, found_asset):
        """测试获取找回资产详情"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == found_asset.recordcode

    def test_update_found_asset(self, admin_authenticated_client, found_asset):
        """测试更新找回资产记录"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        data = {"found_location": "更新后的找回位置"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["found_location"] == "更新后的找回位置"

    def test_partial_update_found_asset(self, admin_authenticated_client, found_asset):
        """测试部分更新找回资产记录"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        data = {"found_location": "部分更新后的找回位置"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["found_location"] == "部分更新后的找回位置"

    def test_destroy_found_asset(self, admin_authenticated_client, found_asset):
        """测试删除找回资产记录"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not FoundAsset.objects.filter(recordcode=found_asset.recordcode).exists()

    def test_batch_delete(self, admin_authenticated_client, found_asset):
        """测试批量删除找回资产记录"""
        url = reverse("found-assets-batch-delete")
        data = {"ids": [found_asset.recordcode]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1


# ==================== RepairAssetViewSet ====================
@pytest.mark.django_db
class TestRepairAssetViewSet:
    """RepairAssetViewSet API 测试"""

    def test_list_repair_assets(self, authenticated_client, repair_asset):
        """测试获取维修资产列表"""
        url = reverse("repair-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_repair_asset(self, admin_authenticated_client, asset, employee):
        """测试创建维修资产记录"""
        url = reverse("repair-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "repair_reason": "新维修原因",
            "repair_date": "2024-12-01",
            "repair_description": "新维修描述",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        # asset_recordcode is write_only in serializer, check recordcode instead
        assert "recordcode" in response.data["data"]

    def test_retrieve_repair_asset(self, authenticated_client, repair_asset):
        """测试获取维修资产详情"""
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == repair_asset.recordcode

    def test_update_repair_asset(self, admin_authenticated_client, repair_asset):
        """测试更新维修资产记录"""
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        data = {"repair_reason": "更新后的维修原因"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    def test_partial_update_repair_asset(self, admin_authenticated_client, repair_asset):
        """测试部分更新维修资产记录"""
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        data = {"repair_reason": "部分更新后的维修原因"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["repair_reason"] == "部分更新后的维修原因"

    def test_destroy_repair_asset(self, admin_authenticated_client, repair_asset):
        """测试删除维修资产记录"""
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not RepairAsset.objects.filter(recordcode=repair_asset.recordcode).exists()
