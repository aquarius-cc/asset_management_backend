"""RepairAssetService 断言缺口补测(B-M2 变异测试 M2 阶段)

针对静态分析识别的高危幸存分支做精确断言补强(T5):
- complete_repair 空参回退: actual_return_date→当天 / physical_grade_after→None
- create_repair_asset: 空 repair_description→None / 空 operator_jobcode→operator=None
- fail_repair: DamagedAsset 落库字段(damaged_asset_number/original_status)
- 三路径操作日志: operation_type 与 description 关键内容
- 完成/失败通知: title 与 related_url 内容
"""

import pytest
from django.utils import timezone

from apps.assetmanagement.models import AssetOperationLog, DamagedAsset, RepairAsset
from apps.assetmanagement.services.repair_asset_service import RepairAssetService
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestRepairDefaultsAndFallbacks:
    """空参回退分支(默认值 or 逻辑)断言"""

    def _make_repairing_asset(self, asset, user):
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_repair_done_defaults_return_date_to_today(self, asset, user):
        """complete_repair 未传 actual_return_date 时回填当天日期"""
        self._make_repairing_asset(asset, user)
        result = RepairAssetService.complete_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.actual_return_date == timezone.now().date()

    def test_repair_done_empty_strings_fall_back(self, asset, user):
        """complete_repair 传空串等同未传: 日期回填当天, 成色不更新"""
        self._make_repairing_asset(asset, user)
        result = RepairAssetService.complete_repair(
            asset_code="A001",
            actual_return_date="",
            physical_grade_after="",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.actual_return_date == timezone.now().date()
        assert result.physical_grade_after is None

    def test_repair_done_keeps_grade_when_not_provided(self, asset, user):
        """complete_repair 未传成色时资产原 physical_grade 不变(显式设值,与模型默认解耦)"""
        asset.physical_grade = "poor"
        asset.save(update_fields=["physical_grade"])
        self._make_repairing_asset(asset, user)
        RepairAssetService.complete_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        asset.refresh_from_db()
        assert asset.physical_grade == "poor"

    def test_create_repair_empty_description_stores_none(self, asset, user):
        """create_repair_asset 空 repair_description 落库为 None"""
        asset.asset_current_status = "broken"
        asset.save()
        result = RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            repair_description="",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.repair_description is None

    def test_create_repair_without_operator_jobcode(self, asset, user):
        """create_repair_asset 空 operator_jobcode 时操作人为 None 仍成功"""
        asset.asset_current_status = "broken"
        asset.save()
        result = RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
        )
        assert isinstance(result, RepairAsset)
        assert result.operator_employee is None


@pytest.mark.django_db
class TestRepairAuditTrail:
    """三路径操作日志与失败落库字段断言"""

    def _make_repairing_asset(self, asset, user):
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_create_repair_writes_operation_log(self, asset, user):
        """送修写 REPAIR 操作日志, 含原因"""
        asset.asset_current_status = "broken"
        asset.save()
        RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair")
        assert "主板故障" in log.description
        assert log.operator_jobcode == user.employee_jobcode

    def test_repair_done_writes_operation_log(self, asset, user):
        """完成维修写 REPAIR_DONE 操作日志"""
        self._make_repairing_asset(asset, user)
        RepairAssetService.complete_repair(
            asset_code="A001",
            actual_return_date="2024-06-10",
            physical_grade_after="良好",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert AssetOperationLog.objects.filter(asset_code="A001", operation_type="repair_done").exists()

    def test_repair_failed_writes_operation_log(self, asset, user):
        """维修失败写 REPAIR_FAILED 操作日志"""
        self._make_repairing_asset(asset, user)
        RepairAssetService.fail_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert AssetOperationLog.objects.filter(asset_code="A001", operation_type="repair_failed").exists()

    def test_repair_failed_creates_damaged_payload(self, asset, user):
        """维修失败生成待报废记录: 数量 1 + 原状态 repairing"""
        self._make_repairing_asset(asset, user)
        RepairAssetService.fail_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        damaged = DamagedAsset.objects.get(asset_recordcode=asset)
        assert damaged.damaged_asset_number == 1
        assert damaged.original_status == "repairing"

    def test_repair_done_notification_payload(self, asset, user):
        """完成通知: 标题与 related_url 指向资产详情"""
        from unittest import mock

        from django.test import TestCase as DjangoTestCase

        self._make_repairing_asset(asset, user)
        with mock.patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=True) as callbacks:
                RepairAssetService.complete_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        assert callbacks
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["title"] == "资产维修完成通知"
        assert kwargs["related_url"] == "/main/assetdetails/A001"


