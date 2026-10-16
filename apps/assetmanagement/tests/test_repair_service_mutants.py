"""repair_asset_service 存活变异体定向补杀(mutmut 双门禁回基线,2026-10-16)

上一轮 WSL mutmut run 实测 GATE_FAIL(killed 1667/2025 = 82.3210 < 基线 83.25676365492598,
需 killed >= 1686)。`mutmut show` 定位 repair 面 23 个存活体,全部源于既有用例未断言的字段/参数面:
- _write_complete_log x8: asset_name / asset_specification / operator_jobcode / operator_name 变体
- _log_repair_audit x4: asset_name / asset_specification 变体
- _send_complete_notification x2: asset / priority kwarg 变体
- _execute_repair_transition x6: FSM detail 文案 x3 / state_change 行 operator_jobcode x2 / update_fields 脏字段 x1
- _lock_asset_for_repair x3: asset_code 过滤丢失(多资产场景) / 幂等过滤范围(他资产 in_progress / 本资产 completed)

对应宪法规则: CT-1(核心路径补测) / CT-4(回归屏障) / T5(精确断言杀伤)。
"""

import unittest.mock as mock

import pytest

from apps.assetmanagement.models import Asset, AssetOperationLog, RepairAsset
from apps.assetmanagement.services.repair_asset_service import RepairAssetService
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestRepairMutantsRound2:
    """按 `mutmut show` 存活清单成组补杀(一组断言对应一族变异体)"""

    def _make_repairing(self, asset, user):
        asset.asset_current_status = "repairing"
        asset.asset_name = "维修机-黑匣子"
        asset.asset_specification = "i7/32G/SSD-2T"
        asset.save(update_fields=["asset_current_status", "asset_name", "asset_specification"])
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def _make_broken(self, asset, name, specification):
        asset.asset_current_status = "broken"
        asset.asset_name = name
        asset.asset_specification = specification
        asset.save(update_fields=["asset_current_status", "asset_name", "asset_specification"])

    @staticmethod
    def _make_second_asset(storage, asset_type):
        return Asset.objects.create(
            asset_code="A999",
            asset_name="第二台资产",
            asset_purchase_price=999.00,
            asset_purchase_date="2024-02-02",
            asset_entry_date="2024-02-03",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
        )

    def _create_repair(self, user):
        return RepairAssetService.create_repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )

    def test_complete_log_all_fields_exact(self, asset, user):
        """repair_done 日志四字段逐字断言(杀 _write_complete_log 8 个变体)"""
        self._make_repairing(asset, user)
        RepairAssetService.complete_repair(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair_done")
        assert log.asset_name == "维修机-黑匣子"
        assert log.asset_specification == "i7/32G/SSD-2T"
        assert log.operator_jobcode == user.employee_jobcode
        assert log.operator_name == user.employee_name

    def test_create_repair_log_asset_fields_exact(self, asset, user):
        """送修操作日志资产字段逐字断言(杀 _log_repair_audit 4 个变体)"""
        self._make_broken(asset, "送修机-引擎", "RTX4090/64G")
        self._create_repair(user)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="repair")
        assert log.asset_name == "送修机-引擎"
        assert log.asset_specification == "RTX4090/64G"
        assert log.operator_name == user.employee_name

    def test_create_state_change_log_operator_jobcode(self, asset, user):
        """送修 state_change 日志透传 operator_jobcode(杀 _execute_repair_transition 2 个变体)"""
        self._make_broken(asset, "测试资产", "i7/16G")
        self._create_repair(user)
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.operator_jobcode == user.employee_jobcode

    def test_invalid_transition_detail_matches_fsm_error(self, asset, user):
        """非法流转 detail = FSM 异常原文(杀 detail None/缺省/"None" 3 个变体)"""
        with pytest.raises(InvalidTransitionError) as fsm_exc:
            AssetFSM.repair(asset)
        expected_detail = str(fsm_exc.value)
        with pytest.raises(AppValidationError) as exc:
            self._create_repair(user)
        assert exc.value.detail == expected_detail
        assert exc.value.error_code == "INVALID_STATE_TRANSITION"

    def test_complete_notification_asset_and_priority(self, asset, user):
        """完成通知 asset 实体与 priority 参数(杀 _send_complete_notification 2 个变体)"""
        self._make_repairing(asset, user)
        with mock.patch("apps.notification.helpers.send_notification_on_commit") as mock_send:
            RepairAssetService.complete_repair(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["asset"] == asset
        assert kwargs["priority"] == "medium"

    def test_transition_does_not_persist_dirty_field(self, asset, user):
        """FSM 转换仅存白名单字段: 内存脏值不落库(杀 update_fields 变体)"""
        self._make_broken(asset, "测试资产", "i7/16G")
        original_name = asset.asset_name
        asset.asset_name = "内存脏值-不落库"
        RepairAssetService._execute_repair_transition(asset, "主板故障", user.employee_jobcode)
        asset.refresh_from_db()
        assert asset.asset_name == original_name
        assert asset.asset_current_status == "repairing"

    def test_create_locks_by_code_with_two_assets(self, asset, user, storage, asset_type):
        """多资产共存时仍按 asset_code 锁定目标行(杀 asset_code 过滤丢失变体)"""
        self._make_second_asset(storage, asset_type)
        self._make_broken(asset, "测试资产", "i7/16G")
        result = self._create_repair(user)
        assert result.asset_recordcode == asset

    def test_create_ignores_other_asset_in_progress(self, asset, user, storage, asset_type):
        """他资产在途维修不阻塞本资产送修(杀 asset_recordcode 过滤丢失变体)"""
        other = self._make_second_asset(storage, asset_type)
        RepairAsset.objects.create(
            asset_recordcode=other,
            repair_date="2024-06-01",
            repair_reason="内存故障",
            repair_status="in_progress",
            operator_employee=user,
        )
        self._make_broken(asset, "测试资产", "i7/16G")
        result = self._create_repair(user)
        assert result.pk is not None

    def test_create_ignores_completed_history(self, asset, user):
        """历史 completed 维修记录不阻塞新送修(杀 repair_status 过滤丢失变体)"""
        RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-01-01",
            repair_reason="历史维修",
            repair_status="completed",
            operator_employee=user,
        )
        self._make_broken(asset, "测试资产", "i7/16G")
        result = self._create_repair(user)
        assert result.pk is not None
