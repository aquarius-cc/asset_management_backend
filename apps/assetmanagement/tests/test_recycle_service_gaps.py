"""RecycleAssetService 变异杀伤补测(B-M2, T5 精确断言)

针对 recycle_asset_service.py 幸存变异体:
- 错误文案/错误码逐字(创建/更新/批删/重新发放)
- 入参归一化: storage/person 字符串→对象、operator 回填优先级
- 回收标记损坏/遗失: 子记录字段、触发词、操作人回退链
- 更新白名单与审计快照 before_data
- 批量删除: 字段恢复、触发词、批量上限
- 事务回滚: 审计写失败不落库(CT-1)
"""

from datetime import date
from unittest import mock

import pytest

from apps.assetmanagement.models import (
    AssetOperationLog,
    BrokenAsset,
    LostAsset,
    OutAsset,
    RecycleAsset,
)
from apps.assetmanagement.services.recycle_asset_service import RecycleAssetService
from core.exceptions import AppValidationError


@pytest.fixture
def recycle_payload(outasset, storage, user):
    """复用 conftest outasset(资产已 in_use 且带申请人/保管人/使用地点)"""
    return {
        "outasset_recordcode": outasset,
        "recycle_asset_storage": storage,
        "recycle_asset_recycle_person_jobcode": user,
        "recycle_asset_date": date(2024, 7, 1),
    }


@pytest.mark.django_db
class TestRecycleErrorDetails:
    """创建/更新路径错误文案与错误码逐字"""

    def test_missing_outasset_recordcode_detail(self, storage, user):
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.create_recycle_asset({"recycle_asset_storage": storage})
        assert exc.value.detail == "缺少出库记录编码"
        assert exc.value.error_code == "MISSING_OUTASSET_RECORDCODE"

    def test_outasset_not_found_detail(self, storage, user):
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.create_recycle_asset(
                {"outasset_recordcode": "OUT-NOPE", "recycle_asset_storage": storage}
            )
        assert exc.value.detail == "出库记录 OUT-NOPE 不存在"
        assert exc.value.error_code == "OUTASSET_NOT_FOUND"

    def test_invalid_status_detail(self, outasset, storage, user):
        """in_store 资产不能回收: 文案逐字"""
        outasset.asset_recordcode.asset_current_status = "in_store"
        outasset.asset_recordcode.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.create_recycle_asset({"outasset_recordcode": outasset})
        assert exc.value.detail == "资产当前状态为 in_store,不能回收"

    def test_update_not_found_detail(self):
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.update_recycle_asset("RC-NOPE", {"recycle_asset_date": "2024-08-01"})
        assert exc.value.detail == "回收记录 RC-NOPE 不存在"
        assert exc.value.error_code == "RECYCLE_ASSET_NOT_FOUND"

    def test_update_field_not_allowed_detail_and_code(self, recycle_payload):
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        # before_data 的 getattr 先于白名单检查,须传真实存在但不在白名单的字段
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.update_recycle_asset(
                created.recordcode, {"recordcode": "HACKED"}, operator_jobcode="U001", operator_name="测试"
            )
        assert exc.value.detail == "不允许修改字段: recordcode"
        assert exc.value.error_code == "FIELD_NOT_ALLOWED"

    def test_update_before_data_snapshot(self, recycle_payload):
        """更新审计快照: before_data 记录修改前原值"""
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        RecycleAssetService.update_recycle_asset(
            created.recordcode,
            {"recycle_asset_date": date(2024, 8, 15)},
            operator_jobcode="U001",
            operator_name="测试",
        )
        log = AssetOperationLog.objects.filter(operation_type="update").order_by("-id").first()
        # JSONField 将 date 序列化为 ISO 字符串
        assert log.before_data == {"recycle_asset_date": "2024-07-01"}
        assert log.after_data == {"recycle_asset_date": "2024-08-15"}