@pytest.mark.django_db
class TestRepairMutantKills:
    """变异体精确断言杀伤(T5 精确断言): 审计字段/错误信息/默认回退/通知载荷"""

    def _make_broken(self, asset):
        asset.asset_current_status = "broken"
        asset.save()

    def _make_repairing(self, asset, user):
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_create_duplicate_exact_warning_and_detail(self, asset, user, caplog):
        """重复送修: 日志与错误文案逐字断言"""
        import logging

        self._make_broken(asset)
        RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )
        with caplog.at_level(logging.WARNING):
            with pytest.raises(AppValidationError) as exc:
                RepairAssetService.create_repair_asset(
                    asset_code="A001",
                    repair_reason="主板故障",
                    repair_date="2024-06-01",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        assert exc.value.detail == "资产 A001 已有进行中的维修记录,不可重复送修"
        assert any(
            r.getMessage() == f"重复送修被拒绝: asset=A001, operator={user.employee_jobcode}" for r in caplog.records
        )

    def test_create_invalid_transition_error_code(self, asset, user):
        """in_store 送修: INVALID_STATE_TRANSITION 错误码精确断言"""
        with pytest.raises(AppValidationError) as exc:
            RepairAssetService.create_repair_asset(
                asset_code="A001",
                repair_reason="x",
                repair_date="2024-06-01",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc.value.error_code == "INVALID_STATE_TRANSITION"

    def test_create_operator_resolved_from_jobcode(self, asset, user):
        """送修成功: 操作人由 jobcode 解析落库"""
        self._make_broken(asset)
        result = RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result.operator_employee == user

    def test_create_state_change_log_exact(self, asset, user):
        """送修状态变更日志: before/after/触发词逐字断言"""
        self._make_broken(asset)
        RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 broken 变更为 repairing (触发: repair)"

    def test_create_operation_log_exact_description(self, asset, user):
        """送修操作日志 description 逐字断言"""
        self._make_broken(asset)
        RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair")
        assert log.description == "Asset sent for repair: 主板故障"

    def test_create_default_params_fallback(self, asset, user):
        """全默认参调用: 描述落 None, 日志操作人为空串"""
        self._make_broken(asset)
        result = RepairAssetService.create_repair_asset(
            asset_code="A001", repair_reason="主板故障", repair_date="2024-06-01"
        )
        assert result.repair_description is None
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair")
        assert log.operator_jobcode == ""
        assert log.operator_name == ""

    def test_complete_no_in_progress_exact(self, asset, user):
        """完成维修无记录: detail 与 error_code 逐字断言"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError) as exc:
            RepairAssetService.complete_repair(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc.value.detail == "该资产没有进行中的维修记录"
        assert exc.value.error_code == "NO_IN_PROGRESS_REPAIR"

    def test_complete_state_change_log_exact(self, asset, user):
        """完成维修状态变更日志逐字断言"""
        self._make_repairing(asset, user)
        RepairAssetService.complete_repair(
            asset_code="A001",
            actual_return_date="2024-06-10",
            physical_grade_after="良好",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 repairing 变更为 recycled_pending (触发: repair_done)"

    def test_complete_operation_log_exact_description(self, asset, user):
        """完成维修操作日志 description 逐字断言"""
        self._make_repairing(asset, user)
        RepairAssetService.complete_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair_done")
        assert log.description == "Repair completed, asset moved to recycled_pending"

    def test_complete_grade_after_recorded_on_repair_record(self, asset, user):
        """完成维修: 维修记录落 physical_grade_after"""
        self._make_repairing(asset, user)
        result = RepairAssetService.complete_repair(
            asset_code="A001",
            physical_grade_after="良好",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.physical_grade_after == "良好"

    def test_complete_default_operator_fallback(self, asset, user):
        """完成维修省略操作人: 全部日志操作人为空(直写日志无归一化,空串原样落库)"""
        self._make_repairing(asset, user)
        RepairAssetService.complete_repair(asset_code="A001")
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.operator_jobcode == ""
        assert not log.operator_name
        done_log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair_done")
        assert not done_log.operator_name

    def test_complete_notification_message_exact(self, asset, user):
        """完成通知 message 逐字断言"""
        from unittest import mock

        from django.test import TestCase as DjangoTestCase

        self._make_repairing(asset, user)
        with mock.patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                RepairAssetService.complete_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["message"] == "资产 A001 维修已完成,已转入待发放状态"

    def test_fail_no_in_progress_exact(self, asset, user):
        """维修失败无记录: detail 与 error_code 逐字断言"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError) as exc:
            RepairAssetService.fail_repair(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        assert exc.value.detail == "该资产没有进行中的维修记录"
        assert exc.value.error_code == "NO_IN_PROGRESS_REPAIR"

    def test_fail_state_change_log_exact(self, asset, user):
        """维修失败状态变更日志逐字断言"""
        self._make_repairing(asset, user)
        RepairAssetService.fail_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 repairing 变更为 damaged (触发: repair_failed)"

    def test_fail_operation_log_exact_description(self, asset, user):
        """维修失败操作日志 description 逐字断言"""
        self._make_repairing(asset, user)
        RepairAssetService.fail_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair_failed")
        assert log.description == "Repair failed, asset moved to damaged"

    def test_fail_notification_payload_exact(self, asset, user):
        """失败通知 title/message/related_url 逐字断言"""
        from unittest import mock

        from django.test import TestCase as DjangoTestCase

        self._make_repairing(asset, user)
        with mock.patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                RepairAssetService.fail_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["title"] == "资产维修失败通知"
        assert kwargs["message"] == "资产 A001 维修失败,已转入待报废状态"
        assert kwargs["related_url"] == "/main/assetdetails/A001"

    def test_fail_default_operator_fallback(self, asset, user):
        """维修失败省略操作人: 日志操作人为空(jobcode 空串/name 归一化为 None)"""
        self._make_repairing(asset, user)
        RepairAssetService.fail_repair(asset_code="A001")
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.operator_jobcode == ""
        assert not log.operator_name


@pytest.mark.django_db
class TestRepairTransactionAtomicity:
    """中途失败全量回滚断言(CT-1 回滚覆盖, 杀伤 @transaction.atomic 删除变异)"""

    def _make_repairing(self, asset, user):
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_create_repair_rolls_back_on_log_failure(self, asset, user):
        """送修中途日志写失败 → 维修记录不存在, 资产状态回 broken"""
        from unittest import mock

        asset.asset_current_status = "broken"
        asset.save()
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                RepairAssetService.create_repair_asset(
                    asset_code="A001",
                    repair_reason="主板故障",
                    repair_date="2024-06-01",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        assert RepairAsset.objects.count() == 0
        asset.refresh_from_db()
        assert asset.asset_current_status == "broken"

    def test_complete_repair_rolls_back_on_log_failure(self, asset, user):
        """完成维修中途日志写失败 → 记录仍 in_progress, 资产仍 repairing"""
        from unittest import mock

        self._make_repairing(asset, user)
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                RepairAssetService.complete_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        record = RepairAsset.objects.get()
        assert record.repair_status == "in_progress"
        asset.refresh_from_db()
        assert asset.asset_current_status == "repairing"

    def test_fail_repair_rolls_back_on_log_failure(self, asset, user):
        """维修失败中途日志写失败 → 记录/资产/待报废记录全部回滚"""
        from unittest import mock

        self._make_repairing(asset, user)
        with mock.patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                RepairAssetService.fail_repair(
                    asset_code="A001",
                    operator_jobcode=user.employee_jobcode,
                    operator_name=user.employee_name,
                )
        record = RepairAsset.objects.get()
        assert record.repair_status == "in_progress"
        asset.refresh_from_db()
        assert asset.asset_current_status == "repairing"
        assert DamagedAsset.objects.count() == 0
