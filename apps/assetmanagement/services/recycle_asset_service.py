"""
回收资产管理服务

提供资产回收的业务逻辑,包括回收记录创建、资产状态更新等操作。
"""

import copy
from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, BrokenAsset, LostAsset, OutAsset, RecycleAsset, Storage
from apps.assetmanagement.selectors import OutAssetSelector
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from apps.usermanagement.models import Employee
from apps.usermanagement.selectors import EmployeeSelector
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError


# 字段白名单:允许通过 update_recycle_asset 修改的字段
RECYCLE_ASSET_UPDATE_ALLOWED_FIELDS = frozenset(
    [
        "recycle_asset_date",
        "recycle_type",
        "recycle_asset_description",
    ]
)


class RecycleAssetService:
    """
    回收资产管理服务

    提供资产回收的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_recycle_asset(
        recycle_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> RecycleAsset:
        """
        创建回收记录

        接受灵活的 recycle_data:
        - outasset_recordcode: OutAsset 对象或 recordcode 字符串
        - recycle_asset_storage: Storage 对象或 storage_code 字符串
        - recycle_asset_recycle_person_jobcode: Employee 对象或 employee_jobcode 字符串
        - asset_recordcode: 可选,未提供时从 outasset 自动推导
        """
        storage_obj = recycle_data.pop("recycle_asset_storage", None)
        recycle_person_obj = recycle_data.pop("recycle_asset_recycle_person_jobcode", None)

        if storage_obj is not None and not isinstance(storage_obj, Storage):
            storage_obj = Storage.objects.filter(storage_code=str(storage_obj)).first()
        if recycle_person_obj is not None and not isinstance(recycle_person_obj, Employee):
            recycle_person_obj = EmployeeSelector.get_employee_by_jobcode(str(recycle_person_obj))

        outasset_recordcode = recycle_data.get("outasset_recordcode")
        if not outasset_recordcode:
            raise AppValidationError(detail="缺少出库记录编码", error_code="MISSING_OUTASSET_RECORDCODE")

        outasset_code = getattr(outasset_recordcode, "recordcode", None) or str(outasset_recordcode)
        outasset = OutAssetSelector.get_outasset_by_record_code(outasset_code)
        if not outasset:
            raise AppValidationError(detail=f"出库记录 {outasset_code} 不存在", error_code="OUTASSET_NOT_FOUND")

        recycle_data["outasset_recordcode"] = outasset

        asset = outasset.asset_recordcode
        if asset.asset_current_status != Asset.AssetStatus.IN_USE:
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status},不能回收",
                error_code="INVALID_ASSET_STATUS_FOR_RECYCLE",
            )

        if not recycle_data.get("asset_recordcode"):
            recycle_data["asset_recordcode"] = asset

        if recycle_person_obj and not recycle_data.get("operator_employee"):
            recycle_data["operator_employee"] = recycle_person_obj

        if not recycle_data.get("operator_employee") and operator_jobcode:
            operator_employee = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)
            if operator_employee:
                recycle_data["operator_employee"] = operator_employee

        is_broken = recycle_data.pop("is_broken", False)
        broken_reason = recycle_data.pop("broken_reason", "")
        is_lost = recycle_data.pop("is_lost", False)
        lost_reason = recycle_data.pop("lost_reason", "")

        recycle_asset = RecycleAsset.objects.create(**recycle_data)

        asset = Asset.objects.select_for_update().get(pk=asset.pk)

        # AC-32/AC-33: 回收时标记损坏/遗失
        if is_broken:
            # 回收 → recycled_pending → broken(两次 FSM 转换合并为一次 save)
            RecycleAssetService._do_recycle_asset_update(
                asset, storage_obj, recycle_person_obj, recycle_asset,
                operator_jobcode, operator_name,
            )
            try:
                AssetFSM.mark_broken(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
            asset.save(update_fields=["asset_current_status"])

            BrokenAsset.objects.create(
                asset_recordcode=asset,
                broken_date=recycle_asset.recycle_asset_date,
                broken_reason=broken_reason or "回收时发现损坏",
                broken_description=f"回收时发现损坏,回收记录: {recycle_asset.recordcode}",
                operator_employee=recycle_person_obj,
            )

        elif is_lost:
            # 回收 → recycled_pending → lost(两次 FSM 转换合并为一次 save)
            RecycleAssetService._do_recycle_asset_update(
                asset, storage_obj, recycle_person_obj, recycle_asset,
                operator_jobcode, operator_name,
            )
            try:
                AssetFSM.mark_lost(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")
            asset.save(update_fields=["asset_current_status"])

            LostAsset.objects.create(
                asset_recordcode=asset,
                lost_date=recycle_asset.recycle_asset_date,
                lost_reason=lost_reason or "回收时发现遗失",
                lost_description=f"回收时发现遗失,回收记录: {recycle_asset.recordcode}",
                operator_employee=recycle_person_obj,
            )

        else:
            # 正常回收(无损坏/遗失标记)
            RecycleAssetService._do_recycle_asset_update(
                asset, storage_obj, recycle_person_obj, recycle_asset,
                operator_jobcode, operator_name,
            )

        return recycle_asset

    @staticmethod
    def _do_recycle_asset_update(
        asset: Asset,
        storage_obj: "Storage | None",
        recycle_person_obj: "Employee | None",
        recycle_asset: RecycleAsset,
        operator_jobcode: str | None,
        operator_name: str | None,
    ) -> None:
        """执行回收的公共逻辑:FSM 转换 + 字段清空 + 审计日志。

        三个分支(normal/broken/lost)共享此逻辑。
        broken/lost 分支调用后需自行执行第二次 FSM 转换 + 创建子记录。
        """
        try:
            AssetFSM.recycle(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

        if storage_obj:
            asset.asset_storage_recordcode = storage_obj
        if recycle_person_obj:
            asset.asset_entry_person_recordcode = recycle_person_obj
        asset.asset_applicant_recordcode = None
        asset.asset_manager_recordcode = None
        asset.asset_using_location = None

        update_fields = [
            "asset_current_status",
            "asset_applicant_recordcode",
            "asset_manager_recordcode",
            "asset_using_location",
        ]
        if storage_obj:
            update_fields.append("asset_storage_recordcode")
        if recycle_person_obj:
            update_fields.append("asset_entry_person_recordcode")
        asset.save(update_fields=update_fields)

        # 审计日志:operator_jobcode 回退到 recycle_person 的工号(避免传入 Employee 对象)
        fallback_jobcode = recycle_person_obj.employee_jobcode if recycle_person_obj else None
        AuditLogger.log_asset_recycle(
            asset=asset,
            recordcode=recycle_asset.recordcode,
            operator_jobcode=operator_jobcode or fallback_jobcode,
            operator_name=operator_name or "",
        )

    @staticmethod
    @transaction.atomic
    def update_recycle_asset(
        recordcode: str,
        update_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> RecycleAsset:
        """
        更新回收记录
        """
        recycle_asset = RecycleAsset.objects.filter(recordcode=recordcode, is_deleted=False).first()
        if not recycle_asset:
            raise AppValidationError(detail=f"回收记录 {recordcode} 不存在", error_code="RECYCLE_ASSET_NOT_FOUND")

        before_data = {key: getattr(recycle_asset, key) for key in update_data.keys()}

        for key, value in update_data.items():
            if key in RECYCLE_ASSET_UPDATE_ALLOWED_FIELDS:
                setattr(recycle_asset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}", error_code="FIELD_NOT_ALLOWED")

        recycle_asset.save()

        AuditLogger.log_asset_update(
            asset=recycle_asset.outasset_recordcode.asset_recordcode if recycle_asset.outasset_recordcode else None,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return recycle_asset

    @staticmethod
    def batch_create_recycle_asset(
        recycle_data_list: list[dict[str, Any]], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        def _create_item(idx: int, recycle_data: dict[str, Any]) -> RecycleAsset:
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
        recordcodes: list[str], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        from core.batch_mixins import BatchOperationMixin

        def _delete_one(record_code: str) -> None:
            recycle_asset = (
                RecycleAsset.objects.select_for_update().filter(recordcode=record_code, is_deleted=False).first()
            )
            if not recycle_asset:
                raise AppValidationError(detail=f"回收记录 {record_code} 不存在", error_code="NOT_FOUND")

            asset = Asset.objects.select_for_update().get(pk=recycle_asset.asset_recordcode.pk)
            if asset.asset_current_status != Asset.AssetStatus.RECYCLED_PENDING:
                raise AppValidationError(
                    detail=f"关联资产当前状态为 {asset.asset_current_status},不允许删除回收记录",
                    error_code="STATUS_NOT_ALLOWED",
                )
            # 保存关联的出库记录信息,用于恢复资产字段
            outasset = OutAsset.objects.filter(
                recordcode=recycle_asset.outasset_recordcode_id, is_deleted=False
            ).first()

            recycle_asset.delete()

            try:
                AssetFSM.cancel_recycle(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

            # 恢复资产的申请人、保管人、使用地点(从出库记录恢复)
            update_fields = ["asset_current_status"]
            if outasset:
                if outasset.outasset_applicant_recordcode:
                    asset.asset_applicant_recordcode = outasset.outasset_applicant_recordcode
                    update_fields.append("asset_applicant_recordcode")
                if outasset.outasset_manager_recordcode:
                    asset.asset_manager_recordcode = outasset.outasset_manager_recordcode
                    update_fields.append("asset_manager_recordcode")
                if outasset.outasset_using_location:
                    asset.asset_using_location = outasset.outasset_using_location
                    update_fields.append("asset_using_location")
            asset.save(update_fields=update_fields)

            AuditLogger.log_state_change(
                asset=asset,
                from_state=Asset.AssetStatus.RECYCLED_PENDING,
                to_state=Asset.AssetStatus.IN_USE,
                trigger="cancel_recycle",
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_delete_execute(ids=recordcodes, process_fn=_delete_one)

    @staticmethod
    @transaction.atomic
    def reissue_recycle_asset(
        recordcode: str, operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> "OutAsset":
        """
        重新发放:将已回收待发放的资产重新出库

        业务规则:
        1. 资产状态必须为 recycled_pending
        2. 资产不能处于损坏或遗失状态(is_broken=False, is_lost=False)
        3. 调用 OutAssetService.create_outasset 重新出库
        """
        from apps.assetmanagement.services.out_asset_service import OutAssetService

        recycle_asset = (
            RecycleAsset.objects.filter(recordcode=recordcode, is_deleted=False)
            .select_related("asset_recordcode")
            .first()
        )
        if not recycle_asset:
            raise AppValidationError(detail=f"回收记录 {recordcode} 不存在", error_code="RECYCLE_ASSET_NOT_FOUND")

        asset = recycle_asset.asset_recordcode
        if not asset:
            raise AppValidationError(detail="回收记录未关联资产", error_code="MISSING_RELATED_ASSET")

        if asset.asset_current_status != "recycled_pending":
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status},只有已回收待发放的资产才能重新发放",
                error_code="INVALID_ASSET_STATUS_FOR_REISSUE",
            )

        # 准备出库数据
        outasset_data = {
            "asset_recordcode": asset,
            "outasset_type": OutAsset.OutassetType.REISSUE,
            "outasset_number": 1,
            "outasset_description": f"重新发放 - 原回收记录: {recycle_asset.recordcode}",
        }

        return OutAssetService.create_outasset(
            outasset_data=outasset_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
