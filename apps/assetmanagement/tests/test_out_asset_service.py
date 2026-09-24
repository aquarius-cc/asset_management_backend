"""
出库 Service 层单元测试(CT-1: out_asset_service 核心业务逻辑独立单测)

覆盖审查报告 #14 所列缺口:
- create_outasset 状态守卫、快照(original_*)构建落库
- 出库后资产状态流转 in_use、仓库清空、usage_type new→used (AC-27 / F-P2-9)
- 非法源状态 ILLEGAL_OUTASSET
- 取消出库(batch_delete_outasset)快照恢复契约
- 批量方法 fail_items 结构
- 行锁超时 409 ASSET_LOCKED(AC-30/65 / F-P2-8): 单条 create 与 cancel 批量路径
"""

from unittest import mock

import pytest
from django.db import OperationalError

from apps.assetmanagement.models import Asset
from apps.assetmanagement.services.out_asset_service import OutAssetService
from core.exceptions import AppValidationError, ResourceConflictError


def _make_asset(
    storage,
    asset_type,
    status,
    code,
    applicant=None,
    manager=None,
    using_location=None,
):
    return Asset.objects.create(
        asset_code=code,
        asset_name="出库Service测试",
        asset_purchase_price=2000,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-01",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status=status,
        asset_applicant_recordcode=applicant,
        asset_manager_recordcode=manager,
        asset_using_location=using_location,
    )


def _outasset_payload(asset, applicant=None, manager=None, using_location="出库地点"):
    return {
        "asset_recordcode": asset,
        "outasset_date": "2024-03-01",
        "outasset_type": "receive",
        "outasset_applicant": applicant,
        "outasset_manager": manager,
        "outasset_using_location": using_location,
    }


@pytest.mark.django_db
class TestCreateOutAssetService:
    """create_outasset:状态守卫 + 快照构建落库"""

    @pytest.mark.parametrize(
        ("source_status", "expected_previous"),
        [("in_store", "in_store"), ("recycled_pending", "recycled_pending")],
    )
    def test_create_success_records_previous_status_and_snapshot(
        self, storage, asset_type, employee, source_status, expected_previous
    ):
        asset = _make_asset(
            storage,
            asset_type,
            source_status,
            f"OUT_SVC_OK_{source_status[0].upper()}",
            applicant=employee,
            manager=employee,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
        )

        assert outasset.outasset_previous_status == expected_previous
        assert outasset.outasset_using_location == "出库地点"

        snapshot = outasset.outasset_snapshot
        assert snapshot["original_applicant"]["jobcode"] == employee.employee_jobcode
        assert snapshot["original_manager"]["jobcode"] == employee.employee_jobcode
        assert snapshot["original_using_location"] == "原地点"
        assert snapshot["asset_storage_recordcode"] == storage.recordcode

        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        assert asset.asset_storage_recordcode is None
        assert asset.asset_applicant_recordcode == employee
        assert asset.asset_using_location == "出库地点"

    def test_create_from_illegal_status_raises(self, storage, asset_type, employee):
        asset = _make_asset(storage, asset_type, "in_use", "OUT_SVC_ILLEGAL")
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(_outasset_payload(asset, applicant=employee))
        assert exc_info.value.error_code == "ILLEGAL_OUTASSET"

    def test_create_missing_asset_code_raises(self, storage, asset_type):
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset({})
        assert exc_info.value.error_code == "MISSING_ASSET_CODE"


