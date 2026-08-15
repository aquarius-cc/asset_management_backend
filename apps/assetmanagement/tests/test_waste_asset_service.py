"""已报废资产管理服务测试"""

from datetime import date
from typing import Any

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetType,
    DamagedAsset,
    Storage,
    WasteAsset,
)
from apps.assetmanagement.services.waste_asset_service import WasteAssetService
from core.exceptions import AppValidationError


@pytest.fixture
def asset_in_damaged(db, storage, asset_type):
    """创建处于 damaged 状态的资产"""
    asset = Asset.objects.create(
        asset_code="A_WASTE",
        asset_name="待报废资产",
        asset_purchase_price=5000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="damaged",
    )
    return asset


@pytest.fixture
def approved_damaged_asset(db, asset_in_damaged):
    """创建已审批通过的待报废记录"""
    return DamagedAsset.objects.create(
        asset_recordcode=asset_in_damaged,
        damaged_asset_number=1,
        approval_status="approved",
        original_status="broken",
    )


@pytest.fixture
def pending_damaged_asset(db, asset_in_damaged):
    """创建待审批的待报废记录"""
    return DamagedAsset.objects.create(
        asset_recordcode=asset_in_damaged,
        damaged_asset_number=1,
        approval_status="pending",
    )


@pytest.mark.django_db
class TestCreateWasteAsset:
    def test_create_without_damaged_asset_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_waste_asset({})
        assert exc_info.value.error_code == "MISSING_DAMAGED_ASSET"

    def test_create_unapproved_damaged_raises(self, pending_damaged_asset, asset_in_damaged):
        """create_waste_asset 读取 waste_data['asset_recordcode'] 作为 DamagedAsset 校验审批状态"""
        waste_data = {
            "asset_recordcode": pending_damaged_asset,
            "damaged_recordcode": pending_damaged_asset,
            "waste_asset_number": 1,
            "waste_asset_date": date.today(),
        }
        # approval_status 为 pending,应触发审批校验拒绝
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_waste_asset(waste_data)
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_APPROVED"

    def test_create_unapproved_rejected_damaged_raises(self):
        """未通过审批的 DamagedAsset 应被拒绝"""
        asset = Asset.objects.create(
            asset_code="A_WASTE2",
            asset_name="W2",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_type_recordcode=AssetType.objects.create(type_code="AT_W2", type_name="AT_W2"),
            asset_storage_recordcode=Storage.objects.create(
                storage_code="S_W2",
                storage_name="S_W2",
                storage_address="addr",
                storage_capacity=100,
                sort_order=0,
            ),
            asset_current_status="damaged",
        )
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="pending",
        )
        # 读取 asset_recordcode 为 DamagedAsset,检查 approval_status != "approved"
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_waste_asset(
                {
                    "asset_recordcode": damaged,
                    "damaged_recordcode": damaged,
                    "waste_asset_number": 1,
                    "waste_asset_date": date.today(),
                }
            )
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_APPROVED"

    def test_create_waste_asset_success(self, db: Any, approved_damaged_asset: Any, asset_in_damaged: Any) -> None:
        """create_waste_asset 成功路径:创建报废记录并将资产从 damaged 流转为 scrapped"""
        result = WasteAssetService.create_waste_asset(
            {
                "asset_recordcode": approved_damaged_asset,
                "damaged_recordcode": approved_damaged_asset,
                "waste_asset_number": 1,
                "waste_asset_date": date.today(),
            }
        )
        assert result.pk is not None
        assert result.asset_recordcode.pk == asset_in_damaged.pk
        asset_in_damaged.refresh_from_db()
        assert asset_in_damaged.asset_current_status == "scrapped"

    def test_create_waste_asset_already_scrapped_skips_fsm(self, db: Any, storage: Any, asset_type: Any) -> None:
        """资产已是 scrapped 时跳过 FSM(避免重复流转),仍创建报废记录"""
        asset = Asset.objects.create(
            asset_code="A_SCRAP2",
            asset_name="S2",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="scrapped",
        )
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="approved",
        )
        result = WasteAssetService.create_waste_asset(
            {
                "asset_recordcode": damaged,
                "damaged_recordcode": damaged,
                "waste_asset_number": 1,
                "waste_asset_date": date.today(),
            }
        )
        assert result.pk is not None
        asset.refresh_from_db()
        assert asset.asset_current_status == "scrapped"


@pytest.mark.django_db
class TestCreateFromDamagedAsset:
    def test_create_from_damaged_success(self, approved_damaged_asset, asset_in_damaged):
        result = WasteAssetService.create_from_damaged_asset(approved_damaged_asset)
        assert result.pk is not None
        assert result.waste_asset_number == 1

    def test_create_from_unapproved_raises(self, pending_damaged_asset):
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_from_damaged_asset(pending_damaged_asset)
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_APPROVED"

    def test_create_from_damaged_without_asset_raises(self, db):
        damaged = DamagedAsset.objects.create(
            damaged_asset_number=1,
            approval_status="approved",
        )
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_from_damaged_asset(damaged)
        assert exc_info.value.error_code == "MISSING_RELATED_ASSET"

    def test_create_duplicate_waste_raises(self, db: Any, approved_damaged_asset: Any) -> None:
        """同一资产已存在报废记录时,再次创建应报 DUPLICATE_WASTE_RECORD"""
        WasteAssetService.create_from_damaged_asset(approved_damaged_asset)
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.create_from_damaged_asset(approved_damaged_asset)
        assert exc_info.value.error_code == "DUPLICATE_WASTE_RECORD"


@pytest.mark.django_db
class TestCancelWasteAsset:
    def _create_waste(self, asset, damaged):
        return WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_number=1,
            waste_asset_date=date.today(),
        )

    def test_cancel_success(self, storage, asset_type, user):
        """取消报废:WasteAsset 记录被删除,资产状态保持 scrapped(终态不可逆)"""
        asset = Asset.objects.create(
            asset_code="A_CANCEL",
            asset_name="取消测试",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="scrapped",
        )
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="approved",
        )
        waste = self._create_waste(asset, damaged)
        waste_rc = waste.recordcode
        WasteAssetService.cancel_waste_asset(
            asset.asset_code,
            operator_jobcode="U001",
            operator_name="操作人",
        )
        assert not WasteAsset.objects.filter(recordcode=waste_rc, is_deleted=False).exists()
        asset.refresh_from_db()
        # scrapped 是终态,取消报废不改变资产状态
        assert asset.asset_current_status == "scrapped"

    def test_cancel_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            WasteAssetService.cancel_waste_asset("NONEXIST")
        assert exc_info.value.error_code == "WASTE_ASSET_NOT_FOUND"

    def test_cancel_non_scrapped_asset(self, storage, asset_type, user, approved_damaged_asset):
        """资产非 scrapped 状态时,取消仅删除记录不改状态"""
        asset = Asset.objects.create(
            asset_code="A_NS",
            asset_name="非scrapped",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_use",
        )
        asset.asset_applicant_recordcode = user
        asset.save(update_fields=["asset_applicant_recordcode"])
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="approved",
        )
        _ = WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_number=1,
            waste_asset_date=date.today(),
        )
        WasteAssetService.cancel_waste_asset(asset.asset_code)
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