@pytest.mark.django_db
class TestRecycleNormalization:
    """入参归一化与 operator 回填优先级"""

    def test_string_refs_resolved_to_objects(self, outasset, storage, user):
        """storage/person 传字符串: 对象化并落库到资产"""
        payload = {
            "outasset_recordcode": outasset.recordcode,
            "recycle_asset_storage": storage.storage_code,
            "recycle_asset_recycle_person_jobcode": user.employee_jobcode,
            "recycle_asset_date": date(2024, 7, 1),
        }
        RecycleAssetService.create_recycle_asset(payload)
        outasset.asset_recordcode.refresh_from_db()
        assert outasset.asset_recordcode.asset_storage_recordcode == storage
        assert outasset.asset_recordcode.asset_entry_person_recordcode == user

    def test_operator_filled_from_recycle_person(self, outasset, storage, user):
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_recycle_person_jobcode": user,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload)
        assert created.operator_employee == user

    def test_operator_filled_from_jobcode_when_no_person(self, outasset, employee):
        """无 recycle_person 时从 operator_jobcode 解析操作人"""
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload, operator_jobcode=employee.employee_jobcode)
        assert created.operator_employee == employee

    def test_person_wins_over_operator_jobcode(self, outasset, user, employee):
        """recycle_person 与 operator_jobcode 并存: 操作人取 person(不被 jobcode 覆写)"""
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_recycle_person_jobcode": user,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload, operator_jobcode=employee.employee_jobcode)
        assert created.operator_employee == user


