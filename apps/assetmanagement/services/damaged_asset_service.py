"""
待报废资产管理服务

提供资产报废申请和审批的业务逻辑。
"""

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, DamagedAsset, WasteAsset
from apps.assetmanagement.selectors import (
    DamagedAssetSelector,
)
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from apps.usermanagement.selectors import EmployeeSelector
from core.exceptions import AppValidationError


class DamagedAssetService:
    """
    待报废资产管理服务

    提供资产报废申请和审批的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_damaged_asset(
        damaged_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> DamagedAsset:
        asset = damaged_data.get("asset_recordcode")
        if not asset:
            raise AppValidationError(detail="缺少资产编码", error_code="MISSING_ASSET_CODE")

        if DamagedAssetSelector.exists_by_asset_code(asset.asset_code):
            raise AppValidationError(
                detail=f"资产 {asset.asset_code} 已存在待报废记录", error_code="DUPLICATE_DAMAGED_RECORD"
            )

        damaged_asset = DamagedAsset.objects.create(**damaged_data)

        # 触发 FSM 状态流转: (in_use|recycled_pending|broken|repairing|lost) → damaged
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status
        # 记录申请前状态(审批拒绝时回退依据,业务约束 §三.5;服务端权威,不信任客户端传值)
        damaged_asset.original_status = old_status
        damaged_asset.save(update_fields=["original_status", "updated_at"])
        try:
            AssetFSM.damaged(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
        asset.save(update_fields=["asset_current_status", "updated_at"])

        AuditLogger.log_state_change(
            asset=asset,
            from_state=old_status,
            to_state="damaged",
            trigger="create_damaged",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return damaged_asset

    @staticmethod
    @transaction.atomic
    def update_damaged_asset(recordcode: str, update_data: dict[str, Any]) -> DamagedAsset:
        """
        更新待报废记录(select_for_update 防并发覆盖)

        Args:
            recordcode: 待报废记录编码
            update_data: 更新字段(白名单过滤)

        Returns:
            更新后的 DamagedAsset
        """
        damaged_asset = DamagedAsset.objects.select_for_update().filter(recordcode=recordcode).first()
        if not damaged_asset:
            raise AppValidationError(detail="待报废记录不存在", error_code="DAMAGED_RECORD_NOT_FOUND")

        allowed_fields = {"damaged_asset_description", "damaged_date", "damaged_asset_number"}
        update_fields = []
        for field, value in update_data.items():
            if field in allowed_fields and value is not None:
                setattr(damaged_asset, field, value)
                update_fields.append(field)

        if update_fields:
            damaged_asset.save(update_fields=update_fields)
        return damaged_asset

    @staticmethod
    @transaction.atomic
    def approve_asset_recordcode(
        asset_recordcode_code: str, approver_jobcode: str, operator_name: str
    ) -> dict[str, Any]:
        """
        审批通过待报废申请

        Args:
            asset_recordcode_code: 资产recordcode
            approver_jobcode: 审批人工号
            operator_name: 审批人姓名

        Returns:
            Dict: 包含damaged_asset和waste_asset的字典
        """
        damaged_asset = DamagedAsset.objects.filter(
            asset_recordcode__recordcode=asset_recordcode_code, is_deleted=False
        ).first()
        if not damaged_asset:
            raise AppValidationError(
                detail=f"待报废记录 {asset_recordcode_code} 不存在", error_code="DAMAGED_ASSET_NOT_FOUND"
            )

        damaged_asset = DamagedAsset.objects.select_for_update().get(pk=damaged_asset.pk)

        if damaged_asset.approval_status != "pending":
            raise AppValidationError(
                detail=f"待报废记录状态为 {damaged_asset.approval_status},不允许审批",
                error_code="INVALID_APPROVAL_STATUS",
            )

        # 更新审批状态
        damaged_asset.approval_status = "approved"
        damaged_asset.approver = EmployeeSelector.get_employee_by_jobcode(approver_jobcode)
        damaged_asset.save()

        # 创建报废记录
        waste_asset = WasteAsset.objects.create(
            asset_recordcode=damaged_asset.asset_recordcode,
            damaged_recordcode=damaged_asset,
            waste_asset_number=damaged_asset.damaged_asset_number,
            waste_asset_date=timezone.now().date(),
        )

        # 更新资产状态
        asset = damaged_asset.asset_recordcode
        AssetFSM.approve(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        # 审计日志
        AuditLogger.log_state_change(
            asset=asset,
            from_state="damaged",
            to_state="scrapped",
            trigger="approve",
            operator_jobcode=approver_jobcode,
            operator_name=operator_name,
        )

        # P1-8 通知:审批通过 → 发给资产所属部门所有 dept_manager
        try:
            from apps.notification.helpers import notify_dept_managers

            notify_dept_managers(
                asset=asset,
                notification_type="approval",
                title="待报废审批通过",
                message=f"资产 {asset.asset_code} 的报废申请已审批通过",
                priority="high",
                related_url=f"/main/assetdetails/{asset.asset_code}",
            )
        except Exception:
            pass  # 通知失败不影响业务

        return {
            "damaged_asset": damaged_asset,
            "waste_asset": waste_asset,
        }

    @staticmethod
    @transaction.atomic
    def reject_asset_recordcode(asset_recordcode_code: str, approver_jobcode: str, operator_name: str) -> DamagedAsset:
        """
        审批拒绝待报废申请

        Args:
            asset_recordcode_code: 资产recordcode
            approver_jobcode: 审批人工号
            operator_name: 审批人姓名

        Returns:
            DamagedAsset: 更新后的待报废记录
        """
        damaged_asset = DamagedAsset.objects.filter(
            asset_recordcode__recordcode=asset_recordcode_code, is_deleted=False
        ).first()
        if not damaged_asset:
            raise AppValidationError(
                detail=f"待报废记录 {asset_recordcode_code} 不存在", error_code="DAMAGED_ASSET_NOT_FOUND"
            )

        damaged_asset = DamagedAsset.objects.select_for_update().get(pk=damaged_asset.pk)

        if damaged_asset.approval_status != "pending":
            raise AppValidationError(
                detail=f"待报废记录状态为 {damaged_asset.approval_status},不允许审批",
                error_code="INVALID_APPROVAL_STATUS",
            )

        # 更新审批状态
        damaged_asset.approval_status = "rejected"
        damaged_asset.approver = EmployeeSelector.get_employee_by_jobcode(approver_jobcode)
        damaged_asset.save()

        # 根据 original_status 回退状态(业务约束 §三.5: 审批拒绝回退申请前状态)
        asset = damaged_asset.asset_recordcode
        old_status = asset.asset_current_status
        AssetFSM.reject_to_original(asset, damaged_asset.original_status)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        # 审计日志
        AuditLogger.log_state_change(
            asset=asset,
            from_state=old_status,
            to_state=asset.asset_current_status,
            trigger="reject",
            operator_jobcode=approver_jobcode,
            operator_name=operator_name,
        )

        # P1-8 通知:审批拒绝 → 发给资产所属部门所有 dept_manager
        try:
            from apps.notification.helpers import notify_dept_managers

            notify_dept_managers(
                asset=asset,
                notification_type="approval",
                title="待报废审批拒绝",
                message=f"资产 {asset.asset_code} 的报废申请已被拒绝",
                priority="medium",
                related_url=f"/main/assetdetails/{asset.asset_code}",
            )
        except Exception:
            pass

        return damaged_asset

    @staticmethod
    @transaction.atomic
    def cancel_asset_recordcode(
        asset_recordcode_code: str, operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> None:
        """
        取消待报废申请

        Args:
            asset_recordcode_code: 资产recordcode
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
        """
        damaged_asset = DamagedAsset.objects.filter(
            asset_recordcode__recordcode=asset_recordcode_code, is_deleted=False
        ).first()
        if not damaged_asset:
            raise AppValidationError(
                detail=f"待报废记录 {asset_recordcode_code} 不存在", error_code="DAMAGED_ASSET_NOT_FOUND"
            )

        damaged_asset = DamagedAsset.objects.select_for_update().get(pk=damaged_asset.pk)

        if damaged_asset.approval_status != "pending":
            raise AppValidationError(
                detail=f"待报废记录状态为 {damaged_asset.approval_status},不允许取消",
                error_code="INVALID_APPROVAL_STATUS",
            )

        # 软删除待报废记录
        damaged_asset.delete()

        # 恢复资产状态
        asset = damaged_asset.asset_recordcode
        old_status = asset.asset_current_status
        AssetFSM.cancel_damaged(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        # 审计日志
        AuditLogger.log_state_change(
            asset=asset,
            from_state=old_status,
            to_state=asset.asset_current_status,
            trigger="cancel",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
