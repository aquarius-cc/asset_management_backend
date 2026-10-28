"""
R-2 维修状态机外围收口测试(M-RC-02)

- PATCH repair_status 被序列化器静默忽略(read_only),状态机旁路关闭,
  资产 asset_current_status 不发生 FSM 迁移
- 同资产顺序双 create → 第二次 400 DUPLICATE_REPAIR_IN_PROGRESS
  (行锁串行化使顺序与并发等价,无需真并发用例)
- 正规流转护栏:旁路关闭后 repair-done 仍可经 Service 改写 repair_status
  (证明 read_only 未误伤正规路径)
"""

from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, RepairAsset


@pytest.fixture
def repairing_asset(db: Any, asset: Asset) -> Asset:
    """处于 repairing 状态的资产(配合 in_progress 维修记录)"""
    asset.asset_current_status = Asset.AssetStatus.REPAIRING
    asset.save(update_fields=["asset_current_status", "updated_at"])
    return asset


@pytest.fixture
def in_progress_repair(db: Any, repairing_asset: Asset) -> RepairAsset:
    """进行中的维修记录(与 repairing 资产配套)"""
    return RepairAsset.objects.create(
        asset_recordcode=repairing_asset,
        repair_reason="R-2 状态机测试",
        repair_date="2026-10-01",
        repair_status=RepairAsset.RepairStatus.IN_PROGRESS,
    )


@pytest.mark.django_db
class TestRepairStatusReadOnly:
    """M-RC-02: repair_status 客户端写入口收口"""

    def test_patch_repair_status_ignored(
        self,
        api_client: APIClient,
        admin_auth_user: Any,
        in_progress_repair: RepairAsset,
        repairing_asset: Asset,
    ) -> None:
        """PATCH 携带 repair_status → 200,状态被静默忽略,可写字段正常更新,资产状态无迁移"""
        api_client.force_authenticate(user=admin_auth_user)
        url = reverse("repair-assets-detail", kwargs={"recordcode": in_progress_repair.recordcode})
        resp = api_client.patch(
            url,
            {"repair_status": "completed", "repair_description": "R-2 旁路尝试"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        in_progress_repair.refresh_from_db()
        assert in_progress_repair.repair_status == RepairAsset.RepairStatus.IN_PROGRESS
        # 可写字段正常更新,证明非整体拒绝
        assert in_progress_repair.repair_description == "R-2 旁路尝试"
        # 资产状态无 FSM 迁移(旁路关闭的核心断言)
        repairing_asset.refresh_from_db()
        assert repairing_asset.asset_current_status == Asset.AssetStatus.REPAIRING

    def test_duplicate_create_sequential_400(
        self,
        api_client: APIClient,
        admin_auth_user: Any,
        asset: Asset,
    ) -> None:
        """同资产顺序双 create → 第二次 400 DUPLICATE_REPAIR_IN_PROGRESS"""
        api_client.force_authenticate(user=admin_auth_user)
        asset.asset_current_status = Asset.AssetStatus.BROKEN
        asset.save(update_fields=["asset_current_status", "updated_at"])
        url = reverse("repair-assets-list")
        payload = {
            "asset_recordcode": asset.recordcode,
            "repair_reason": "R-2 重复送修",
            "repair_date": "2026-10-02",
        }
        first = api_client.post(url, payload, format="json")
        assert first.status_code == status.HTTP_201_CREATED

        second = api_client.post(url, payload, format="json")
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert "DUPLICATE_REPAIR_IN_PROGRESS" in str(second.data)
        assert (
            RepairAsset.objects.filter(
                asset_recordcode=asset, repair_status=RepairAsset.RepairStatus.IN_PROGRESS
            ).count()
            == 1
        )

    def test_repair_done_still_works_after_readonly(
        self,
        api_client: APIClient,
        admin_auth_user: Any,
        in_progress_repair: RepairAsset,
        repairing_asset: Asset,
    ) -> None:
        """回归护栏:read_only 不误伤正规流转,repair-done 经 Service 改写 repair_status"""
        api_client.force_authenticate(user=admin_auth_user)
        # 先确认旁路关闭(PATCH 状态被忽略)
        patch_url = reverse("repair-assets-detail", kwargs={"recordcode": in_progress_repair.recordcode})
        resp = api_client.patch(patch_url, {"repair_status": "completed"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        in_progress_repair.refresh_from_db()
        assert in_progress_repair.repair_status == RepairAsset.RepairStatus.IN_PROGRESS

        # 正规流转:repair-done → Service 改写为 completed + 资产 FSM 迁移
        done_url = reverse("assets-repair-done", kwargs={"recordcode": repairing_asset.recordcode})
        resp = api_client.post(done_url, {"actual_return_date": "2026-10-28"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        in_progress_repair.refresh_from_db()
        assert in_progress_repair.repair_status == RepairAsset.RepairStatus.COMPLETED
        repairing_asset.refresh_from_db()
        assert repairing_asset.asset_current_status == Asset.AssetStatus.RECYCLED_PENDING
