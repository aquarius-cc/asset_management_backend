"""
已报废资产管理服务

提供资产报废执行的业务逻辑。
"""

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, DamagedAsset, WasteAsset
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from core.exceptions import AppValidationError


class WasteAssetService:
    """
    已报废资产管理服务

    提供资产报废执行的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_waste_asset(
        waste_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> WasteAsset:
        damaged_asset = waste_data.get("asset_recordcode")
        if not damaged_asset:
            raise AppValidationError(detail="缺少待报废记录", error_code="MISSING_DAMAGED_ASSET")

        if damaged_asset.approval_status != DamagedAsset.ApprovalStatus.APPROVED:
            raise AppValidationError(detail="待报废记录未通过审批,无法报废", error_code="DAMAGED_ASSET_NOT_APPROVED")

        # waste_data["asset_recordcode"] 承载 DamagedAsset,创建 WasteAsset 时需转换为底层 Asset
        waste_data["asset_recordcode"] = damaged_asset.asset_recordcode
        waste_asset = WasteAsset.objects.create(**waste_data)

        asset = damaged_asset.asset_recordcode
        if asset:
            asset = Asset.objects.select_for_update().get(pk=asset.pk)

            # 仅当资产尚未转为 scrapped 时才触发 FSM(避免与 approve_asset_recordcode 重复调用)
            if asset.asset_current_status != Asset.AssetStatus.SCRAPPED:
                try:
                    AssetFSM.approve(asset)
                except InvalidTransitionError as e:
                    raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

                asset.save(update_fields=["asset_current_status"])

        if asset:
            AuditLogger.log_asset_waste(
                asset=asset,
                waste_record_code=waste_asset.recordcode,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return waste_asset

    @staticmethod
    @transaction.atomic
    def create_from_damaged_asset(
        damaged_asset: DamagedAsset, operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> WasteAsset:
        if damaged_asset.approval_status != DamagedAsset.ApprovalStatus.APPROVED:
            raise AppValidationError(
                detail=f"待报废记录未审批通过,当前状态: {damaged_asset.approval_status}",
                error_code="DAMAGED_ASSET_NOT_APPROVED",
            )

        asset = damaged_asset.asset_recordcode
        if not asset:
            raise AppValidationError(detail="待报废记录未关联资产", error_code="MISSING_RELATED_ASSET")

        existing_waste = WasteAsset.objects.filter(
            asset_recordcode__asset_code=asset.asset_code, is_deleted=False
        ).first()
        if existing_waste:
            raise AppValidationError(
                detail=f"资产 {asset.asset_code} 已存在已报废记录", error_code="DUPLICATE_WASTE_RECORD"
            )

        waste_data = {
            "asset_recordcode": asset,
            "damaged_recordcode": damaged_asset,
            "waste_asset_number": damaged_asset.damaged_asset_number,
            "waste_asset_date": timezone.now().date(),
            "waste_asset_description": damaged_asset.damaged_asset_description,
        }

        waste_asset = WasteAsset.objects.create(**waste_data)

        if asset:
            AuditLogger.log_asset_waste(
                asset=asset,
                waste_record_code=waste_asset.asset_recordcode.asset_code
                if waste_asset.asset_recordcode
                else str(waste_asset.id),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return waste_asset

    @staticmethod
    @transaction.atomic
    def cancel_waste_asset(
        waste_asset_code: str, operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> None:
        """
        取消已报废记录(软删除已报废记录,不改变资产状态)

        业务规则:
        - scrapped 是终态,不可逆
        - 只删除 WasteAsset 记录,不改变资产状态
        - 如需恢复资产使用,应走重新入库流程
        """
        waste_asset = WasteAsset.objects.filter(asset_recordcode__asset_code=waste_asset_code, is_deleted=False).first()
        if not waste_asset:
            raise AppValidationError(detail=f"已报废记录 {waste_asset_code} 不存在", error_code="WASTE_ASSET_NOT_FOUND")

        asset = waste_asset.asset_recordcode

        # [HALT] 取消报废:scrapped 是终态,不可逆
        # 只删除 WasteAsset 记录,不改变资产状态
        # 如需恢复资产使用,应走重新入库流程
        waste_asset.delete()

        if asset:
            AuditLogger.log_asset_delete(
                asset_code=asset.asset_code,
                asset_name=asset.asset_name,
                asset=asset,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

    @staticmethod
    def batch_delete_waste_assets(waste_asset_codes: list[str], operator_jobcode: str | None, operator_name: str | None) -> dict[str, Any]:
        """
        批量删除报废记录(DR-1 收敛)

        【契约变更说明】原 View 循环无 AppValidationError 分支, Service 抛出的
        WASTE_ASSET_NOT_FOUND 被遮蔽为 INTERNAL_ERROR; 迁移后透传真实错误码。
        _delete_one 内局部转换 DoesNotExist -> NOT_FOUND, 单条 cancel_waste_asset
        的公开行为不变。
        """
        from core.batch_mixins import BatchOperationMixin

        def _delete_one(waste_asset_code: str) -> None:
            try:
                WasteAssetService.cancel_waste_asset(
                    waste_asset_code,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
            except WasteAsset.DoesNotExist:
                raise AppValidationError(
                    detail=f"已报废记录 {waste_asset_code} 不存在", error_code="NOT_FOUND"
                ) from None

        return BatchOperationMixin.batch_delete_execute(waste_asset_codes, _delete_one)

