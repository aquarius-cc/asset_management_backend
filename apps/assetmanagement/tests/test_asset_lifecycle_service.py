"""资产生命周期批量删除 Service 层测试(#17 §1.2 分层收敛)

覆盖:
- batch_delete_lifecycle_asset: broken/lost/found 三入口, 合成成功+NOT_FOUND 分类
- batch_delete_repair_asset: 成功 / REPAIR_IN_PROGRESS 透传 / NOT_FOUND
- 批大小上限 BATCH_SIZE_EXCEEDED(与 test_recycle_asset_service.py 同语义: 抛异常而非 fail_items)
"""

import pytest

from apps.assetmanagement.models import (
    AssetOperationLog,
    BrokenAsset,
    FoundAsset,
    LostAsset,
    RepairAsset,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.exceptions import AppValidationError


NOT_FOUND_ID = "NO_SUCH_RECORDCODE"


@pytest.mark.django_db
class TestBatchDeleteLifecycleAsset:
    """批量删除损坏/遗失/找回记录"""

    def test_broken_mixed_success_and_not_found(self, broken_asset):
        """合成场景: 1 条成功(软删+审计) + 1 条不存在(NOT_FOUND), 互不影响"""
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            [broken_asset.recordcode, NOT_FOUND_ID],
            "delete_broken_asset",
            operator_jobcode="OP999",
            operator_name="测试操作员",
        )

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["success_ids"] == [broken_asset.recordcode]
        assert result["fail_items"] == [
            {"id": NOT_FOUND_ID, "error_code": "NOT_FOUND", "error_message": f"记录 {NOT_FOUND_ID} 不存在"}
        ]

        assert not BrokenAsset.objects.filter(recordcode=broken_asset.recordcode, is_deleted=False).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description__startswith="损坏资产记录删除",
        ).exists()

    @pytest.mark.parametrize(
        ("delete_method", "fixture_name"),
        [("delete_lost_asset", "lost_asset"), ("delete_found_asset", "found_asset")],
    )
    def test_parameterized_success(self, request, delete_method, fixture_name):
        """lost/found 与 broken 同构: 成功软删 + NOT_FOUND 分类"""
        record = request.getfixturevalue(fixture_name)
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            [record.recordcode, NOT_FOUND_ID],
            delete_method,
            operator_jobcode="OP999",
            operator_name="测试操作员",
        )

        assert result["success_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
        model = LostAsset if fixture_name == "lost_asset" else FoundAsset
        assert not model.objects.filter(recordcode=record.recordcode, is_deleted=False).exists()

    def test_exceeds_limit_raises(self):
        """101 条 → 抛 BATCH_SIZE_EXCEEDED(前置校验, 不落 fail_items, 与全仓 batch_delete 一致)"""
        ids = [f"R{i}" for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            AssetLifecycleMixin.batch_delete_lifecycle_asset(ids, "delete_broken_asset")
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestBatchDeleteRepairAsset:
    """批量删除维修记录"""

    def test_success_soft_deletes_with_audit(self, repair_asset):
        repair_asset.repair_status = RepairAsset.RepairStatus.COMPLETED
        repair_asset.save(update_fields=["repair_status", "updated_at"])
        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [repair_asset.recordcode], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["success_count"] == 1
        assert not RepairAsset.objects.filter(recordcode=repair_asset.recordcode, is_deleted=False).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=repair_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description__startswith="维修记录删除",
        ).exists()

    def test_in_progress_error_code_preserved(self, repair_asset):
        """进行中的维修记录: REPAIR_IN_PROGRESS 原样进 fail_items(不被 NOT_FOUND/兜底遮蔽)"""
        repair_asset.repair_status = RepairAsset.RepairStatus.IN_PROGRESS
        repair_asset.save(update_fields=["repair_status", "updated_at"])

        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [repair_asset.recordcode], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "REPAIR_IN_PROGRESS"
        assert result["fail_items"][0]["error_message"] == (
            f"维修记录 {repair_asset.recordcode} 正在进行中,不可删除"
        )

    def test_not_found_classified(self):
        """不存在的维修记录: NOT_FOUND(收敛前落入 INTERNAL_ERROR, 行为变更已登记 #17)"""
        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [NOT_FOUND_ID], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["fail_count"] == 1
        assert result["fail_items"][0] == {
            "id": NOT_FOUND_ID,
            "error_code": "NOT_FOUND",
            "error_message": f"记录 {NOT_FOUND_ID} 不存在",
        }
