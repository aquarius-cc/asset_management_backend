"""
资产生命周期管理 Mixin

提供资产状态流转相关的业务方法:标记损坏/遗失、找回、维修记录删除。
维修状态流转(送修/完成/失败)统一收敛至 RepairAssetService,禁止在
本 Mixin 重复实现。
被 AssetService 继承以保持统一 API。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, BrokenAsset, FoundAsset, LostAsset
from apps.assetmanagement.models.operation_log import AssetOperationLog
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError


class AssetLifecycleMixin:
    """资产生命周期状态流转方法"""

    @staticmethod
    @transaction.atomic
    def mark_asset_broken(
        asset_code: str,
        broken_reason: str,
        broken_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
        user: Any | None = None,
    ) -> BrokenAsset:
        """标记资产为已损坏, 返回创建的 BrokenAsset 记录(batch 响应按该记录序列化)"""
        from core.exceptions import AppValidationError

        asset = Asset.objects.select_for_update().filter(asset_code=asset_code).first()
        if asset is None:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")

        # BEQ-02 行级隔离: 创建前校验目标资产在用户可见范围内(与 by_asset 查询侧同口径)
        if user is not None:
            AssetSelector.ensure_asset_visible(asset, user)

        if asset.asset_current_status == Asset.AssetStatus.BROKEN:
            existing = BrokenAsset.objects.filter(asset_recordcode=asset).order_by("-created_at").first()
            if existing is not None:
                return existing
            # 历史数据缺失时补建记录, 保持幂等语义(不改变资产状态, 不重复 FSM 迁移)
            return BrokenAsset.objects.create(
                asset_recordcode=asset,
                broken_reason=broken_reason,
                broken_description=broken_description,
            )

        from apps.usermanagement.selectors import EmployeeSelector

        operator = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)

        try:
            AssetFSM.mark_broken(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog

        broken_record = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason=broken_reason,
            broken_description=broken_description,
            operator_employee=operator,
        )
        # DateField default=timezone.now 使内存实例携带 datetime, 刷新为 DB 落库后的 date(否则响应序列化拒绝)
        broken_record.refresh_from_db()
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.BROKEN,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"资产标记为已损坏: {broken_reason}",
        )
        return broken_record

    @staticmethod
    @transaction.atomic
    def mark_asset_lost(
        asset_code: str,
        lost_reason: str,
        last_known_location: str = "",
        lost_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
        user: Any | None = None,
    ) -> LostAsset:
        """标记资产为已遗失, 返回创建的 LostAsset 记录(batch 响应按该记录序列化)"""
        from core.exceptions import AppValidationError

        asset = Asset.objects.select_for_update().filter(asset_code=asset_code).first()
        if asset is None:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")

        # BEQ-02 行级隔离: 创建前校验目标资产在用户可见范围内(与 by_asset 查询侧同口径)
        if user is not None:
            AssetSelector.ensure_asset_visible(asset, user)

        if asset.asset_current_status == Asset.AssetStatus.LOST:
            existing = LostAsset.objects.filter(asset_recordcode=asset).order_by("-created_at").first()
            if existing is not None:
                return existing
            # 历史数据缺失时补建记录, 保持幂等语义(不改变资产状态, 不重复 FSM 迁移)
            return LostAsset.objects.create(
                asset_recordcode=asset,
                last_known_location=last_known_location,
                lost_reason=lost_reason,
                lost_description=lost_description,
            )

        from apps.usermanagement.selectors import EmployeeSelector

        operator = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)

        try:
            AssetFSM.mark_lost(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog

        lost_record = LostAsset.objects.create(
            asset_recordcode=asset,
            last_known_location=last_known_location,
            lost_reason=lost_reason,
            lost_description=lost_description,
            operator_employee=operator,
        )
        # DateField default=timezone.now 使内存实例携带 datetime, 刷新为 DB 落库后的 date(否则响应序列化拒绝)
        lost_record.refresh_from_db()
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.LOST,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"资产标记为已遗失: {lost_reason}",
        )
        return lost_record

    @staticmethod
    @transaction.atomic
    def find_and_return_asset(
        asset_code: str,
        found_location: str = "",
        found_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> Asset:
        """找回遗失资产(转入待发放状态)"""
        from core.exceptions import AppValidationError

        asset = Asset.objects.select_for_update().filter(asset_code=asset_code).first()
        if asset is None:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")

        lost_record = LostAsset.objects.filter(asset_recordcode=asset).first()
        if lost_record is None:
            raise AppValidationError(detail=f"资产 {asset_code} 无遗失记录,无法找回", error_code="NO_LOST_RECORD")

        from apps.usermanagement.selectors import EmployeeSelector

        operator = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)

        try:
            AssetFSM.found_and_return(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, FoundAsset

        FoundAsset.objects.create(
            lost_asset_recordcode=lost_record,
            asset_recordcode=asset,
            found_location=found_location,
            found_description=found_description,
            operator_employee=operator,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.FOUND,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="遗失资产找回,转入待发放状态",
        )
        return asset

    @staticmethod
    @transaction.atomic
    def delete_repair_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """软删除维修记录(进行中的记录拒绝,防止资产卡死 repairing)"""
        from apps.assetmanagement.models import RepairAsset

        obj = RepairAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)

        if obj.repair_status == RepairAsset.RepairStatus.IN_PROGRESS:
            from core.exceptions import AppValidationError

            raise AppValidationError(
                detail=f"维修记录 {recordcode} 正在进行中,不可删除",
                error_code="REPAIR_IN_PROGRESS",
            )

        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,  # type: ignore[union-attr]
            asset_name=obj.asset_recordcode.asset_name,  # type: ignore[union-attr]
            asset_specification=obj.asset_recordcode.asset_specification,  # type: ignore[union-attr]
            operation_type=AssetOperationLog.OperationType.DELETE,
            description=f"维修记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    @transaction.atomic
    def delete_broken_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """软删除损坏资产记录(事务包裹、逐条校验、审计日志)"""
        obj = BrokenAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,  # type: ignore[union-attr]
            asset_name=obj.asset_recordcode.asset_name,  # type: ignore[union-attr]
            asset_specification=obj.asset_recordcode.asset_specification,  # type: ignore[union-attr]
            operation_type=AssetOperationLog.OperationType.DELETE,
            description=f"损坏资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    @transaction.atomic
    def delete_lost_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """软删除遗失资产记录(事务包裹、逐条校验、审计日志)"""
        obj = LostAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,  # type: ignore[union-attr]
            asset_name=obj.asset_recordcode.asset_name,  # type: ignore[union-attr]
            asset_specification=obj.asset_recordcode.asset_specification,  # type: ignore[union-attr]
            operation_type=AssetOperationLog.OperationType.DELETE,
            description=f"遗失资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    @transaction.atomic
    def delete_found_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """软删除找回资产记录(事务包裹、逐条校验、审计日志)"""
        obj = FoundAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,
            asset_name=obj.asset_recordcode.asset_name,
            asset_specification=obj.asset_recordcode.asset_specification,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description=f"找回资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    def batch_create_broken_assets(
        items: list[dict[str, Any]],
        operator_jobcode: str = "",
        operator_name: str = "",
        user: Any | None = None,
    ) -> dict[str, Any]:
        """批量创建损坏资产记录"""
        from core.batch_mixins import BatchOperationMixin

        def _create_one(idx: int, item: dict[str, Any]) -> Asset:
            return AssetLifecycleMixin.mark_asset_broken(
                asset_code=item["asset_code"],
                broken_reason=item["broken_reason"],
                broken_description=item.get("broken_description", ""),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                user=user,
            )

        return BatchOperationMixin.batch_execute(
            items=items, process_fn=_create_one, max_batch_size=100, use_transaction=False,
        )

    @staticmethod
    def batch_create_lost_assets(
        items: list[dict[str, Any]],
        operator_jobcode: str = "",
        operator_name: str = "",
        user: Any | None = None,
    ) -> dict[str, Any]:
        """批量创建遗失资产记录"""
        from core.batch_mixins import BatchOperationMixin

        def _create_one(idx: int, item: dict[str, Any]) -> Asset:
            return AssetLifecycleMixin.mark_asset_lost(
                asset_code=item["asset_code"],
                lost_reason=item["lost_reason"],
                lost_description=item.get("lost_description", ""),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                user=user,
            )

        return BatchOperationMixin.batch_execute(
            items=items, process_fn=_create_one, max_batch_size=100, use_transaction=False,
        )

    @staticmethod
    # [HALT] 批量删除既有生命周期事件记录(软删+审计透传, 批大小与逐条原子由 batch_delete_execute 保证)
    def batch_delete_lifecycle_asset(
        ids: list[str],
        delete_service_method: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """批量删除损坏/遗失/找回记录(子类差异仅 delete_service_method 参数)"""
        from core.batch_mixins import BatchOperationMixin
        from core.exceptions import AppValidationError

        def _delete_one(recordcode: str) -> None:
            try:
                getattr(AssetLifecycleMixin, delete_service_method)(
                    recordcode=recordcode,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
            except (BrokenAsset.DoesNotExist, LostAsset.DoesNotExist, FoundAsset.DoesNotExist):
                raise AppValidationError(detail=f"记录 {recordcode} 不存在", error_code="NOT_FOUND") from None

        return BatchOperationMixin.batch_delete_execute(ids=ids, process_fn=_delete_one)

    @staticmethod
    # [HALT] 批量删除维修记录(进行中的记录由其单条实现拒绝, error_code 透传)
    def batch_delete_repair_asset(
        ids: list[str],
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict[str, Any]:
        """批量删除维修记录"""
        from apps.assetmanagement.models import RepairAsset
        from core.batch_mixins import BatchOperationMixin
        from core.exceptions import AppValidationError

        def _delete_one(recordcode: str) -> None:
            try:
                AssetLifecycleMixin.delete_repair_asset(
                    recordcode=recordcode,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
            except RepairAsset.DoesNotExist:
                raise AppValidationError(detail=f"记录 {recordcode} 不存在", error_code="NOT_FOUND") from None

        return BatchOperationMixin.batch_delete_execute(ids=ids, process_fn=_delete_one)
