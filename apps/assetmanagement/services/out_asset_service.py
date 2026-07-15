"""
出库资产管理服务

提供资产出库的业务逻辑，包括出库记录创建、状态变更等操作。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
from apps.assetmanagement.selectors import OutAssetSelector
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError


# 字段白名单
OUTASSET_UPDATE_ALLOWED_FIELDS = frozenset(
    [
        "outasset_type",
        "outasset_number",
        "outasset_description",
        "outasset_using_location",
        "return_date",
        "outasset_date",
    ]
)


class OutAssetService:
    """
    出库资产管理服务

    提供资产出库的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_outasset(
        outasset_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> OutAsset:
        asset = outasset_data.get("asset_recordcode")
        if not asset:
            raise AppValidationError(detail="缺少资产编码", error_code="MISSING_ASSET_CODE")

        if asset.asset_current_status not in ["in_store", "recycled_pending"]:
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status}，不能出库",
                error_code="ILLEGAL_OUTASSET",  # 2001: 非法出库
            )

        outasset_data["outasset_previous_status"] = asset.asset_current_status

        applicant = outasset_data.pop("outasset_applicant", None)
        manager = outasset_data.pop("outasset_manager", None)
        using_location = outasset_data.pop("outasset_using_location", None)

        # 设置 OutAsset 表的 FK 字段
        outasset_data["outasset_applicant_recordcode"] = applicant
        outasset_data["outasset_manager_recordcode"] = manager
        outasset_data["outasset_using_location"] = using_location

        # 构建 JSON 快照
        snapshot = {
            "applicant": {
                "jobcode": applicant.employee_jobcode if applicant else None,
                "name": applicant.employee_name if applicant else None,
            }
            if applicant
            else None,
            "manager": {
                "jobcode": manager.employee_jobcode if manager else None,
                "name": manager.employee_name if manager else None,
            }
            if manager
            else None,
            "using_location": using_location,
        }
        outasset_data["outasset_snapshot"] = snapshot

        outasset = OutAsset.objects.create(**outasset_data)

        asset = Asset.objects.select_for_update().get(pk=asset.pk)

        try:
            AssetFSM.outasset(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

        asset.asset_storage_recordcode = None
        if applicant:
            asset.asset_applicant_recordcode = applicant
        if manager:
            asset.asset_manager_recordcode = manager
        if using_location:
            asset.asset_using_location = using_location

        update_fields = [
            "asset_current_status",
            "asset_storage_recordcode",
        ]
        if applicant:
            update_fields.append("asset_applicant_recordcode")
        if manager:
            update_fields.append("asset_manager_recordcode")
        if using_location:
            update_fields.append("asset_using_location")
        asset.save(update_fields=update_fields)

        AuditLogger.log_asset_out(
            asset=asset,
            outrecordcode=outasset.recordcode,
            operator_jobcode=operator_jobcode or (applicant.employee_jobcode if applicant else None),
            operator_name=operator_name,
        )

        return outasset

    @staticmethod
    @transaction.atomic
    def update_outasset(
        recordcode: str,
        update_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> OutAsset:
        outasset = OutAssetSelector.get_outasset_by_record_code(recordcode)
        if not outasset:
            raise AppValidationError(detail=f"出库记录 {recordcode} 不存在", error_code="OUTASSET_NOT_FOUND")

        before_data = {key: getattr(outasset, key) for key in update_data.keys()}

        for key, value in update_data.items():
            if key in OUTASSET_UPDATE_ALLOWED_FIELDS:
                setattr(outasset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}", error_code="FIELD_NOT_ALLOWED")

        outasset.save()
        AuditLogger.log_asset_update(
            asset=outasset.asset_recordcode,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return outasset

    @staticmethod
    def get_outasset_statistics() -> dict[str, Any]:
        return OutAssetSelector.get_outasset_statistics()

    @staticmethod
    def batch_create_outasset(
        outasset_data_list: list[dict[str, Any]], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        import copy

        def _create_item(idx: int, outasset_data: dict[str, Any]) -> OutAsset:
            return OutAssetService.create_outasset(
                outasset_data=copy.deepcopy(outasset_data),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_execute(
            items=outasset_data_list,
            process_fn=_create_item,
            max_batch_size=100,
            use_transaction=False,
        )

    @staticmethod
    def batch_delete_outasset(
        recordcodes: list[str], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        MAX_BATCH_SIZE = 100
        if len(recordcodes) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_ids: list[str] = []
        fail_items: list[dict[str, Any]] = []

        for recordcode in recordcodes:
            try:
                with transaction.atomic():
                    outasset = (
                        OutAsset.objects.select_for_update().filter(recordcode=recordcode, is_deleted=False).first()
                    )
                    if not outasset:
                        fail_items.append(
                            {
                                "id": recordcode,
                                "error_code": "NOT_FOUND",
                                "error_message": f"出库记录 {recordcode} 不存在",
                            }
                        )
                        continue

                    asset = Asset.objects.select_for_update().get(pk=outasset.asset_recordcode.pk)
                    if asset.asset_current_status != "in_use":
                        fail_items.append(
                            {
                                "id": recordcode,
                                "error_code": "STATUS_NOT_ALLOWED",
                                "error_message": f"关联资产当前状态为 {asset.asset_current_status}，不允许删除出库记录",
                            }
                        )
                        continue

                    if RecycleAsset.objects.filter(outasset_recordcode=outasset, is_deleted=False).exists():
                        fail_items.append(
                            {
                                "id": recordcode,
                                "error_code": "HAS_RECYCLE_RECORDS",
                                "error_message": "出库记录存在关联回收记录，不允许删除",
                            }
                        )
                        continue

                    previous_status = outasset.outasset_previous_status or "in_store"

                    outasset.delete()

                    AssetFSM.cancel_outasset(asset, previous_status)

                    asset.asset_applicant_recordcode = None
                    asset.asset_manager_recordcode = None
                    asset.asset_using_location = None

                    update_fields = [
                        "asset_current_status",
                        "asset_applicant_recordcode",
                        "asset_manager_recordcode",
                        "asset_using_location",
                    ]
                    if previous_status == "in_store":
                        asset.asset_storage_recordcode = None
                        update_fields.append("asset_storage_recordcode")

                    asset.save(update_fields=update_fields)

                success_ids.append(recordcode)

            except InvalidTransitionError as e:
                fail_items.append({"id": recordcode, "error_code": "INVALID_STATE_TRANSITION", "error_message": str(e)})
            except Exception:
                fail_items.append(
                    {"id": recordcode, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误，请稍后重试"}
                )

        return {
            "total": len(recordcodes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items,
        }
