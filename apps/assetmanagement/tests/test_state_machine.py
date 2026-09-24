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
class TestCancelDamaged:
    """取消报废回退路径专项: 与 reject_to_original 同构"""

    def _damaged_asset(self, storage, asset_type):
        return _make_asset(storage, asset_type, "damaged", "A_FSM_C")

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
    def test_cancel_returns_to_original(self, storage, asset_type, original_status, expected_status):
        """damaged → 原状态(合法原状态逐一回退,与 reject 一致)"""
        asset = self._damaged_asset(storage, asset_type)
        AssetFSM.cancel_damaged(asset, original_status)
        assert asset.asset_current_status == expected_status

    @pytest.mark.parametrize("original_status", [None, "in_store", "scrapped", "unknown_x"])
    def test_cancel_illegal_original_falls_back(self, storage, asset_type, original_status):
        """缺失/非法原状态兜底 recycled_pending"""
        asset = self._damaged_asset(storage, asset_type)
        AssetFSM.cancel_damaged(asset, original_status)
        assert asset.asset_current_status == "recycled_pending"

    def test_cancel_on_non_damaged_raises(self, storage, asset_type):
        """非 damaged 状态取消应抛 InvalidTransitionError"""
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_CE")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.cancel_damaged(asset, "in_use")


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
    """CT-3: lost → damaged (to_damaged) 显式路径测试"""

    def test_lost_to_damaged(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "lost", "A_FSM_LD")
        AssetFSM.to_damaged(asset)
        assert asset.asset_current_status == "damaged"


@pytest.mark.django_db
class TestBrokenToDamaged:
    """CT-3: broken → damaged (to_damaged) 显式路径测试"""

    def test_broken_to_damaged(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "broken", "A_FSM_BD")
        AssetFSM.to_damaged(asset)
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
            AssetFSM.to_damaged(asset)

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


@pytest.mark.django_db
class TestOutAssetTransition:
    """CT-3: (in_store | recycled_pending) → in_use(outasset 显式路径)"""

    @pytest.mark.parametrize("source_status", ["in_store", "recycled_pending"])
    def test_outasset_to_in_use(self, storage, asset_type, source_status):
        asset = _make_asset(storage, asset_type, source_status, f"A_FSM_OUT_{source_status[0].upper()}")
        AssetFSM.outasset(asset)
        assert asset.asset_current_status == "in_use"


@pytest.mark.django_db
class TestCancelOutAsset:
    """CT-3: in_use → previous_status(cancel_outasset 显式路径)"""

    @pytest.mark.parametrize(
        ("previous_status", "expected_status"),
        [("in_store", "in_store"), ("recycled_pending", "recycled_pending")],
    )
    def test_cancel_outasset_returns_previous(self, storage, asset_type, previous_status, expected_status):
        asset = _make_asset(storage, asset_type, "in_use", f"A_FSM_CO_{previous_status}")
        AssetFSM.cancel_outasset(asset, previous_status)
        assert asset.asset_current_status == expected_status

    def test_cancel_outasset_illegal_previous_raises(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_COE")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.cancel_outasset(asset, "scrapped")

    def test_cancel_outasset_on_non_in_use_raises(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_store", "A_FSM_CON")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.cancel_outasset(asset, "in_store")


@pytest.mark.django_db
class TestCancelRecycle:
    """CT-3: recycled_pending → in_use(cancel_recycle 显式路径)"""

    def test_cancel_recycle_to_in_use(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "recycled_pending", "A_FSM_CR")
        AssetFSM.cancel_recycle(asset)
        assert asset.asset_current_status == "in_use"

    def test_cancel_recycle_on_non_pending_raises(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_use", "A_FSM_CR_E")
        with pytest.raises(InvalidTransitionError):
            AssetFSM.cancel_recycle(asset)


@pytest.mark.django_db
class TestMarkBrokenFromInStore:
    """CT-3: in_store → broken 显式路径(VALID_TRANSITIONS 声明,此前零覆盖)"""

    def test_mark_broken_from_in_store(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_store", "A_FSM_BKS")
        AssetFSM.mark_broken(asset)
        assert asset.asset_current_status == "broken"


@pytest.mark.django_db
class TestMarkLostFromInStore:
    """CT-3: in_store → lost 显式路径(VALID_TRANSITIONS 声明,此前零覆盖)"""

    def test_mark_lost_from_in_store(self, storage, asset_type):
        asset = _make_asset(storage, asset_type, "in_store", "A_FSM_LSS")
        AssetFSM.mark_lost(asset)
        assert asset.asset_current_status == "lost"
