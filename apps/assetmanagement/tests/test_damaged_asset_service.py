"""待报废资产管理服务测试"""

import pytest

from apps.assetmanagement.models import (
    Asset,
    DamagedAsset,
)
from apps.assetmanagement.services.damaged_asset_service import DamagedAssetService
from core.exceptions import AppValidationError


@pytest.fixture
def asset_in_use(db, storage, asset_type, user):
    """创建处于 in_use 状态的资产"""
    asset = Asset.objects.create(
        asset_code="A_DMG",
        asset_name="待报废测试",
        asset_purchase_price=3000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_use",
    )
    asset.asset_applicant_recordcode = user
    asset.asset_manager_recordcode = user
    asset.save(update_fields=["asset_applicant_recordcode", "asset_manager_recordcode"])
    return asset


@pytest.fixture
def asset_damaged(db, storage, asset_type, user):
    """创建处于 damaged 状态的资产"""
    asset = Asset.objects.create(
        asset_code="A_DMG_D",
        asset_name="待报废状态资产",
        asset_purchase_price=3000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="damaged",
    )
    asset.asset_applicant_recordcode = user
    asset.save(update_fields=["asset_applicant_recordcode"])
    return asset


@pytest.fixture
def pending_damaged(db, asset_in_use):
    """创建待审批的待报废记录"""
    return DamagedAsset.objects.create(
        asset_recordcode=asset_in_use,
        damaged_asset_number=1,
        approval_status="pending",
        original_status="in_use",
    )


@pytest.mark.django_db
class TestCreateDamagedAsset:
    def test_create_success(self, asset_in_use):
        data = {"asset_recordcode": asset_in_use, "damaged_asset_number": 1}
        result = DamagedAssetService.create_damaged_asset(data)
        assert result.pk is not None
        assert result.approval_status == "pending"

    def test_create_without_asset_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.create_damaged_asset({})
        assert exc_info.value.error_code == "MISSING_ASSET_CODE"

    def test_create_duplicate_record_raises(self, asset_in_use):
        DamagedAssetService.create_damaged_asset({"asset_recordcode": asset_in_use, "damaged_asset_number": 1})
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.create_damaged_asset({"asset_recordcode": asset_in_use, "damaged_asset_number": 1})
        assert exc_info.value.error_code == "DUPLICATE_DAMAGED_RECORD"

    def test_create_populates_original_status(self, asset_in_use):
        """创建时应自动记录申请前状态(审批拒绝回退依据,业务约束 §三.5)"""
        result = DamagedAssetService.create_damaged_asset(
            {"asset_recordcode": asset_in_use, "damaged_asset_number": 1}
        )
        result.refresh_from_db()
        assert result.original_status == "in_use"
        asset_in_use.refresh_from_db()
        assert asset_in_use.asset_current_status == "damaged"


