"""AssetLifecycleMixin 变异杀伤补测(B-M2, T5 精确断言)

针对 asset_lifecycle_mixin.py 幸存变异体:
- ASSET_NOT_FOUND 文案逐字(broken/lost/find 三入口)
- operator 经 EmployeeSelector 解析落库(杀 →None 变异)
- 默认参数 ""→"XXXX"(描述/位置/操作人, 直写日志无归一化)
- 审计文案逐字(标记损坏/遗失/找回)
- 软删返回 dict 键值逐字 + 删除审计文案
- 批量参数: item.get 键名/默认值、max_batch_size=100
- BEQ-02 行级守卫真实调用(杀 is not None→is None)
- 事务回滚: 审计写失败不落库(杀 @transaction.atomic 删除)
"""

from unittest import mock

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    BrokenAsset,
    FoundAsset,
    LostAsset,
    RepairAsset,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestLifecycleNotFoundAndOperator:
    """不存在文案逐字 + operator 解析落库"""

    def test_mark_broken_not_found_exact(self):
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.mark_asset_broken(asset_code="NOPE", broken_reason="x", operator_jobcode="U001")
        assert exc.value.detail == "资产 NOPE 不存在"
        assert exc.value.error_code == "ASSET_NOT_FOUND"

    def test_mark_lost_not_found_exact(self):
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.mark_asset_lost(asset_code="NOPE", lost_reason="x", operator_jobcode="U001")
        assert exc.value.detail == "资产 NOPE 不存在"
        assert exc.value.error_code == "ASSET_NOT_FOUND"

    def test_find_not_found_exact(self):
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.find_and_return_asset(asset_code="NOPE", operator_jobcode="U001")
        assert exc.value.detail == "资产 NOPE 不存在"
        assert exc.value.error_code == "ASSET_NOT_FOUND"

    def test_find_no_lost_record_exact(self, asset):
        """非遗失态资产找回: NO_LOST_RECORD 文案逐字"""
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.find_and_return_asset(asset_code="A001", operator_jobcode="U001")
        assert exc.value.detail == "资产 A001 无遗失记录,无法找回"
        assert exc.value.error_code == "NO_LOST_RECORD"

    def test_mark_broken_operator_resolved_to_employee(self, asset, user):
        record = AssetLifecycleMixin.mark_asset_broken(
            asset_code="A001",
            broken_reason="摔坏",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert record.operator_employee == user

    def test_mark_lost_operator_resolved_to_employee(self, asset, user):
        record = AssetLifecycleMixin.mark_asset_lost(
            asset_code="A001",
            lost_reason="丢失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert record.operator_employee == user

    def test_find_operator_resolved_to_employee(self, asset, user):
        AssetLifecycleMixin.mark_asset_lost(
            asset_code="A001", lost_reason="丢失", operator_jobcode=user.employee_jobcode
        )
        AssetLifecycleMixin.find_and_return_asset(asset_code="A001", operator_jobcode=user.employee_jobcode)
        found = FoundAsset.objects.get(asset_recordcode=asset)
        assert found.operator_employee == user


@pytest.mark.django_db
class TestLifecycleDefaultsAndDescriptions:
    """默认参数回退(空串)与审计文案逐字"""

    def test_mark_broken_defaults_all_empty(self, asset):
        record = AssetLifecycleMixin.mark_asset_broken(asset_code="A001", broken_reason="摔坏")
        assert record.broken_description == ""
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="broken")
        assert log.operator_jobcode == ""
        assert not log.operator_name
        assert log.description == "资产标记为已损坏: 摔坏"

    def test_mark_broken_description_kept(self, asset):
        record = AssetLifecycleMixin.mark_asset_broken(
            asset_code="A001", broken_reason="摔坏", broken_description="外壳裂"
        )
        assert record.broken_description == "外壳裂"

    def test_mark_lost_defaults_all_empty(self, asset):
        record = AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        assert record.last_known_location == ""
        assert record.lost_description == ""
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="lost")
        assert log.operator_jobcode == ""
        assert not log.operator_name
        assert log.description == "资产标记为已遗失: 丢失"

    def test_mark_lost_location_kept(self, asset):
        record = AssetLifecycleMixin.mark_asset_lost(
            asset_code="A001", lost_reason="丢失", last_known_location="三楼仓库"
        )
        assert record.last_known_location == "三楼仓库"

    def test_find_defaults_and_log_exact(self, asset):
        AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        AssetLifecycleMixin.find_and_return_asset(asset_code="A001")
        found = FoundAsset.objects.get(asset_recordcode=asset)
        assert found.found_location == ""
        assert found.found_description == ""
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="found")
        assert log.description == "遗失资产找回,转入待发放状态"
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_find_location_kept(self, asset):
        AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        AssetLifecycleMixin.find_and_return_asset(asset_code="A001", found_location="前台")
        found = FoundAsset.objects.get(asset_recordcode=asset)
        assert found.found_location == "前台"


