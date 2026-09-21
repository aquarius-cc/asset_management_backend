"""回收资产管理服务测试"""

import unittest.mock as mock
from datetime import date

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    BrokenAsset,
    LostAsset,
    OutAsset,
)
from apps.assetmanagement.services import recycle_asset_service
from apps.assetmanagement.services.recycle_asset_service import RecycleAssetService
from apps.assetmanagement.state_machine import InvalidTransitionError
from core.exceptions import AppValidationError


@pytest.fixture
def out_asset(db, storage, asset_type, user):
    """创建已出库的资产和出库记录"""
    asset = Asset.objects.create(
        asset_code="A_RECY",
        asset_name="可回收资产",
        asset_purchase_price=5000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_use",
    )
    asset.asset_applicant_recordcode = user
    asset.asset_manager_recordcode = user
    asset.asset_using_location = "使用地点"
    asset.save(update_fields=["asset_applicant_recordcode", "asset_manager_recordcode", "asset_using_location"])

    out = OutAsset.objects.create(
        asset_recordcode=asset,
        outasset_date="2024-01-01",
        outasset_previous_status="in_store",
    )
    return out


@pytest.fixture
def recycle_data(out_asset, storage, user):
    return {
        "outasset_recordcode": out_asset,
        "recycle_asset_storage": storage,
        "recycle_asset_recycle_person_jobcode": user,
        "recycle_asset_date": date.today(),
    }


@pytest.mark.django_db
class TestCreateRecycleAsset:
    def test_create_success(self, recycle_data):
        result = RecycleAssetService.create_recycle_asset(recycle_data)
        assert result.pk is not None
        asset = result.asset_recordcode
        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"
        assert asset.asset_applicant_recordcode is None
        assert asset.asset_manager_recordcode is None
        assert asset.asset_using_location is None

    def test_create_without_outasset_raises(self, storage, user):
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.create_recycle_asset(
                {
                    "recycle_asset_storage": storage,
                    "recycle_asset_recycle_person_jobcode": user,
                    "recycle_asset_date": date.today(),
                }
            )
        assert exc_info.value.error_code == "MISSING_OUTASSET_RECORDCODE"

    def test_create_nonexistent_outasset_raises(self, storage, user):
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.create_recycle_asset(
                {
                    "outasset_recordcode": "NONEXIST",
                    "recycle_asset_storage": storage,
                    "recycle_asset_recycle_person_jobcode": user,
                    "recycle_asset_date": date.today(),
                }
            )
        assert exc_info.value.error_code == "OUTASSET_NOT_FOUND"

    def test_create_invalid_status_raises(self, out_asset, storage, user):
        asset = out_asset.asset_recordcode
        asset.asset_current_status = "in_store"
        asset.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.create_recycle_asset(
                {
                    "outasset_recordcode": out_asset,
                    "recycle_asset_storage": storage,
                    "recycle_asset_recycle_person_jobcode": user,
                    "recycle_asset_date": date.today(),
                }
            )
        assert exc_info.value.error_code == "INVALID_ASSET_STATUS_FOR_RECYCLE"

    def test_create_with_string_storage_code(self, out_asset, user):
        result = RecycleAssetService.create_recycle_asset(
            {
                "outasset_recordcode": out_asset,
                "recycle_asset_storage": out_asset.asset_recordcode.asset_storage_recordcode.storage_code,
                "recycle_asset_recycle_person_jobcode": user.employee_jobcode,
                "recycle_asset_date": date.today(),
            }
        )
        assert result.pk is not None

    def test_create_with_operator_jobcode(self, out_asset, storage, user):
        result = RecycleAssetService.create_recycle_asset(
            {
                "outasset_recordcode": out_asset,
                "recycle_asset_storage": storage,
                "recycle_asset_date": date.today(),
            },
            operator_jobcode=user.employee_jobcode,
            operator_name="操作人",
        )
        assert result.operator_employee is not None


@pytest.mark.django_db
class TestUpdateRecycleAsset:
    def test_update_success(self, recycle_data):
        ra = RecycleAssetService.create_recycle_asset(recycle_data)
        result = RecycleAssetService.update_recycle_asset(
            ra.recordcode,
            {"recycle_type": "归还"},
        )
        assert result.recycle_type == "归还"

    def test_update_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.update_recycle_asset("NONEXIST", {"recycle_type": "x"})
        assert exc_info.value.error_code == "RECYCLE_ASSET_NOT_FOUND"

    def test_update_multiple_fields(self, recycle_data):
        ra = RecycleAssetService.create_recycle_asset(recycle_data)
        result = RecycleAssetService.update_recycle_asset(
            ra.recordcode,
            {"recycle_type": "借用归还", "recycle_asset_description": "测试描述"},
        )
        assert result.recycle_type == "借用归还"
        assert result.recycle_asset_description == "测试描述"


