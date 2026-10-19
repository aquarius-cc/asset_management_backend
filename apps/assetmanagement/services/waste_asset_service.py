"""
已报废资产管理服务

提供已报废记录的取消/批量删除业务逻辑(创建路径见 DamagedAssetService.approve 内联)。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import WasteAsset
from core.exceptions import AppValidationError


class WasteAssetService:
    """
    已报废资产管理服务

    提供已报废记录的取消/批量删除业务逻辑。
    """

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
    def batch_delete_waste_assets(
        waste_asset_codes: list[str], operator_jobcode: str | None, operator_name: str | None
    ) -> dict[str, Any]:
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