@pytest.mark.django_db
class TestSoftDeleteContract:
    """软删返回 dict 键值逐字 + 删除审计文案 + 默认操作人"""

    def _completed_repair(self, asset, user):
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status=RepairAsset.RepairStatus.COMPLETED,
            operator_employee=user,
        )

    def test_delete_repair_return_exact_and_log(self, asset, user):
        record = self._completed_repair(asset, user)
        result = AssetLifecycleMixin.delete_repair_asset(
            record.recordcode, operator_jobcode="U001", operator_name="张三"
        )
        assert result == {"recordcode": record.recordcode, "status": "deleted"}
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.description == f"维修记录删除: {record.recordcode}"
        record.refresh_from_db()
        assert record.is_deleted is True

    def test_delete_repair_default_operator_empty(self, asset, user):
        record = self._completed_repair(asset, user)
        AssetLifecycleMixin.delete_repair_asset(record.recordcode)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_delete_repair_visibility_guard_invoked(self, asset, user):
        """BEQ-02 守卫真实调用: mock 抛越权即传播(杀 is not None→is None)"""
        record = self._completed_repair(asset, user)
        with mock.patch("apps.assetmanagement.selectors.asset_selector.AssetSelector.ensure_asset_visible") as guard:
            guard.side_effect = AppValidationError(detail="不可见", error_code="ASSET_NOT_VISIBLE")
            with pytest.raises(AppValidationError):
                AssetLifecycleMixin.delete_repair_asset(record.recordcode, user=user)
        guard.assert_called_once()

    def test_delete_broken_return_exact_and_log(self, asset):
        record = AssetLifecycleMixin.mark_asset_broken(asset_code="A001", broken_reason="摔坏", operator_jobcode="U001")
        result = AssetLifecycleMixin.delete_broken_asset(record.recordcode, operator_jobcode="U001")
        assert result == {"recordcode": record.recordcode, "status": "deleted"}
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.description == f"损坏资产记录删除: {record.recordcode}"

    def test_delete_lost_return_exact_and_log(self, asset):
        record = AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失", operator_jobcode="U001")
        result = AssetLifecycleMixin.delete_lost_asset(record.recordcode, operator_jobcode="U001")
        assert result == {"recordcode": record.recordcode, "status": "deleted"}
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.description == f"遗失资产记录删除: {record.recordcode}"

    def test_delete_found_return_exact_and_log(self, asset):
        AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失", operator_jobcode="U001")
        AssetLifecycleMixin.find_and_return_asset(asset_code="A001", operator_jobcode="U001")
        found = FoundAsset.objects.get(asset_recordcode=asset)
        result = AssetLifecycleMixin.delete_found_asset(found.recordcode, operator_jobcode="U001")
        assert result == {"recordcode": found.recordcode, "status": "deleted"}
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.description == f"找回资产记录删除: {found.recordcode}"

    def test_delete_broken_default_operator_empty(self, asset):
        record = AssetLifecycleMixin.mark_asset_broken(asset_code="A001", broken_reason="摔坏")
        AssetLifecycleMixin.delete_broken_asset(record.recordcode)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_delete_lost_default_operator_empty(self, asset):
        record = AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        AssetLifecycleMixin.delete_lost_asset(record.recordcode)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_delete_lost_visibility_guard_invoked(self, asset, user):
        """BEQ-02 守卫真实调用(delete_lost 变体)"""
        record = AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        with mock.patch("apps.assetmanagement.selectors.asset_selector.AssetSelector.ensure_asset_visible") as guard:
            guard.side_effect = AppValidationError(detail="不可见", error_code="ASSET_NOT_VISIBLE")
            with pytest.raises(AppValidationError):
                AssetLifecycleMixin.delete_lost_asset(record.recordcode, user=user)
        guard.assert_called_once()

    def test_delete_found_default_operator_empty(self, asset):
        AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        AssetLifecycleMixin.find_and_return_asset(asset_code="A001")
        found = FoundAsset.objects.get(asset_recordcode=asset)
        AssetLifecycleMixin.delete_found_asset(found.recordcode)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.operator_jobcode == ""
        assert not log.operator_name