@pytest.mark.django_db
class TestBatchDeleteRecycleAsset:
    def _create_recycle(self, out_asset, storage, user):
        return RecycleAssetService.create_recycle_asset(
            {
                "outasset_recordcode": out_asset,
                "recycle_asset_storage": storage,
                "recycle_asset_recycle_person_jobcode": user,
                "recycle_asset_date": date.today(),
            }
        )

    def test_batch_delete_exceeds_limit_raises(self):
        codes = [f"RC{i}" for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.batch_delete_recycle_asset(codes)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_nonexistent(self):
        result = RecycleAssetService.batch_delete_recycle_asset(["NONEXIST"])
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_delete_wrong_status(self, out_asset, storage, user):
        ra = self._create_recycle(out_asset, storage, user)
        asset = out_asset.asset_recordcode
        asset.asset_current_status = "in_store"
        asset.save(update_fields=["asset_current_status"])
        result = RecycleAssetService.batch_delete_recycle_asset([ra.recordcode])
        assert result["success_count"] == 0
        assert result["fail_items"][0]["error_code"] == "STATUS_NOT_ALLOWED"

    def test_batch_delete_success_records_audit_log(self, out_asset, storage, user):
        """取消回收成功后应写入状态变更审计日志"""
        ra = self._create_recycle(out_asset, storage, user)
        asset = out_asset.asset_recordcode
        result = RecycleAssetService.batch_delete_recycle_asset(
            [ra.recordcode], operator_jobcode=user.employee_jobcode, operator_name=user.employee_name
        )
        assert result["success_count"] == 1
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        log = (
            AssetOperationLog.objects.filter(
                asset_code=asset.asset_code,
                operation_type="state_change",
                description__contains="cancel_recycle",
            )
            .order_by("-operation_time")
            .first()
        )
        assert log is not None
        assert log.operator_jobcode == user.employee_jobcode
        assert "recycled_pending" in log.description
        assert "in_use" in log.description


@pytest.mark.django_db
class TestRecycleWithBrokenLostMarks:
    """AC-61: 回收时标记损坏/遗失须记录第二次 FSM 转换(recycled_pending → broken/lost)审计"""

    def _create_recycle(self, out_asset, storage, user, **extra):
        data = {
            "outasset_recordcode": out_asset,
            "recycle_asset_storage": storage,
            "recycle_asset_recycle_person_jobcode": user,
            "recycle_asset_date": date.today(),
        }
        data.update(extra)
        return RecycleAssetService.create_recycle_asset(
            data, operator_jobcode=user.employee_jobcode, operator_name=user.employee_name
        )

    def test_create_with_broken_records_state_change_audit(self, out_asset, storage, user):
        asset = out_asset.asset_recordcode
        RecycleAssetService.create_recycle_asset(
            {
                "outasset_recordcode": out_asset,
                "recycle_asset_storage": storage,
                "recycle_asset_recycle_person_jobcode": user,
                "recycle_asset_date": date.today(),
                "is_broken": True,
                "broken_reason": "外壳破损",
            },
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"
        assert BrokenAsset.objects.filter(asset_recordcode=asset).exists()
        log = (
            AssetOperationLog.objects.filter(
                asset_code=asset.asset_code,
                operation_type="state_change",
                description__contains="recycle_mark_broken",
            )
            .order_by("-operation_time")
            .first()
        )
        assert log is not None, "回收标记损坏应记录第二次 FSM 转换审计"
        assert log.operator_jobcode == user.employee_jobcode
        assert "recycled_pending" in log.description
        assert "broken" in log.description

    def test_create_with_lost_records_state_change_audit(self, out_asset, storage, user):
        asset = out_asset.asset_recordcode
        RecycleAssetService.create_recycle_asset(
            {
                "outasset_recordcode": out_asset,
                "recycle_asset_storage": storage,
                "recycle_asset_recycle_person_jobcode": user,
                "recycle_asset_date": date.today(),
                "is_lost": True,
                "lost_reason": "库内盘点缺失",
            },
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        asset.refresh_from_db()
        assert asset.asset_current_status == "lost"
        assert LostAsset.objects.filter(asset_recordcode=asset).exists()
        log = (
            AssetOperationLog.objects.filter(
                asset_code=asset.asset_code,
                operation_type="state_change",
                description__contains="recycle_mark_lost",
            )
            .order_by("-operation_time")
            .first()
        )
        assert log is not None, "回收标记遗失应记录第二次 FSM 转换审计"
        assert log.operator_jobcode == user.employee_jobcode
        assert "recycled_pending" in log.description
        assert "lost" in log.description

    def test_normal_recycle_emits_no_broken_lost_audit(self, out_asset, storage, user):
        """回归护栏: 正常回收路径不得向 broken/lost 转换审计泄漏(保障 normal 分支不动)"""
        asset = out_asset.asset_recordcode
        ra = self._create_recycle(out_asset, storage, user)
        result = RecycleAssetService.batch_delete_recycle_asset(
            [ra.recordcode], operator_jobcode=user.employee_jobcode, operator_name=user.employee_name
        )
        assert result["success_count"] == 1
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        assert not AssetOperationLog.objects.filter(
            asset_code=asset.asset_code,
            operation_type="state_change",
            description__contains="recycle_mark_broken",
        ).exists()
        assert not AssetOperationLog.objects.filter(
            asset_code=asset.asset_code,
            operation_type="state_change",
            description__contains="recycle_mark_lost",
        ).exists()


@pytest.mark.django_db
class TestReissueRecycleAsset:
    """CT-3: reissue_recycle_asset (recycled_pending → in_use) 全路径测试"""

    def test_reissue_success(self, recycle_data, user):
        recycle_asset = RecycleAssetService.create_recycle_asset(recycle_data)
        result = RecycleAssetService.reissue_recycle_asset(
            recycle_asset.recordcode,
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.asset_recordcode.refresh_from_db()
        assert result.outasset_type == OutAsset.OutassetType.REISSUE
        assert result.asset_recordcode.asset_current_status == "in_use"
        assert AssetOperationLog.objects.filter(
            asset_code=result.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.OUT,
        ).exists()

    def test_reissue_record_not_found(self):
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.reissue_recycle_asset("NONEXIST")
        assert exc_info.value.error_code == "RECYCLE_ASSET_NOT_FOUND"

    def test_reissue_wrong_status(self, recycle_data):
        recycle_asset = RecycleAssetService.create_recycle_asset(recycle_data)
        asset = recycle_asset.asset_recordcode
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.reissue_recycle_asset(recycle_asset.recordcode)
        assert exc_info.value.error_code == "INVALID_ASSET_STATUS_FOR_REISSUE"


@pytest.mark.django_db
class TestDefensiveBranches:
    """CT-3/CT-4 (2026-09-21 B1 拆分配套):覆盖 create_recycle_asset 防御分支"""

    @mock.patch("apps.assetmanagement.services.recycle_asset_service.AssetFSM.mark_broken")
    def test_broken_secondary_fsm_failure_raises(self, mock_mark_broken, out_asset, storage, user):
        mock_mark_broken.side_effect = InvalidTransitionError("broken 转换不允许")
        with pytest.raises(AppValidationError) as exc_info:
            RecycleAssetService.create_recycle_asset(
                {
                    "outasset_recordcode": out_asset,
                    "recycle_asset_storage": storage,
                    "recycle_asset_recycle_person_jobcode": user,
                    "recycle_asset_date": date.today(),
                    "is_broken": True,
                }
            )
        assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"

    def test_outasset_without_related_asset_raises(self, storage, user):
        """防御分支:出库记录未关联资产 → OUTASSET_ASSET_MISSING(回收流程不进入)"""
        fake_outasset = mock.MagicMock()
        fake_outasset.asset_recordcode = None
        with mock.patch.object(
            recycle_asset_service.OutAssetSelector,
            "get_outasset_by_record_code",
            return_value=fake_outasset,
        ):
            with pytest.raises(AppValidationError) as exc_info:
                RecycleAssetService.create_recycle_asset(
                    {
                        "outasset_recordcode": "OUT_WITHOUT_ASSET",
                        "recycle_asset_storage": storage,
                        "recycle_asset_recycle_person_jobcode": user,
                        "recycle_asset_date": date.today(),
                    }
                )
        assert exc_info.value.error_code == "OUTASSET_ASSET_MISSING"
