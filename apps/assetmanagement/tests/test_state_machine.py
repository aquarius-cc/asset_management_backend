"""资产状态机核心测试(CT-3: 全路径覆盖 + 审批拒绝回退路径专项)"""

import pytest

from apps.assetmanagement.models import Asset
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError


def _make_asset(storage, asset_type, status="in_store", code="A_FSM"):
    return Asset.objects.create(
        asset_code=code,
        asset_name="FSM测试",
        asset_purchase_price=2000,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-01",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status=status,
    )


@pytest.mark.django_db
class TestRejectToOriginal:
    def _damaged_asset(self, storage, asset_type):
        return _make_asset(storage, asset_type, "damaged", "A_FSM_R")

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
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_E")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.reject_to_original(asset, "in_use")


@pytest.mark.django_db
class TestMarkBrokenFromInUse:
    """CT-3: in_use → broken 显式路径测试"""

    def test_mark_broken_from_in_use(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_BK1")
        AssetFSM.mark_broken(asset)
        assert asset.asset_current_status == "broken"

    def test_mark_broken_from_in_use_via_service(self, storage, asset_type, user):
        from apps.assetmanagement.services.asset_service import AssetService

        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_BK2")
        AssetService.mark_asset_broken(
            asset_code="A_FSM_BK2",
            broken_reason="在用时损坏",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"


@pytest.mark.django_db
class TestMarkLostFromInUse:
    """CT-3: in_use → lost 显式路径测试"""

    def test_mark_lost_from_in_use(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_LS1")
        AssetFSM.mark_lost(asset)
        assert asset.asset_current_status == "lost"

    def test_mark_lost_from_in_use_via_service(self, storage, asset_type, user):
        from apps.assetmanagement.services.asset_service import AssetService

        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_LS2")
        AssetService.mark_asset_lost(
            asset_code="A_FSM_LS2",
            lost_reason="在用时遗失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        asset.refresh_from_db()
        assert asset.asset_current_status == "lost"


@pytest.mark.django_db
class TestMarkBrokenFromRecycledPending:
    """CT-3: recycled_pending → broken 显式路径测试"""

    def test_mark_broken_from_recycled_pending(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "recycled_pending", "A_FSM_RBK")
        AssetFSM.mark_broken(asset)
        assert asset.asset_current_status == "broken"


@pytest.mark.django_db
class TestMarkLostFromRecycledPending:
    """CT-3: recycled_pending → lost 显式路径测试"""

    def test_mark_lost_from_recycled_pending(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "recycled_pending", "A_FSM_RLS")
        AssetFSM.mark_lost(asset)
        assert asset.asset_current_status == "lost"


@pytest.mark.django_db
class TestLostToDamaged:
    """CT-3: lost → damaged (damaged) 显式路径测试"""

    def test_lost_to_damaged(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "lost", "A_FSM_LD")
        AssetFSM.damaged(asset)
        assert asset.asset_current_status == "damaged"


@pytest.mark.django_db
class TestScrappedTerminalRejection:
    """CT-3: scrapped 终态 — 所有转出路径应被拒绝"""

    def test_scrapped_blocks_recycle(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_RC")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.recycle(asset)

    def test_scrapped_blocks_damaged(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_DM")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.damaged(asset)

    def test_scrapped_blocks_mark_broken(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_BK")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.mark_broken(asset)

    def test_scrapped_blocks_mark_lost(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_LS")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.mark_lost(asset)

    def test_scrapped_blocks_repair(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_RP")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.repair(asset)

    def test_scrapped_blocks_approve(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_AP")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.approve(asset)

    def test_scrapped_blocks_force_recycle(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_FR")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.force_recycle_from_any(asset)

    def test_scrapped_blocks_reject_to_original(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_SCR_RJ")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.reject_to_original(asset, "in_use")


@pytest.mark.django_db
class TestForceRecycleFromAny:
    """CT-3: force_recycle_from_any 全路径覆盖"""

    @pytest.mark.parametrize(
        "from_status",
        ["in_store", "in_use", "recycled_pending", "broken", "repairing", "lost", "damaged"],
    )
    def test_force_recycle_from_non_terminal(self, storage, asset_type, from_status):
        asset = _make_asset(storage, asset_type, from_status, f"A_FSM_FR_{from_status}")
        AssetFSM.force_recycle_from_any(asset)
        assert asset.asset_current_status == "recycled_pending"

    def test_force_recycle_from_scrapped_raises(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "scrapped", "A_FSM_FR_SCR")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.force_recycle_from_any(asset)