@pytest.mark.django_db
class TestBatchContracts:
    """批量创建: item 键名/默认值/max_batch_size/操作人默认"""

    @staticmethod
    def _make_asset(code: str, asset_type) -> Asset:
        return Asset.objects.create(
            asset_code=code,
            asset_name=f"资产{code}",
            asset_purchase_price=1,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_type_recordcode=asset_type,
        )

    def test_batch_broken_description_key_and_default(self, asset):
        """显式 description 透传(杀键名变异) + 缺省为空串(杀默认值变异)
        两 item 用不同资产: 同资产第二次标记走幂等路径,不产生新行"""
        self._make_asset("A002", asset.asset_type_recordcode)
        items = [
            {"asset_code": "A001", "broken_reason": "摔坏", "broken_description": "外壳裂"},
            {"asset_code": "A002", "broken_reason": "摔坏"},
        ]
        result = AssetLifecycleMixin.batch_create_broken_assets(items, operator_jobcode="U001")
        assert result["success_count"] == 2
        records = BrokenAsset.objects.order_by("id")
        assert records[0].broken_description == "外壳裂"
        assert records[1].broken_description == ""

    def test_batch_lost_description_key_and_default(self, asset):
        self._make_asset("A002", asset.asset_type_recordcode)
        items = [
            {"asset_code": "A001", "lost_reason": "丢失", "lost_description": "最后见于三楼"},
            {"asset_code": "A002", "lost_reason": "丢失"},
        ]
        result = AssetLifecycleMixin.batch_create_lost_assets(items, operator_jobcode="U001")
        assert result["success_count"] == 2
        records = LostAsset.objects.order_by("id")
        assert records[0].lost_description == "最后见于三楼"
        assert records[1].lost_description == ""

    def test_batch_broken_exceeds_limit(self):
        """批量上限 100: 101 条立即拒绝(杀 max_batch_size→101)"""
        items = [{"asset_code": f"A{i}", "broken_reason": "x"} for i in range(101)]
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.batch_create_broken_assets(items)
        assert exc.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_lost_exceeds_limit(self):
        items = [{"asset_code": f"A{i}", "lost_reason": "x"} for i in range(101)]
        with pytest.raises(AppValidationError) as exc:
            AssetLifecycleMixin.batch_create_lost_assets(items)
        assert exc.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_default_operator_empty(self, asset):
        """批删链路默认操作人为空串(batch 级默认值杀灭)"""
        result = AssetLifecycleMixin.batch_create_broken_assets([{"asset_code": "A001", "broken_reason": "摔"}])
        assert result["success_count"] == 1
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="broken")
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_batch_lost_default_operator_empty(self, asset):
        """lost 批量默认操作人为空(batch 级默认值杀灭)"""
        result = AssetLifecycleMixin.batch_create_lost_assets([{"asset_code": "A001", "lost_reason": "丢"}])
        assert result["success_count"] == 1
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="lost")
        assert log.operator_jobcode == ""
        assert not log.operator_name

    def test_batch_delete_lifecycle_default_operator_empty(self, asset):
        """batch_delete_lifecycle 默认操作人透传为空(杀批量层默认值变异)"""
        record = AssetLifecycleMixin.mark_asset_broken(asset_code="A001", broken_reason="摔坏")
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset([record.recordcode], "delete_broken_asset")
        assert result["success_count"] == 1
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="delete")
        assert log.operator_jobcode == ""
        assert not log.operator_name


@pytest.mark.django_db
class TestLifecycleAtomicRollback:
    """审计写失败全量回滚(杀 @transaction.atomic 删除)"""

    def test_mark_broken_rolls_back(self, asset):
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetLifecycleMixin.mark_asset_broken(asset_code="A001", broken_reason="摔坏")
        assert BrokenAsset.objects.count() == 0
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"

    def test_mark_lost_rolls_back(self, asset):
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        assert LostAsset.objects.count() == 0
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"

    def test_find_and_return_rolls_back(self, asset):
        AssetLifecycleMixin.mark_asset_lost(asset_code="A001", lost_reason="丢失")
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetLifecycleMixin.find_and_return_asset(asset_code="A001")
        assert FoundAsset.objects.count() == 0
        asset.refresh_from_db()
        assert asset.asset_current_status == "lost"
