"""
维修资产管理服务 - 提供资产维修的统一业务逻辑,防止通过不同入口创建重复维修记录。

维修状态流转的唯一实现,AssetViewSet 的 repair/repair-done/repair-failed
action 与 RepairAssetViewSet 的 create 均委托本服务,禁止绕过。

Class:
  - RepairAssetService: 维修资产管理服务
    - create_repair_asset: 创建维修记录(触发 broken→repairing 状态流转)
    - complete_repair: 完成维修(触发 repairing→recycled_pending 状态流转)
    - fail_repair: 维修失败(触发 repairing→damaged 状态流转)

调用链:
  View -> RepairAssetService -> AssetFSM/EmployeeSelector/RepairAsset
  本模块依赖 -> Asset, RepairAsset, DamagedAsset, AssetFSM, AuditLogger
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, AssetOperationLog, DamagedAsset, RepairAsset
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from apps.usermanagement.models import Employee
from apps.usermanagement.selectors import EmployeeSelector
from core.exceptions import AppValidationError


logger = logging.getLogger(__name__)


class RepairAssetService:
    """
    维修资产管理服务

    统一封装维修记录的创建、完成、失败逻辑,
    防止通过不同入口创建重复的 in_progress 维修记录。
    """

    @staticmethod
    def _lock_asset_for_repair(
        asset_code: str,
        operator_jobcode: str,
    ) -> tuple[Asset, Employee | None]:
        """锁定资产 + 幂等校验 + 获取操作人"""
        # AC-65: 捕获锁超时,返回 409 Conflict
        from django.db import OperationalError

        from core.exceptions import ResourceConflictError

        try:
            asset = Asset.objects.select_for_update().get(asset_code=asset_code)
        except OperationalError:
            raise ResourceConflictError(
                detail="资产被其他用户锁定,请稍后重试",
                error_code="ASSET_LOCKED",
            )

        # L1-3 防重复校验:检查是否已有 in_progress 维修记录
        if RepairAsset.objects.filter(
            asset_recordcode=asset, repair_status=RepairAsset.RepairStatus.IN_PROGRESS
        ).exists():
            logger.warning(f"重复送修被拒绝: asset={asset_code}, operator={operator_jobcode}")
            raise AppValidationError(
                detail=f"资产 {asset_code} 已有进行中的维修记录,不可重复送修",
                error_code="DUPLICATE_REPAIR_IN_PROGRESS",
            )

        operator = None
        if operator_jobcode:
            operator = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)

        return asset, operator

    @staticmethod
    def _execute_repair_transition(
        asset: Asset,
        repair_reason: str,
        operator_jobcode: str,
    ) -> str:
        """FSM 状态转换 (broken → repairing) + 审计日志"""
        from_state = asset.asset_current_status
        try:
            AssetFSM.repair(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
        asset.save(update_fields=["asset_current_status", "updated_at"])

        # AC-61: 记录状态变更日志

        AuditLogger.log_state_change(
            asset=asset,
            from_state=from_state,
            to_state=Asset.AssetStatus.REPAIRING,
            trigger="repair",
            operator_jobcode=operator_jobcode,
        )
        return from_state

    @staticmethod
    def _log_repair_audit(
        asset: Asset,
        operator_jobcode: str,
        operator_name: str,
        repair_reason: str,
    ) -> None:
        """记录操作日志"""
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.REPAIR,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"Asset sent for repair: {repair_reason}",
        )

    @staticmethod
    @transaction.atomic
    def create_repair_asset(
        asset_code: str,
        repair_reason: str,
        repair_date: str,
        repair_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> RepairAsset:
        """
        创建维修记录(送修资产: broken → repairing)

        包含防重复校验:同一资产不允许存在多条 in_progress 维修记录。
        """
        asset, operator = RepairAssetService._lock_asset_for_repair(
            asset_code,
            operator_jobcode,
        )

        RepairAssetService._execute_repair_transition(
            asset,
            repair_reason,
            operator_jobcode,
        )

        repair_record = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date=repair_date,
            repair_reason=repair_reason,
            repair_description=repair_description or None,
            operator_employee=operator,
            physical_grade_before=asset.physical_grade,
        )

        RepairAssetService._log_repair_audit(
            asset,
            operator_jobcode,
            operator_name,
            repair_reason,
        )

        return repair_record  # type: ignore[no-any-return]

    @staticmethod
    @transaction.atomic
    def complete_repair(
        asset_code: str,
        actual_return_date: str = "",
        physical_grade_after: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> RepairAsset:
        """维修完成: repairing → recycled_pending"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        repair_record = RepairAsset.objects.filter(
            asset_recordcode=asset, repair_status=RepairAsset.RepairStatus.IN_PROGRESS
        ).first()
        if not repair_record:
            raise AppValidationError(detail="该资产没有进行中的维修记录", error_code="NO_IN_PROGRESS_REPAIR")

        from_state = asset.asset_current_status
        AssetFSM.repair_done(asset)
        if physical_grade_after:
            asset.physical_grade = physical_grade_after
        asset.save(update_fields=["asset_current_status", "physical_grade", "updated_at"])

        repair_record.repair_status = RepairAsset.RepairStatus.COMPLETED
        repair_record.actual_return_date = actual_return_date or timezone.now().date()
        repair_record.physical_grade_after = physical_grade_after or None
        repair_record.save(update_fields=["repair_status", "actual_return_date", "physical_grade_after", "updated_at"])

        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.REPAIR_DONE,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="Repair completed, asset moved to recycled_pending",
        )

        # AC-61: 记录状态变更日志

        AuditLogger.log_state_change(
            asset=asset,
            from_state=from_state,
            to_state=Asset.AssetStatus.RECYCLED_PENDING,
            trigger="repair_done",
            operator_jobcode=operator_jobcode,
        )

        # 维修完成通知(事务提交后执行)
        from apps.notification.helpers import send_notification_on_commit

        send_notification_on_commit(
            asset=asset,
            notification_type="status_change",
            title="资产维修完成通知",
            message=f"资产 {asset.asset_code} 维修已完成,已转入待发放状态",
            priority="medium",
            related_url=f"/main/assetdetails/{asset.asset_code}",
        )

        return repair_record

    @staticmethod
    @transaction.atomic
    def fail_repair(
        asset_code: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> RepairAsset:
        """维修失败: repairing → damaged"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        repair_record = RepairAsset.objects.filter(
            asset_recordcode=asset, repair_status=RepairAsset.RepairStatus.IN_PROGRESS
        ).first()
        if not repair_record:
            raise AppValidationError(detail="该资产没有进行中的维修记录", error_code="NO_IN_PROGRESS_REPAIR")

        from_state = asset.asset_current_status
        AssetFSM.repair_failed(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        # AC-61: 记录状态变更日志

        AuditLogger.log_state_change(
            asset=asset,
            from_state=from_state,
            to_state=Asset.AssetStatus.DAMAGED,
            trigger="repair_failed",
            operator_jobcode=operator_jobcode,
        )

        repair_record.repair_status = RepairAsset.RepairStatus.FAILED
        repair_record.save(update_fields=["repair_status", "updated_at"])

        DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
            original_status=from_state,
        )

        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.REPAIR_FAILED,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="Repair failed, asset moved to damaged",
        )

        # 维修失败通知(事务提交后执行)
        from apps.notification.helpers import send_notification_on_commit

        send_notification_on_commit(
            asset=asset,
            notification_type="status_change",
            title="资产维修失败通知",
            message=f"资产 {asset.asset_code} 维修失败,已转入待报废状态",
            priority="high",
            related_url=f"/main/assetdetails/{asset.asset_code}",
        )

        return repair_record