@pytest.mark.django_db
class TestOutAssetLockAndUsageType:
    """F-P2-8/F-P2-9: 出库行锁409 + usage_type new→used (AC-27/30/65)"""

    def test_create_outasset_lock_timeout_raises_409(self, storage, asset_type, employee):
        """AC-30/65: 出库行锁超时 → ResourceConflictError(409) ASSET_LOCKED"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_LK409")
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("database is locked"),
        ):
            with pytest.raises(ResourceConflictError) as exc:
                OutAssetService.create_outasset(
                    _outasset_payload(asset, applicant=employee),
                    operator_jobcode=employee.employee_jobcode,
                )
        assert exc.value.status_code == 409
        assert exc.value.error_code == "ASSET_LOCKED"

    def test_create_outasset_flips_usage_type_to_used(self, storage, asset_type, employee):
        """AC-27: 出库成功后 usage_type new→used (F-P2-9); fresh query 避开 FK 缓存"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_USED")
        assert asset.usage_type == "new"
        OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee),
            operator_jobcode=employee.employee_jobcode,
        )
        fresh = Asset.objects.get(asset_code=asset.asset_code)
        assert fresh.usage_type == "used"

    def test_cancel_outasset_lock_timeout_lands_in_fail_items(self, storage, asset_type, user, employee):
        """AC-65: cancel 行锁超时 → fail_items ASSET_LOCKED,不落 INTERNAL_ERROR/500"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_CLK")
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
        )
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("database is locked"),
        ):
            result = OutAssetService.batch_delete_outasset(
                [outasset.recordcode], operator_jobcode=user.employee_jobcode
            )
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_LOCKED"


@pytest.mark.django_db
class TestCancelOutAssetService:
    """取消出库(batch_delete_outasset):快照 original_* 恢复核心契约"""

    def test_cancel_restores_original_fields(self, storage, asset_type, user, employee):
        asset = _make_asset(
            storage,
            asset_type,
            "in_store",
            "OUT_SVC_CNL_1",
            applicant=user,
            manager=user,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee, using_location="出库地点")
        )

        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode == employee
        assert asset.asset_using_location == "出库地点"
        assert asset.asset_current_status == "in_use"
        assert asset.asset_storage_recordcode is None

        result = OutAssetService.batch_delete_outasset([outasset.recordcode], operator_jobcode=user.employee_jobcode)
        assert result["success_count"] == 1

        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"
        assert asset.asset_storage_recordcode == storage
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_manager_recordcode == user
        assert asset.asset_using_location == "原地点"

    def test_cancel_from_recycled_pending_not_restore_storage(self, storage, asset_type, user, employee):
        asset = _make_asset(
            storage,
            asset_type,
            "recycled_pending",
            "OUT_SVC_CNL_2",
            applicant=user,
            manager=user,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(_outasset_payload(asset, applicant=employee))

        asset.refresh_from_db()
        assert asset.asset_storage_recordcode is None

        result = OutAssetService.batch_delete_outasset([outasset.recordcode], operator_jobcode=user.employee_jobcode)
        assert result["success_count"] == 1

        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"
        assert asset.asset_storage_recordcode is None
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_using_location == "原地点"


@pytest.mark.django_db
class TestBatchOutAssetService:
    """批量方法 fail_items 结构(CT-4 回归护栏)"""

    def test_batch_create_fail_items_structure(self, storage, asset_type, employee):
        valid = _make_asset(storage, asset_type, "in_store", "OUT_SVC_BC_OK")
        illegal = _make_asset(storage, asset_type, "in_use", "OUT_SVC_BC_ILL")
        result = OutAssetService.batch_create_outasset(
            [_outasset_payload(valid, applicant=employee), _outasset_payload(illegal, applicant=employee)]
        )
        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ILLEGAL_OUTASSET"
        valid.refresh_from_db()
        illegal.refresh_from_db()
        assert valid.asset_current_status == "in_use"  # 首条成功:批量独立性
        assert illegal.asset_current_status == "in_use"  # 失败条保持原状

    def test_batch_delete_fail_items_structure(self, storage, asset_type, employee):
        result = OutAssetService.batch_delete_outasset(
            ["OUT-NOT-EXIST-123"], operator_jobcode=employee.employee_jobcode
        )
        assert result["total"] == 1
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["id"] == "OUT-NOT-EXIST-123"
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
