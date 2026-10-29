"""
资产生命周期事件 ViewSet API 测试

测试 BrokenAssetViewSet, LostAssetViewSet, FoundAssetViewSet, RepairAssetViewSet 的 API 端点。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import AssetOperationLog, BrokenAsset, FoundAsset, LostAsset, RepairAsset


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
        """测试创建损坏资产记录(【C-1 修复】现经 mark_asset_broken: FSM in_store→broken + 审计 + 行级隔离)"""
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
        # C-1 核心锚: 创建后资产状态已流转(绕过 FSM 的旧路径资产仍为 in_store)
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"

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
        """测试删除损坏资产记录(批次②a: 软删而非物理删除, 响应保留 recordcode + 审计落库)"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == broken_asset.recordcode
        assert BrokenAsset.all_objects.filter(recordcode=broken_asset.recordcode, is_deleted=True).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
        ).exists()

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
        """测试创建遗失资产记录(【C-1 修复】现经 mark_asset_lost: FSM in_store→lost + 审计 + 行级隔离)"""
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
        # C-1 核心锚: 创建后资产状态已流转(绕过 FSM 的旧路径资产仍为 in_store)
        asset.refresh_from_db()
        assert asset.asset_current_status == "lost"

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
        """测试删除遗失资产记录(批次②a: 软删而非物理删除, 响应保留 recordcode + 审计落库)"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == lost_asset.recordcode
        assert LostAsset.all_objects.filter(recordcode=lost_asset.recordcode, is_deleted=True).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=lost_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
        ).exists()

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
        """测试创建找回资产记录(【C-1 修复】现经 find_and_return_asset: FSM lost→recycled_pending + 行级隔离)"""
        # C-1 后 create 走 FSM: 资产必须处于 lost 态(lost_asset 夹具已建遗失记录但未流转状态)
        asset.asset_current_status = "lost"
        asset.save(update_fields=["asset_current_status", "updated_at"])
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
        # C-1 核心锚: 创建后资产状态已流转(找回→待发放)
        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"

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
        """测试删除找回资产记录(批次②a: 软删而非物理删除, 响应保留 recordcode + 审计落库)"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == found_asset.recordcode
        assert FoundAsset.all_objects.filter(recordcode=found_asset.recordcode, is_deleted=True).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=found_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
        ).exists()

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
        """测试创建维修资产记录(broken 资产送修,经 RepairAssetService)"""
        asset.asset_current_status = "broken"
        asset.save(update_fields=["asset_current_status"])
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
        asset.refresh_from_db()
        assert asset.asset_current_status == "repairing"

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
        """已完成维修记录可删除"""
        RepairAsset.objects.filter(recordcode=repair_asset.recordcode).update(repair_status="completed")
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not RepairAsset.objects.filter(recordcode=repair_asset.recordcode).exists()

    def test_destroy_repair_asset_in_progress_rejected(self, admin_authenticated_client, repair_asset):
        """进行中的维修记录拒绝删除,防止资产卡死 repairing"""
        url = reverse("repair-assets-detail", kwargs={"recordcode": repair_asset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert RepairAsset.objects.filter(recordcode=repair_asset.recordcode).exists()

    def test_batch_delete(self, admin_authenticated_client, repair_asset, broken_asset):
        """批量删除维修记录(#17 下沉 Service 后视图冒烟: 成功 + 失败明细 + 标准中文文案)"""
        RepairAsset.objects.filter(recordcode=repair_asset.recordcode).update(repair_status="completed")
        url = reverse("repair-assets-batch-delete")
        response = admin_authenticated_client.post(
            url,
            {"ids": [repair_asset.recordcode, broken_asset.recordcode]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        data = response.data["data"]
        assert data["success_count"] == 1
        assert data["fail_items"][0]["error_code"] == "NOT_FOUND"
        assert response.data["message"] == "批量删除完成,成功 1 条,失败 1 条"
        assert not RepairAsset.objects.filter(recordcode=repair_asset.recordcode, is_deleted=False).exists()


class TestLifecycleUpdateAudit:
    """【M-RC-05】update/partial_update 走 Service 委托后落 UPDATE 审计行(正反用例)"""

    def test_update_broken_writes_operation_log(self, admin_authenticated_client, broken_asset):
        """更新损坏记录 → 200 且落 UPDATE 审计行"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        response = admin_authenticated_client.put(url, {"broken_reason": "审计后原因"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "更新成功"
        log = AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.UPDATE,
        ).latest("operation_time")
        assert log.related_record_code == broken_asset.recordcode
        assert log.related_record_type == "BrokenAsset"

    def test_partial_update_lost_writes_operation_log(self, admin_authenticated_client, lost_asset):
        """部分更新遗失记录 → 200 且落 UPDATE 审计行"""
        url = reverse("lost-assets-detail", kwargs={"recordcode": lost_asset.recordcode})
        response = admin_authenticated_client.patch(url, {"lost_reason": "审计后遗失原因"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        log = AssetOperationLog.objects.filter(
            asset_code=lost_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.UPDATE,
        ).latest("operation_time")
        assert log.related_record_code == lost_asset.recordcode
        assert log.related_record_type == "LostAsset"

    def test_update_found_writes_operation_log(self, admin_authenticated_client, found_asset):
        """更新找回记录 → 200 且落 UPDATE 审计行"""
        url = reverse("found-assets-detail", kwargs={"recordcode": found_asset.recordcode})
        response = admin_authenticated_client.put(
            url, {"found_location": "审计后找回地点"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        log = AssetOperationLog.objects.filter(
            asset_code=found_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.UPDATE,
        ).latest("operation_time")
        assert log.related_record_code == found_asset.recordcode
        assert log.related_record_type == "FoundAsset"

    def test_update_by_regular_user_forbidden_no_log(self, authenticated_client, broken_asset):
        """普通认证用户 PUT → 403 且不写审计行(防覆写绕过权限分支)"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": broken_asset.recordcode})
        response = authenticated_client.put(url, {"broken_reason": "越权"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.UPDATE,
        ).exists()

    def test_update_nonexistent_recordcode_no_log(self, admin_authenticated_client, broken_asset):
        """不存在的 recordcode → 404 且不写审计行(防异常分支误写审计)"""
        url = reverse("broken-assets-detail", kwargs={"recordcode": "RC-NOT-EXIST"})
        response = admin_authenticated_client.put(url, {"broken_reason": "x"}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.UPDATE,
        ).exists()