@pytest.mark.django_db
class TestBrokenLostFinalize:
    """回收时标记损坏/遗失: 子记录字段/触发词/操作人回退链"""

    def test_broken_with_explicit_reason(self, recycle_payload, user):
        recycle_payload["is_broken"] = True
        recycle_payload["broken_reason"] = "屏幕碎裂"
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        record = BrokenAsset.objects.get(asset_recordcode=created.asset_recordcode)
        assert record.broken_reason == "屏幕碎裂"
        assert record.broken_description == f"回收时发现损坏,回收记录: {created.recordcode}"
        created.asset_recordcode.refresh_from_db()
        assert created.asset_recordcode.asset_current_status == "broken"

    def test_broken_fallback_reason_when_absent(self, recycle_payload):
        """未传 broken_reason: 回退文案逐字"""
        recycle_payload["is_broken"] = True
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        record = BrokenAsset.objects.get(asset_recordcode=created.asset_recordcode)
        assert record.broken_reason == "回收时发现损坏"

    def test_lost_fallback_reason_and_description(self, recycle_payload):
        """未传 lost_reason: 回退文案与描述逐字"""
        recycle_payload["is_lost"] = True
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        record = LostAsset.objects.get(asset_recordcode=created.asset_recordcode)
        assert record.lost_reason == "回收时发现遗失"
        assert record.lost_description == f"回收时发现遗失,回收记录: {created.recordcode}"
        created.asset_recordcode.refresh_from_db()
        assert created.asset_recordcode.asset_current_status == "lost"

    def test_broken_state_change_trigger_exact(self, recycle_payload, user):
        """损坏二次转换: 状态日志触发词/操作人回退逐字"""
        recycle_payload["is_broken"] = True
        RecycleAssetService.create_recycle_asset(recycle_payload)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 recycled_pending 变更为 broken (触发: recycle_mark_broken)"
        # 无显式 operator_jobcode: 回退到 recycle_person 工号
        assert log.operator_jobcode == user.employee_jobcode
        assert log.operator_name == ""

    def test_lost_state_change_trigger_exact(self, recycle_payload):
        recycle_payload["is_lost"] = True
        RecycleAssetService.create_recycle_asset(recycle_payload)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 recycled_pending 变更为 lost (触发: recycle_mark_lost)"

    def test_explicit_operator_wins_over_fallback(self, recycle_payload, user, employee):
        """显式 operator_jobcode 优先于 person 回退"""
        recycle_payload["is_broken"] = True
        RecycleAssetService.create_recycle_asset(
            recycle_payload, operator_jobcode=employee.employee_jobcode, operator_name="张三"
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.operator_jobcode == employee.employee_jobcode
        assert log.operator_name == "张三"

    def test_broken_invalid_transition_error_code(self, recycle_payload):
        """二次转换非法: INVALID_STATE_TRANSITION 错误码精确"""
        from apps.assetmanagement.state_machine import InvalidTransitionError

        recycle_payload["is_broken"] = True
        with mock.patch("apps.assetmanagement.services.recycle_asset_service.AssetFSM.mark_broken") as mk:
            mk.side_effect = InvalidTransitionError("boom")
            with pytest.raises(AppValidationError) as exc:
                RecycleAssetService.create_recycle_asset(recycle_payload)
        assert exc.value.error_code == "INVALID_STATE_TRANSITION"

    def test_recycle_invalid_transition_error_code(self, outasset):
        """主转换非法(in_store 不可回收): 错误码精确"""
        outasset.asset_recordcode.asset_current_status = "broken"
        outasset.asset_recordcode.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.create_recycle_asset({"outasset_recordcode": outasset})
        assert exc.value.error_code == "INVALID_ASSET_STATUS_FOR_RECYCLE"


@pytest.mark.django_db
class TestBatchDeleteRecycle:
    """批量删除: 文案/恢复/触发词/上限"""

    def test_batch_delete_not_found_detail(self):
        result = RecycleAssetService.batch_delete_recycle_asset(["RC-GONE"])
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
        assert result["fail_items"][0]["error_message"] == "回收记录 RC-GONE 不存在"

    def test_batch_delete_wrong_status_detail(self, recycle_asset):
        """资产未处于 recycled_pending: 拒删文案逐字"""
        result = RecycleAssetService.batch_delete_recycle_asset([recycle_asset.recordcode])
        assert result["fail_items"][0]["error_code"] == "STATUS_NOT_ALLOWED"
        assert result["fail_items"][0]["error_message"] == "关联资产当前状态为 in_use,不允许删除回收记录"

    def test_batch_delete_restores_fields_and_trigger(self, outasset, storage, user):
        """批删回收记录: 资产回 in_use 并从出库记录恢复申请人/保管人/使用地点"""
        # OutAsset 记录侧补齐可恢复字段(夹具只写在 Asset 侧,恢复源在 OutAsset 侧)
        outasset.outasset_applicant_recordcode = user
        outasset.outasset_manager_recordcode = user
        outasset.outasset_using_location = "使用地点"
        outasset.save()
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_storage": storage,
            "recycle_asset_recycle_person_jobcode": user,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload)
        asset = created.asset_recordcode
        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"
        assert asset.asset_applicant_recordcode is None  # 回收时已清空

        result = RecycleAssetService.batch_delete_recycle_asset([created.recordcode], operator_jobcode="U001")
        assert result["success_count"] == 1
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_manager_recordcode == user
        assert asset.asset_using_location == "使用地点"
        log = AssetOperationLog.objects.filter(asset_code="A001", operation_type="state_change").order_by("-id").first()
        assert log.description == "状态从 recycled_pending 变更为 in_use (触发: cancel_recycle)"

    def test_batch_delete_cancel_invalid_transition_code(self, recycle_asset, storage, user):
        from apps.assetmanagement.state_machine import InvalidTransitionError

        recycle_asset.asset_recordcode.asset_current_status = "recycled_pending"
        recycle_asset.asset_recordcode.save(update_fields=["asset_current_status"])
        with mock.patch("apps.assetmanagement.services.recycle_asset_service.AssetFSM.cancel_recycle") as cr:
            cr.side_effect = InvalidTransitionError("boom")
            result = RecycleAssetService.batch_delete_recycle_asset([recycle_asset.recordcode])
        assert result["fail_items"][0]["error_code"] == "INVALID_STATE_TRANSITION"

    def test_batch_delete_exceeds_limit(self):
        """批量上限 100: 101 条立即拒绝(BATCH_SIZE_EXCEEDED, 不进逐条流程)"""
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.batch_delete_recycle_asset([f"RC-{i}" for i in range(101)])
        assert exc.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestRecycleMutantKillsRound2:
    """第二轮定点杀伤: 显式遗失原因/Storage 对象直通/重新发放参数/回滚"""

    def test_lost_with_explicit_reason(self, recycle_payload):
        """显式 lost_reason: 子记录落显式值(杀 pop 键名/None 变异)"""
        recycle_payload["is_lost"] = True
        recycle_payload["lost_reason"] = "遗失在仓库"
        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        record = LostAsset.objects.get(asset_recordcode=created.asset_recordcode)
        assert record.lost_reason == "遗失在仓库"
        assert record.lost_description == f"回收时发现遗失,回收记录: {created.recordcode}"

    def test_storage_object_passthrough(self, outasset, storage, user):
        """storage 传对象: 直通落库(杀 and→or 与 filter→None 变异)"""
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_storage": storage,
            "recycle_asset_date": date(2024, 7, 1),
        }
        RecycleAssetService.create_recycle_asset(payload)
        outasset.asset_recordcode.refresh_from_db()
        assert outasset.asset_recordcode.asset_storage_recordcode == storage

    def test_reissue_outasset_payload_exact(self, outasset, storage, user):
        """重新发放: 出库参数逐字(type/number/description)"""
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_storage": storage,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload)
        with mock.patch("apps.assetmanagement.services.out_asset_service.OutAssetService.create_outasset") as mk:
            RecycleAssetService.reissue_recycle_asset(created.recordcode, operator_jobcode="U001")
        data = mk.call_args.kwargs["outasset_data"]
        assert data["outasset_type"] == OutAsset.OutassetType.REISSUE
        assert data["outasset_number"] == 1
        assert data["outasset_description"] == f"重新发放 - 原回收记录: {created.recordcode}"

    def test_reissue_wrong_status_detail(self, outasset, storage, user):
        """非 recycled_pending 重新发放: 文案逐字"""
        payload = {
            "outasset_recordcode": outasset,
            "recycle_asset_storage": storage,
            "recycle_asset_date": date(2024, 7, 1),
        }
        created = RecycleAssetService.create_recycle_asset(payload)
        created.asset_recordcode.asset_current_status = "broken"
        created.asset_recordcode.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc:
            RecycleAssetService.reissue_recycle_asset(created.recordcode)
        assert exc.value.detail == "资产当前状态为 broken,只有已回收待发放的资产才能重新发放"
        assert exc.value.error_code == "INVALID_ASSET_STATUS_FOR_REISSUE"

    def test_create_recycle_rolls_back_on_state_log_failure(self, recycle_payload):
        """回收中途审计写失败 → 回收记录不落库,资产仍 in_use(杀 atomic 删除)"""
        from apps.assetmanagement.audit import AuditLogger

        # 正常回收路径的审计调用是 log_asset_recycle(_do_recycle_asset_update :256)
        with mock.patch.object(AuditLogger, "log_asset_recycle", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                RecycleAssetService.create_recycle_asset(recycle_payload)
        assert RecycleAsset.objects.count() == 0
        recycle_payload["outasset_recordcode"].asset_recordcode.refresh_from_db()
        assert recycle_payload["outasset_recordcode"].asset_recordcode.asset_current_status == "in_use"

    def test_update_recycle_rolls_back_on_audit_failure(self, recycle_payload):
        """更新中途审计写失败 → 字段不变(杀 atomic 删除)"""
        from apps.assetmanagement.audit import AuditLogger

        created = RecycleAssetService.create_recycle_asset(recycle_payload)
        with mock.patch.object(AuditLogger, "log_asset_update", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                RecycleAssetService.update_recycle_asset(
                    created.recordcode,
                    {"recycle_asset_date": date(2024, 9, 1)},
                    operator_jobcode="U001",
                    operator_name="测试",
                )
        created.refresh_from_db()
        assert created.recycle_asset_date == date(2024, 7, 1)