@pytest.mark.django_db
class TestApproveAssetRecordcode:
    def test_approve_success(self, asset_damaged, user):
        """审批通过:damaged → scrapped"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset_damaged,
            damaged_asset_number=1,
            approval_status="pending",
            original_status="broken",
        )
        result = DamagedAssetService.approve_asset_recordcode(
            asset_damaged.recordcode,
            approver_jobcode=user.employee_jobcode,
            operator_name="审批人",
        )
        assert result["damaged_asset"].approval_status == "approved"
        assert result["waste_asset"].pk is not None
        asset_damaged.refresh_from_db()
        assert asset_damaged.asset_current_status == "scrapped"

    def test_approve_nonexistent_raises(self, user):
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.approve_asset_recordcode("NONEXIST", user.employee_jobcode, "审批人")
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_FOUND"

    def test_approve_non_pending_status_raises(self, asset_damaged, user):
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset_damaged,
            damaged_asset_number=1,
            approval_status="approved",
        )
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.approve_asset_recordcode(asset_damaged.recordcode, user.employee_jobcode, "审批人")
        assert exc_info.value.error_code == "INVALID_APPROVAL_STATUS"


@pytest.mark.django_db
class TestRejectAssetRecordcode:
    def test_reject_to_broken(self, db, storage, asset_type, user):
        """审批拒绝(原状态 broken):damaged → broken"""
        asset = Asset.objects.create(
            asset_code="A_BRK_R",
            asset_name="损坏资产",
            asset_purchase_price=2000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="damaged",
        )
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="pending",
            original_status="broken",
        )
        result = DamagedAssetService.reject_asset_recordcode(
            asset.recordcode,
            approver_jobcode=user.employee_jobcode,
            operator_name="审批人",
        )
        assert result.approval_status == "rejected"
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"

    def test_reject_to_lost(self, db, storage, asset_type, user):
        """审批拒绝(原状态 lost):damaged → lost"""
        asset = Asset.objects.create(
            asset_code="A_LOST_R",
            asset_name="遗失资产",
            asset_purchase_price=2000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="damaged",
        )
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="pending",
            original_status="lost",
        )
        result = DamagedAssetService.reject_asset_recordcode(
            asset.recordcode,
            approver_jobcode=user.employee_jobcode,
            operator_name="审批人",
        )
        assert result.approval_status == "rejected"
        asset.refresh_from_db()
        assert asset.asset_current_status == "lost"

    def test_reject_nonexistent_raises(self, user):
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.reject_asset_recordcode("NONEXIST", user.employee_jobcode, "审批人")
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_FOUND"

    @pytest.mark.parametrize(
        ("original_status", "expected_status"),
        [
            ("in_use", "in_use"),
            ("recycled_pending", "recycled_pending"),
            ("repairing", "repairing"),
            (None, "recycled_pending"),
            ("in_store", "recycled_pending"),
        ],
    )
    def test_reject_returns_to_original_status(
        self, db, storage, asset_type, user, original_status, expected_status
    ):
        """审批拒绝:damaged → 原状态;缺失/非法原状态兜底 recycled_pending"""
        asset = Asset.objects.create(
            asset_code="A_REJ_P",
            asset_name="回退测试资产",
            asset_purchase_price=2000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="damaged",
        )
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            approval_status="pending",
            original_status=original_status,
        )
        result = DamagedAssetService.reject_asset_recordcode(
            asset.recordcode,
            approver_jobcode=user.employee_jobcode,
            operator_name="审批人",
        )
        assert result.approval_status == "rejected"
        asset.refresh_from_db()
        assert asset.asset_current_status == expected_status

    def test_reject_non_pending_status_raises(self, asset_damaged, user):
        DamagedAsset.objects.create(
            asset_recordcode=asset_damaged,
            damaged_asset_number=1,
            approval_status="rejected",
        )
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.reject_asset_recordcode(asset_damaged.recordcode, user.employee_jobcode, "审批人")
        assert exc_info.value.error_code == "INVALID_APPROVAL_STATUS"


@pytest.mark.django_db
class TestCancelAssetRecordcode:
    def test_cancel_success(self, asset_damaged):
        """取消报废:damaged → recycled_pending"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset_damaged,
            damaged_asset_number=1,
            approval_status="pending",
            original_status="in_use",
        )
        DamagedAssetService.cancel_asset_recordcode(
            asset_damaged.recordcode,
            operator_jobcode="U001",
            operator_name="操作人",
        )
        asset_damaged.refresh_from_db()
        assert asset_damaged.asset_current_status == "recycled_pending"

    def test_cancel_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.cancel_asset_recordcode("NONEXIST")
        assert exc_info.value.error_code == "DAMAGED_ASSET_NOT_FOUND"

    def test_cancel_non_pending_status_raises(self, asset_damaged):
        DamagedAsset.objects.create(
            asset_recordcode=asset_damaged,
            damaged_asset_number=1,
            approval_status="approved",
        )
        with pytest.raises(AppValidationError) as exc_info:
            DamagedAssetService.cancel_asset_recordcode(asset_damaged.recordcode)
        assert exc_info.value.error_code == "INVALID_APPROVAL_STATUS"
