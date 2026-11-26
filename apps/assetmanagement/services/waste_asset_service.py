"""
已报废资产管理服务

提供已报废记录的取消/批量删除业务逻辑(创建路径见 DamagedAssetService.approve 内联)。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import WasteAsset
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.selectors.waste_asset_selector import WasteAssetSelector
from core.exceptions import AppValidationError


class WasteAssetService:
    """
    已报废资产管理服务

    提供已报废记录的取消/批量删除业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def cancel_waste_asset(
        waste_asset_code: str, operator_jobcode: str | None = None, operator_name: str | None = None, *, user: Any
    ) -> None:
        """
        取消已报废记录(软删除已报废记录,不改变资产状态)

        业务规则:
        - scrapped 是终态,不可逆
        - 只删除 WasteAsset 记录,不改变资产状态
        - 如需恢复资产使用,应走重新入库流程
        """
        try:
            # M-CONC-01:行锁读,锁内复检 is_deleted(防并发双请求双份审计+双软删)
            waste_asset = WasteAssetSelector.get_for_update_by_asset_code(waste_asset_code)
        except WasteAsset.DoesNotExist:
            raise AppValidationError(
                detail=f"已报废记录 {waste_asset_code} 不存在", error_code="WASTE_ASSET_NOT_FOUND"
            ) from None

        asset = waste_asset.asset_recordcode

        # BF-170 OP-03:行级隔离(B14)——资产不在调用者可见范围则拒绝(与 asset/recycle/damaged 链同口径,DR-1)
        AssetSelector.ensure_asset_visible(asset, user)

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
        waste_asset_codes: list[str],
        operator_jobcode: str | None,
        operator_name: str | None,
        *,
        user: Any,
    ) -> dict[str, Any]:
        """
        批量删除报废记录(DR-1 收敛)

        【契约变更说明】原 View 循环无 AppValidationError 分支, Service 抛出的
        WASTE_ASSET_NOT_FOUND 被遮蔽为 INTERNAL_ERROR; 迁移后透传真实错误码。
        【M-CONC-01 错误码口径】① 行锁超时 → ResourceConflictError → fail_items
        error_code=ASSET_LOCKED(409 语义); ② 锁内取行时记录已被并发软删(不再匹配
        is_deleted=False) → DoesNotExist → 映射 WASTE_ASSET_NOT_FOUND。二者不可混同。
        """
        from core.batch_mixins import BatchOperationMixin

        def _delete_one(waste_asset_code: str) -> None:
            WasteAssetService.cancel_waste_asset(
                waste_asset_code,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                user=user,
            )

        return BatchOperationMixin.batch_delete_execute(waste_asset_codes, _delete_one)
