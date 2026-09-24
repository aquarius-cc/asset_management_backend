"""
出库资产管理服务

提供资产出库的业务逻辑,包括出库记录创建、状态变更等操作。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
from apps.assetmanagement.selectors import OutAssetSelector
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError
from core.locks import lock_row_or_409


# 字段白名单
OUTASSET_UPDATE_ALLOWED_FIELDS = frozenset(
    [
        "outasset_type",
        "outasset_number",
        "outasset_description",
        "outasset_using_location",
        "return_date",
        "outasset_date",
        "outasset_applicant_recordcode",
        "outasset_manager_recordcode",
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

        OutAssetService._validate_outasset_source(asset)

        outasset_data["outasset_previous_status"] = asset.asset_current_status

        applicant = outasset_data.pop("outasset_applicant", None)
        manager = outasset_data.pop("outasset_manager", None)
        using_location = outasset_data.pop("outasset_using_location", None)

        # 设置 OutAsset 表的 FK 字段
        outasset_data["outasset_applicant_recordcode"] = applicant
        outasset_data["outasset_manager_recordcode"] = manager
        outasset_data["outasset_using_location"] = using_location

        outasset_data["outasset_snapshot"] = OutAssetService._build_outasset_snapshot(
            asset, applicant, manager, using_location
        )

        outasset = OutAsset.objects.create(**outasset_data)

        asset = OutAssetService._apply_outasset_to_asset(asset, applicant, manager, using_location)

        AuditLogger.log_asset_out(
            asset=asset,
            outrecordcode=outasset.recordcode,
            operator_jobcode=operator_jobcode or (applicant.employee_jobcode if applicant else None),
            operator_name=operator_name,
        )

        return outasset  # type: ignore[no-any-return]

    @staticmethod
    def _validate_outasset_source(asset: Asset) -> None:
        """校验出库源状态:仅 in_store / recycled_pending 允许出库"""
        if asset.asset_current_status not in [Asset.AssetStatus.IN_STORE, Asset.AssetStatus.RECYCLED_PENDING]:
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status},不能出库",
                error_code="ILLEGAL_OUTASSET",  # 2001: 非法出库
            )

    @staticmethod
    def _build_outasset_snapshot(asset: Asset, applicant: Any, manager: Any, using_location: Any) -> dict[str, Any]:
        """构建 JSON 快照(包含恢复所需的所有字段)

        【P0-2 修复】applicant/manager/using_location 为出库单目标值(仅追溯展示);
        original_* 为出库前资产原值,取消出库时用于恢复原始字段。
        """
        return {
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
            "asset_storage_recordcode": (
                asset.asset_storage_recordcode.recordcode if asset.asset_storage_recordcode else None
            ),
            "original_applicant": (
                {
                    "jobcode": asset.asset_applicant_recordcode.employee_jobcode,
                    "name": asset.asset_applicant_recordcode.employee_name,
                }
                if asset.asset_applicant_recordcode
                else None
            ),
            "original_manager": (
                {
                    "jobcode": asset.asset_manager_recordcode.employee_jobcode,
                    "name": asset.asset_manager_recordcode.employee_name,
                }
                if asset.asset_manager_recordcode
                else None
            ),
            "original_using_location": asset.asset_using_location,
        }

    @staticmethod
    def _build_asset_people_update(asset: Asset, applicant: Any, manager: Any, using_location: Any) -> list[str]:
        """组装 Asset 主表申请人/保管人/使用地点字段更新(Dynamic update_fields,create/update 共用)"""
        update_fields: list[str] = []
        if applicant is not None:
            asset.asset_applicant_recordcode = applicant
            update_fields.append("asset_applicant_recordcode")
        if manager is not None:
            asset.asset_manager_recordcode = manager
            update_fields.append("asset_manager_recordcode")
        if using_location is not None:
            asset.asset_using_location = using_location
            update_fields.append("asset_using_location")
        return update_fields

    @staticmethod
    def _apply_outasset_to_asset(asset: Asset, applicant: Any, manager: Any, using_location: Any) -> Asset:
        """锁行并执行出库:FSM 转换 + 资产字段变化 + 定向 save"""
        # F-P2-8: 锁超时收敛至核心助手
        asset = lock_row_or_409(Asset.objects.select_for_update(), pk=asset.pk)

        try:
            AssetFSM.outasset(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

        asset.asset_storage_recordcode = None
        # F-P2-9 (AC-30): 出库资产 usage_type → used(唯一实现点;删除/取消出库不回退)
        asset.usage_type = Asset.UsageType.USED
        update_fields = ["asset_current_status", "asset_storage_recordcode", "usage_type"]
        update_fields += OutAssetService._build_asset_people_update(asset, applicant, manager, using_location)
        asset.save(update_fields=update_fields)

        return asset

    @staticmethod
    def _build_update_audit_snapshot(
        outasset: OutAsset,
        update_data: dict[str, Any],
        applicant: Any,
        manager: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """组装出库更新审计 before/after 快照(jobcode 口径),并完成 FK 字段名重映射"""
        before_data: dict[str, Any] = {}
        for key in update_data:
            before_data[key] = getattr(outasset, key)
        if applicant is not None:
            current_applicant = getattr(outasset, "outasset_applicant_recordcode", None)
            before_data["outasset_applicant"] = current_applicant.employee_jobcode if current_applicant else None
        if manager is not None:
            current_manager = getattr(outasset, "outasset_manager_recordcode", None)
            before_data["outasset_manager"] = current_manager.employee_jobcode if current_manager else None

        if applicant is not None:
            update_data["outasset_applicant_recordcode"] = applicant
        if manager is not None:
            update_data["outasset_manager_recordcode"] = manager

        after_data = dict(update_data)
        for key in ("outasset_applicant_recordcode", "outasset_manager_recordcode"):
            if key in after_data:
                emp = after_data[key]
                after_data[key] = emp.employee_jobcode if emp else None
        return before_data, after_data

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
        outasset = OutAsset.objects.select_for_update().get(pk=outasset.pk)

        applicant = update_data.pop("outasset_applicant", None)
        manager = update_data.pop("outasset_manager", None)

        before_data, after_data = OutAssetService._build_update_audit_snapshot(
            outasset, update_data, applicant, manager
        )

        for key, value in update_data.items():
            if key in OUTASSET_UPDATE_ALLOWED_FIELDS:
                setattr(outasset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}", error_code="FIELD_NOT_ALLOWED")

        outasset.save()

        asset = outasset.asset_recordcode
        if asset is not None:
            # F-P2-8: 锁超时收敛至核心助手(update_outasset 关联资产锁)
            asset = lock_row_or_409(Asset.objects.select_for_update(), pk=asset.pk)
            update_fields = OutAssetService._build_asset_people_update(
                asset, applicant, manager, update_data.get("outasset_using_location")
            )
            if update_fields:
                asset.save(update_fields=update_fields)

        AuditLogger.log_asset_update(
            asset=outasset.asset_recordcode,
            before_data=before_data,
            after_data=after_data,
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
            bulk_item = copy.deepcopy(outasset_data)
            # 键名归一(批量契约适配):批量端点 validated_data 以 outasset_asset(Asset 实例)携带资产,
            # 单条入口 create_outasset 期望 asset_recordcode;直接调用方已用 asset_recordcode 则透传。
            # row_number 为批量框架索引元数据,非 OutAsset 模型字段,过滤避免 create() 收到多余键。
            if "outasset_asset" in bulk_item:
                bulk_item["asset_recordcode"] = bulk_item.pop("outasset_asset")
            bulk_item.pop("row_number", None)
            return OutAssetService.create_outasset(
                outasset_data=bulk_item,
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
        from core.batch_mixins import BatchOperationMixin

        return BatchOperationMixin.batch_delete_execute(
            ids=recordcodes,
            process_fn=lambda recordcode: OutAssetService._delete_one(recordcode, operator_jobcode, operator_name),
        )

    @staticmethod
    def _delete_one(recordcode: str, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        outasset = OutAssetSelector.get_outasset_for_update(recordcode)
        if not outasset:
            raise AppValidationError(detail=f"出库记录 {recordcode} 不存在", error_code="NOT_FOUND")

        # F-P2-8: 锁超时收敛至核心助手(关联资产锁;出库单持有确已存在的关联资产)
        asset = lock_row_or_409(
            Asset.objects.select_for_update(), pk=outasset.asset_recordcode.pk  # type: ignore[union-attr]
        )
        if asset.asset_current_status != Asset.AssetStatus.IN_USE:
            raise AppValidationError(
                detail=f"关联资产当前状态为 {asset.asset_current_status},不允许删除出库记录",
                error_code="STATUS_NOT_ALLOWED",
            )
        if RecycleAsset.objects.filter(outasset_recordcode=outasset, is_deleted=False).exists():
            raise AppValidationError(detail="出库记录存在关联回收记录,不允许删除", error_code="HAS_RECYCLE_RECORDS")

        previous_status = outasset.outasset_previous_status or Asset.AssetStatus.IN_STORE

        outasset.delete()

        try:
            AssetFSM.cancel_outasset(asset, previous_status)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION")

        OutAssetService._restore_asset_fields(asset, outasset, previous_status)

        AuditLogger.log_state_change(
            asset=asset,
            from_state=Asset.AssetStatus.IN_USE,
            to_state=previous_status,
            trigger="cancel_outasset",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def _restore_asset_fields(asset: Asset, outasset: OutAsset, previous_status: str) -> None:
        """从快照恢复资产字段(而非清空为 None)

        恢复语义:original_* 原值优先(落空置 None),降级用出库单目标值;
        仅当原状态 in_store 时从快照恢复仓库。
        """
        snapshot = outasset.outasset_snapshot or {}

        update_fields = ["asset_current_status"]

        for original_key, fallback_key, field_attr in (
            ("original_applicant", "applicant", "asset_applicant_recordcode"),
            ("original_manager", "manager", "asset_manager_recordcode"),
        ):
            restore, value = OutAssetService._resolve_snapshot_employee(snapshot, original_key, fallback_key)
            if restore:
                setattr(asset, field_attr, value)
                update_fields.append(field_attr)

        if "original_using_location" in snapshot:
            asset.asset_using_location = snapshot["original_using_location"]
            update_fields.append("asset_using_location")
        elif snapshot.get("using_location"):
            asset.asset_using_location = snapshot["using_location"]
            update_fields.append("asset_using_location")

        # 恢复仓库(仅当原状态为 in_store 时,从快照恢复)
        if previous_status == Asset.AssetStatus.IN_STORE and snapshot.get("asset_storage_recordcode"):
            from apps.assetmanagement.models import Storage

            storage = Storage.objects.filter(recordcode=snapshot["asset_storage_recordcode"]).first()
            if storage:
                asset.asset_storage_recordcode = storage
                update_fields.append("asset_storage_recordcode")

        asset.save(update_fields=update_fields)

    @staticmethod
    def _resolve_snapshot_employee(snapshot: dict[str, Any], original_key: str, fallback_key: str) -> tuple[bool, Any]:
        """解析快照员工:original 键在则必须覆盖(含落空置 None),否则尝试 fallback 定向"""
        if original_key in snapshot:
            original = snapshot[original_key]
            if original and original.get("jobcode"):
                from apps.usermanagement.selectors import EmployeeSelector

                return True, EmployeeSelector.get_employee_by_jobcode(original["jobcode"])
            return True, None
        fallback = snapshot.get(fallback_key)
        if fallback and fallback.get("jobcode"):
            from apps.usermanagement.selectors import EmployeeSelector

            return True, EmployeeSelector.get_employee_by_jobcode(fallback["jobcode"])
        return False, None
