"""资产状态机核心测试(CT-3: 审批拒绝回退路径专项)"""

import pytest

from apps.assetmanagement.models import Asset
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError


@pytest.mark.django_db
class TestRejectToOriginal:
    def _damaged_asset(self, storage, asset_type):
        return Asset.objects.create(
            asset_code="A_FSM_R",
            asset_name="FSM拒绝测试",
            asset_purchase_price=2000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="damaged",
        )

    @pytest.mark.parametrize(
        ("original_status", "expected_status"),
        [
            ("in_use", "in_use"),
            ("recycled_pending", "recycled_pending"),
            ("broken", "broken"),
            ("lost", "lost"),
            ("repairing", "repairing"),
        ],
    )
    def test_reject_returns_to_original(self, storage, asset_type, original_status, expected_status):
        """damaged → 原状态(合法原状态逐一回退)"""
        asset = self._damaged_asset(storage, asset_type)
        AssetFSM.reject_to_original(asset, original_status)
        assert asset.asset_current_status == expected_status

    @pytest.mark.parametrize("original_status", [None, "in_store", "scrapped", "unknown_x"])
    def test_reject_illegal_original_falls_back(self, storage, asset_type, original_status):
        """缺失/非法原状态兜底 recycled_pending"""
        asset = self._damaged_asset(storage, asset_type)
        AssetFSM.reject_to_original(asset, original_status)
        assert asset.asset_current_status == "recycled_pending"

    def test_reject_on_non_damaged_raises(self, storage, asset_type):
        """非 damaged 状态审批拒绝应抛 InvalidTransitionError"""
        asset = Asset.objects.create(
            asset_code="A_FSM_E",
            asset_name="FSM错误测试",
            asset_purchase_price=2000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_use",
        )
        with pytest.raises(InvalidTransitionError):
            AssetFSM.reject_to_original(asset, "in_use")
