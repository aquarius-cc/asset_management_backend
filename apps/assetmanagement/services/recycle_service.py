"""
回收资产管理服务

提供资产回收的业务逻辑，包括回收记录创建、资产状态更新等操作。
"""

from typing import Optional, Dict, Any, List

from django.db import transaction
from django.utils import timezone
from core.exceptions import AppValidationError
from core.batch_mixins import BatchOperationMixin

from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
from apps.assetmanagement.selectors import OutAssetSelector, RecycleAssetSelector
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from apps.assetmanagement.audit import AuditLogger


class RecycleAssetService:
    """
    回收资产管理服务

    提供资产回收的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_recycle_asset(
        recycle_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> RecycleAsset:
        storage_obj = recycle_data.pop('recycle_asset_storage_code', None)
        recycle_person_obj = recycle_data.pop('recycle_asset_recycle_person_jobcode', None)

        recycle_outasset = recycle_data.get('recycle_outasset')
        if not recycle_outasset:
            raise AppValidationError(
                detail="缺少出库记录编码",
                error_code="MISSING_OUTASSET_RECORDCODE"
            )

        outasset = OutAssetSelector.get_outasset_by_record_code(
            recycle_outasset.recordcode
        )
        if not outasset:
            raise AppValidationError(
                detail=f"出库记录 {recycle_outasset} 不存在",
                error_code="OUTASSET_NOT_FOUND"
            )

        asset = outasset.outasset_asset
        if asset.asset_current_status != 'in_use':
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status}，不能回收",
                error_code="INVALID_ASSET_STATUS_FOR_RECYCLE"
            )

        if recycle_person_obj and not recycle_data.get('operator_employee'):
            recycle_data['operator_employee'] = recycle_person_obj

        if not recycle_data.get('operator_employee') and operator_jobcode:
            recycle_data['operator_employee'] = operator_jobcode

        recycle_asset = RecycleAsset.objects.create(**recycle_data)

        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status

        try:
            AssetFSM.recycle(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(
                detail=str(e),
                error_code="INVALID_STATE_TRANSITION"
            )

        if storage_obj:
            asset.asset_storage = storage_obj
        if recycle_person_obj:
            asset.asset_entry_person = recycle_person_obj

        update_fields = ['asset_current_status']
        if storage_obj:
            update_fields.append('asset_storage')
        if recycle_person_obj:
            update_fields.append('asset_entry_person')

        asset.save(update_fields=update_fields)

        AuditLogger.log_asset_recycle(
            asset=asset,
            recordcode=recycle_asset.recordcode,
            # 【P1-12 修复】优先使用方法参数的操作人，回退到 recycle_data 中的值
            operator_jobcode=operator_jobcode or recycle_data.get('operator_employee'),
            operator_name=operator_name or recycle_data.get('asset_entry_person_name')
        )

        return recycle_asset

    @staticmethod
    @transaction.atomic
    def update_recycle_asset(
        recordcode: str,
        update_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> RecycleAsset:
        """
        更新回收记录

        【P1-05 修复】将更新逻辑从 View 层迁移到 Service 层，
        确保审计日志记录和业务校验一致性。

        Args:
            recordcode: 回收记录编码
            update_data: 更新数据
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            RecycleAsset: 更新后的回收记录
        """
        recycle_asset = RecycleAssetSelector.get_recycle_asset_by_record_code(recordcode)
        if not recycle_asset:
            raise AppValidationError(
                detail=f"回收记录 {recordcode} 不存在",
                error_code="RECYCLE_ASSET_NOT_FOUND"
            )

        before_data = {key: getattr(recycle_asset, key) for key in update_data.keys()}

        for key, value in update_data.items():
            if hasattr(recycle_asset, key):
                setattr(recycle_asset, key, value)
            else:
                raise AppValidationError(
                    detail=f"不允许修改字段: {key}",
                    error_code="FIELD_NOT_ALLOWED"
                )

        recycle_asset.save()

        AuditLogger.log_asset_update(
            asset=recycle_asset.recycle_outasset.outasset_asset if recycle_asset.recycle_outasset else None,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return recycle_asset

    @staticmethod
    def batch_create_recycle_asset(
        recycle_data_list: List[Dict[str, Any]],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        import copy

        def _create_item(idx: int, recycle_data: Dict[str, Any]) -> RecycleAsset:
            return RecycleAssetService.create_recycle_asset(
                recycle_data=copy.deepcopy(recycle_data),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_execute(
            items=recycle_data_list,
            process_fn=_create_item,
            max_batch_size=100,
            use_transaction=False,
        )

    @staticmethod
    def batch_delete_recycle_asset(
        recordcodes: List[str],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        MAX_BATCH_SIZE = 100
        if len(recordcodes) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条",
                error_code="BATCH_SIZE_EXCEEDED"
            )

        success_ids: List[str] = []
        fail_items: List[Dict[str, Any]] = []

        for record_code in recordcodes:
            try:
                with transaction.atomic():
                    recycle_asset = RecycleAsset.objects.select_for_update().filter(
                        recordcode=record_code, is_deleted=False
                    ).first()
                    if not recycle_asset:
                        fail_items.append({
                            "id": record_code,
                            "error_code": "NOT_FOUND",
                            "error_message": f"回收记录 {record_code} 不存在"
                        })
                        continue

                    asset = Asset.objects.select_for_update().get(pk=recycle_asset.recycle_asset_code.pk)
                    if asset.asset_current_status != 'recycled_pending':
                        fail_items.append({
                            "id": record_code,
                            "error_code": "STATUS_NOT_ALLOWED",
                            "error_message": f"关联资产当前状态为 {asset.asset_current_status}，不允许删除回收记录"
                        })
                        continue

                    recycle_asset.delete()

                    AssetFSM.cancel_recycle(asset)

                    asset.asset_entry_person = None
                    asset.save(update_fields=[
                        'asset_current_status',
                        'asset_entry_person',
                    ])

                success_ids.append(record_code)

            except InvalidTransitionError as e:
                fail_items.append({
                    "id": record_code,
                    "error_code": "INVALID_STATE_TRANSITION",
                    "error_message": str(e)
                })
            except Exception:
                fail_items.append({
                    "id": record_code,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(recordcodes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items
        }
