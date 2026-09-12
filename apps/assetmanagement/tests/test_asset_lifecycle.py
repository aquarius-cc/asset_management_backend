"""
AssetLifecycleMixin 状态流转单元测试

覆盖 mark_asset_broken, mark_asset_lost, find_and_return_asset,
以及维修流转 create_repair_asset / complete_repair / fail_repair。
"""

from unittest import mock

import pytest
from django.db import OperationalError
from django.test import TestCase as DjangoTestCase

from apps.assetmanagement.models import (
    Asset,
    BrokenAsset,
    DamagedAsset,
    LostAsset,
    RepairAsset,
)
from apps.assetmanagement.services.asset_service import AssetService
from apps.assetmanagement.services.repair_asset_service import RepairAssetService
from core.exceptions import AppValidationError, ResourceConflictError


@pytest.mark.django_db
class TestMarkAssetBroken:
    """mark_asset_broken 测试"""

    def test_mark_broken_from_in_store(self, asset, user):
        result = AssetService.mark_asset_broken(
            asset_code="A001",
            broken_reason="硬件故障",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "broken"
        assert BrokenAsset.objects.filter(asset_recordcode=asset).exists()

    def test_mark_broken_already_broken(self, asset, user):
        """已损坏的资产再次标记应幂等返回"""
        asset.asset_current_status = "broken"
        asset.save()
        result = AssetService.mark_asset_broken(
            asset_code="A001",
            broken_reason="再次损坏",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result.asset_current_status == "broken"

    def test_mark_broken_invalid_transition(self, asset, user):
        """scrapped 状态不能标记为 broken(Service 层转 AppValidationError)"""
        asset.asset_current_status = "scrapped"
        asset.save()
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.mark_asset_broken(
                asset_code="A001",
                broken_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"

    def test_mark_broken_asset_not_found(self, user):
        """不存在的资产编码应抛 ASSET_NOT_FOUND(A6 修复)"""
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.mark_asset_broken(
                asset_code="NO_SUCH_CODE",
                broken_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"


@pytest.mark.django_db
class TestMarkAssetLost:
    """mark_asset_lost 测试"""

    def test_mark_lost_from_in_store(self, asset, user):
        result = AssetService.mark_asset_lost(
            asset_code="A001",
            lost_reason="遗失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "lost"
        assert LostAsset.objects.filter(asset_recordcode=asset).exists()

    def test_mark_lost_already_lost(self, asset, user):
        """已遗失的资产再次标记应幂等返回"""
        asset.asset_current_status = "lost"
        asset.save()
        result = AssetService.mark_asset_lost(
            asset_code="A001",
            lost_reason="再次遗失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result.asset_current_status == "lost"

    def test_mark_lost_invalid_transition(self, asset, user):
        """scrapped 状态不能标记为 lost(Service 层转 AppValidationError)"""
        asset.asset_current_status = "scrapped"
        asset.save()
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.mark_asset_lost(
                asset_code="A001",
                lost_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"

    def test_mark_lost_asset_not_found(self, user):
        """不存在的资产编码应抛 ASSET_NOT_FOUND(A6 修复)"""
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.mark_asset_lost(
                asset_code="NO_SUCH_CODE",
                lost_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"


@pytest.mark.django_db
class TestFindAndReturnAsset:
    """find_and_return_asset 测试"""

    def _make_lost_asset(self, asset, user):
        """辅助:将资产标记为 lost 并创建 LostAsset 记录"""
        asset.asset_current_status = "lost"
        asset.save()
        return LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="遗失",
        )

    def test_find_and_return_success(self, asset, user):
        self._make_lost_asset(asset, user)
        result = AssetService.find_and_return_asset(
            asset_code="A001",
            found_location="仓库A",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "recycled_pending"

    def test_find_and_return_no_lost_record(self, asset, user):
        """没有 LostAsset 记录时应返回业务错误 400(NO_LOST_RECORD),而非 500"""
        asset.asset_current_status = "lost"
        asset.save()
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.find_and_return_asset(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "NO_LOST_RECORD"

    def test_find_and_return_asset_not_found(self, user):
        """资产不存在时应返回业务错误 400(ASSET_NOT_FOUND),而非 500"""
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.find_and_return_asset(
                asset_code="NON_EXISTENT",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_find_and_return_repeat_calls(self, asset, user):
        """重复找回(资产已非 lost)应返回业务错误 400,而非 500 InvalidTransitionError"""
        self._make_lost_asset(asset, user)
        AssetService.find_and_return_asset(
            asset_code="A001",
            found_location="仓库A",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.find_and_return_asset(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"


@pytest.mark.django_db
class TestRepairAsset:
    """create_repair_asset 测试(维修唯一实现 RepairAssetService)"""

    def _make_broken_asset(self, asset, user):
        """辅助:将资产标记为 broken"""
        asset.asset_current_status = "broken"
        asset.save()
        return asset

    def test_repair_asset_success(self, asset, user):
        self._make_broken_asset(asset, user)
        result = RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert isinstance(result, RepairAsset)
        asset.refresh_from_db()
        assert asset.asset_current_status == "repairing"

    def test_repair_asset_invalid_transition(self, asset, user):
        """in_store 状态不能送修"""
        with pytest.raises(AppValidationError):
            RepairAssetService.create_repair_asset(
                asset_code="A001",
                repair_reason="x",
                repair_date="2024-06-01",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )

    def test_repair_asset_duplicate_in_progress_rejected(self, asset, user):
        """已存在 in_progress 维修记录时不可重复送修"""
        self._make_broken_asset(asset, user)
        RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )
        with pytest.raises(AppValidationError) as exc:
            RepairAssetService.create_repair_asset(
                asset_code="A001",
                repair_reason="主板故障",
                repair_date="2024-06-01",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc.value.error_code == "DUPLICATE_REPAIR_IN_PROGRESS"

    def test_repair_asset_lock_timeout_rejected(self, asset, user):
        """select_for_update 锁超时返回 409 ASSET_LOCKED"""
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("database is locked"),
        ):
            with pytest.raises(ResourceConflictError) as exc:
                RepairAssetService.create_repair_asset(
                    asset_code="A001",
                    repair_reason="主板故障",
                    repair_date="2024-06-01",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        assert exc.value.error_code == "ASSET_LOCKED"


@pytest.mark.django_db
class TestRepairDone:
    """complete_repair 测试(维修唯一实现 RepairAssetService)"""

    def _make_repairing_asset(self, asset, user):
        """辅助:将资产标记为 repairing 并创建维修记录"""
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_repair_done_success(self, asset, user):
        self._make_repairing_asset(asset, user)
        result = RepairAssetService.complete_repair(
            asset_code="A001",
            actual_return_date="2024-06-10",
            physical_grade_after="良好",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.repair_status == "completed"
        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"
        assert asset.physical_grade == "良好"

    def test_repair_done_no_in_progress_record(self, asset, user):
        """没有进行中的维修记录时应报错"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError):
            RepairAssetService.complete_repair(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )

    def test_repair_done_registers_notification_on_commit(self, asset, user):
        """维修完成注册 on_commit 通知:提交前不发送,提交后发送(B6)"""
        self._make_repairing_asset(asset, user)
        with mock.patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
                RepairAssetService.complete_repair(
                    asset_code="A001",
                    actual_return_date="2024-06-10",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
                mock_notify.assert_not_called()
            assert len(callbacks) == 1
            callbacks[0]()
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["notification_type"] == "status_change"
        assert "维修已完成" in kwargs["message"]
        assert kwargs["priority"] == "medium"


@pytest.mark.django_db
class TestRepairFailed:
    """fail_repair 测试(维修唯一实现 RepairAssetService)"""

    def _make_repairing_asset(self, asset, user):
        """辅助:将资产标记为 repairing 并创建维修记录"""
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_repair_failed_success(self, asset, user):
        self._make_repairing_asset(asset, user)
        result = RepairAssetService.fail_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.repair_status == "failed"
        asset.refresh_from_db()
        assert asset.asset_current_status == "damaged"
        damaged = DamagedAsset.objects.get(asset_recordcode=asset)
        assert damaged.original_status == "repairing"

    def test_repair_failed_no_in_progress_record(self, asset, user):
        """没有进行中的维修记录时应报错"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError):
            RepairAssetService.fail_repair(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )

    def test_repair_failed_registers_notification_on_commit(self, asset, user):
        """维修失败注册 on_commit 通知:提交前不发送,提交后发送(B6)"""
        self._make_repairing_asset(asset, user)
        with mock.patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
                RepairAssetService.fail_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
                mock_notify.assert_not_called()
            assert len(callbacks) == 1
            callbacks[0]()
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["notification_type"] == "status_change"
        assert "维修失败" in kwargs["message"]
        assert kwargs["priority"] == "high"


@pytest.mark.django_db
class TestBatchCreateBrokenAssets:
    """batch_create_broken_assets 批量损坏登记测试（R3-04 载荷键统一为 asset_code）"""

    def test_batch_create_broken_success(self, asset, user):
        items = [
            {
                "row_number": 1,
                "asset_code": "A001",
                "broken_reason": "屏幕破裂",
                "broken_description": "批量登记",
            }
        ]
        result = AssetService.batch_create_broken_assets(
            items=items,
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result["total"] == 1
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"
        assert BrokenAsset.objects.filter(asset_recordcode=asset).exists()

    def test_batch_create_broken_mixed_results(self, asset, user):
        """多条条目时逐条执行且状态独立"""
        items = [
            {"row_number": 1, "asset_code": "A001", "broken_reason": "碰撞损坏"},
            {"row_number": 2, "asset_code": "A001", "broken_reason": "再次登记应幂等"},
        ]
        result = AssetService.batch_create_broken_assets(
            items=items,
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["fail_count"] == 0
        assert BrokenAsset.objects.filter(asset_recordcode=asset).count() == 1
