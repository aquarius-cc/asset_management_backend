"""
资产管理服务

提供资产管理的核心业务逻辑,包括资产的创建、更新、删除、状态变更等操作。
"""

import json
import string
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, DamagedAsset, OutAsset
from apps.assetmanagement.selectors import (
    AssetSelector,
    StorageSelector,
)
from apps.assetmanagement.state_machine import AssetFSM, AssetState, InvalidTransitionError
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError

from .asset_lifecycle_mixin import AssetLifecycleMixin


# 不可变字段集(防御纵深,非字段白名单):
# - 标识/系统字段不可经通用更新接口修改
# - asset_current_status 的变更所有权归状态机(FSM 专用入口),保证 CT-3 全路径约束
# 字段来源唯一性由 AssetUpdateSerializer 承担(DR-1);入参必须是已校验的 validated_data
ASSET_UPDATE_IMMUTABLE_FIELDS = frozenset(
    [
        "asset_code",
        "recordcode",
        "qr_code",
        "version",
        "is_deleted",
        "created_at",
        "updated_at",
        "asset_current_status",
    ]
)


def _run_manual_transition(asset: Asset, target_state: AssetState) -> None:
    """手动改状态的 FSM 收口(#38)

    将 FSM 内部的 InvalidTransitionError 映射为业务校验异常,
    避免裸异常逃逸服务层导致未处理 500。
    """
    try:
        AssetFSM._transition(asset, target_state)
    except InvalidTransitionError as e:
        raise AppValidationError(detail=str(e), error_code="INVALID_STATE_TRANSITION") from None


class AssetCodeGenerator:
    """
    资产编码生成器

    后端自动生成 asset_code,前端无需传递。
    生成格式:{类型层级路径}-{8位大写UUID}
    """

    RANDOM_CHARS = string.ascii_uppercase + string.digits
    RANDOM_LENGTH = 8
    MAX_RETRY = 3

    @classmethod
    def _generate_uuid_hex(cls) -> str:
        return uuid.uuid4().hex[:8].upper()

    @classmethod
    def _get_type_path(cls, asset_type: Any) -> str:
        """获取资产类型的层级路径,如 'IT-COMPUTER-NOTEBOOK'"""
        if not asset_type:
            return "UNKNOWN"
        path_parts = []
        current = asset_type
        max_depth = 10
        while current and max_depth > 0:
            path_parts.append(current.type_code)
            if current.parent:
                current = current.parent
            else:
                break
            max_depth -= 1
        path_parts.reverse()
        return "-".join(path_parts)

    @classmethod
    def generate(cls, asset_type: Any, purchase_number: int = 1) -> list[str]:
        if purchase_number < 1:
            raise ValueError("purchase_number 必须 >= 1")
        type_path = cls._get_type_path(asset_type)
        uuid_hex = cls._generate_uuid_hex()
        codes = []
        for i in range(1, purchase_number + 1):
            if purchase_number > 1:
                code = f"{type_path}-{uuid_hex}{i:04d}"
            else:
                code = f"{type_path}-{uuid_hex}"
            codes.append(code)
        return codes

    @classmethod
    def generate_with_unique_check(cls, asset_type: Any, purchase_number: int = 1) -> list[str]:
        for _ in range(cls.MAX_RETRY):
            codes = cls.generate(asset_type, purchase_number)
            existing = Asset.objects.filter(asset_code__in=codes).values_list("asset_code", flat=True)
            if not existing:
                return codes
        raise RuntimeError(f"生成资产编码失败:连续 {cls.MAX_RETRY} 次尝试均存在唯一性冲突")


class AssetService(AssetLifecycleMixin, BatchOperationMixin):
    """
    资产管理服务

    提供资产全生命周期管理的业务逻辑。
    CRUD 操作在此类中定义,生命周期流转方法继承自 AssetLifecycleMixin。
    """

    @staticmethod
    @transaction.atomic
    def create_asset(
        asset_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> list[Asset]:
        asset_data = dict(asset_data)
        asset_data.pop("asset_code", None)
        asset_type = asset_data.get("asset_type_recordcode")
        purchase_number = asset_data.get("asset_purchase_number", 1)
        # 创建资产初始状态统一注入 in_store,禁止客户端指定(CT-3);
        # 需在防污染拷贝(dict(asset_data))之后覆写,不污染调用方原 dict。
        asset_data["asset_current_status"] = Asset.AssetStatus.IN_STORE
        codes = AssetCodeGenerator.generate_with_unique_check(
            asset_type=asset_type,
            purchase_number=purchase_number,
        )
        created_assets = []
        for code in codes:
            single_data = {**asset_data, "asset_code": code}
            # 自动生成 qr_code 内容(JSON 格式,供前端扫码使用)
            if not single_data.get("qr_code"):
                single_data["qr_code"] = json.dumps(
                    {
                        "asset_code": code,
                        "scan_type": "asset_detail",
                    }
                )
            asset = Asset.objects.create(**single_data)
            AuditLogger.log_asset_create(
                asset=asset,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
            created_assets.append(asset)
        return created_assets

    @staticmethod
    @transaction.atomic
    def update_asset(
        asset_code: str,
        update_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> Asset:
        """更新资产(入参必须是 Serializer 校验后的 validated_data)。

        字段来源唯一性由 AssetUpdateSerializer 承担(DR-1),Service 仅保留
        ASSET_UPDATE_IMMUTABLE_FIELDS 不可变集作为防御纵深:
        - 状态变更(asset_current_status)必须走 FSM 专用入口(CT-3);
        - 标识/系统字段不可经通用更新接口修改。

        validated_data 中 FK 字段为模型实例,审计快照统一 str() 归一化,
        保证 OperationLog JSON 字段可序列化。

        user 必填(B12): 行级隔离,不可见与不存在同义(ASSET_NOT_FOUND)。
        """
        asset = AssetSelector.get_asset_by_code(asset_code, user=user)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        # B12 TOCTOU 兜底: 锁内重取快照后再次校验行级可见性
        AssetSelector.ensure_asset_visible(asset, user)

        def _normalize(value: Any) -> Any:
            # FK 实例 → 其 recordcode（FK 列真实值，与存量审计日志口径一致）；
            # 无 recordcode 的兜底取 pk；Decimal/date 等非 JSON 原生类型转 str；
            # 其余标量原样
            if hasattr(value, "pk"):
                return str(getattr(value, "recordcode", value.pk))
            if isinstance(value, (Decimal, date, datetime, time, UUID)):
                return str(value)
            return value

        for key in update_data:
            if key in ASSET_UPDATE_IMMUTABLE_FIELDS:
                raise AppValidationError(detail=f"不允许修改字段: {key}", error_code="FIELD_NOT_ALLOWED")
        before_data = {key: _normalize(getattr(asset, key)) for key in update_data}
        for key, value in update_data.items():
            setattr(asset, key, value)
        asset.save()
        AuditLogger.log_asset_update(
            asset=asset,
            before_data=before_data,
            after_data={key: _normalize(value) for key, value in update_data.items()},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return asset

    @staticmethod
    def _delete_guarded(
        asset: Asset,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """删除守卫 + 审计 + 软删除的唯一实现(单条/批量共用,DR-1);失败抛 AppValidationError"""
        # [HALT] 统一删除入口:状态/出库/待报废守卫 + 审计 + asset.delete()
        if asset.asset_current_status != Asset.AssetStatus.IN_STORE:
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status},不允许删除", error_code="ASSET_IN_USE"
            )
        if OutAsset.objects.filter(asset_recordcode=asset, is_deleted=False).exists():
            raise AppValidationError(
                detail=f"资产 {asset.asset_code} 存在未完成的出库记录", error_code="ASSET_HAS_OUTASSET"
            )
        if DamagedAsset.objects.filter(asset_recordcode=asset, is_deleted=False).exists():
            raise AppValidationError(detail="资产存在待报废记录,不允许删除", error_code="HAS_DAMAGED_RECORDS")
        AuditLogger.log_asset_delete(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset=asset,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        asset.delete()

    @staticmethod
    @transaction.atomic
    def delete_asset(
        asset_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> None:
        asset = AssetSelector.get_asset_by_code(asset_code, user=user)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        # B12 TOCTOU 兜底: 锁内重取快照后再次校验行级可见性
        AssetSelector.ensure_asset_visible(asset, user)
        AssetService._delete_guarded(asset, operator_jobcode, operator_name)

    @staticmethod
    def batch_create_asset(
        asset_data_list: list[dict[str, Any]], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        def _create_item(idx: int, asset_data: dict[str, Any]) -> Asset | None:
            import copy

            result = AssetService.create_asset(
                asset_data=copy.deepcopy(asset_data),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
            return result[0] if result else None

        return BatchOperationMixin.batch_execute(
            items=asset_data_list,
            process_fn=_create_item,
            max_batch_size=100,
            use_transaction=False,
        )

    @staticmethod
    def batch_delete_asset(
        asset_codes: list[str],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> dict[str, Any]:
        def _delete_one(asset_code: str) -> None:
            # B12 行级隔离: 不可见/不存在统一归入 NOT_FOUND,响应结构不变。
            # 先经 scoped 查询解析(外层连接过滤不可用于 select_for_update,
            # PostgreSQL 会拒绝锁取 outer join 的可空侧),再按主键加锁 + TOCTOU 兜底。
            asset = AssetSelector.get_asset_by_code(asset_code, user=user)
            if not asset:
                raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="NOT_FOUND")
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            try:
                AssetSelector.ensure_asset_visible(asset, user)
            except AppValidationError:
                raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="NOT_FOUND") from None
            # 守卫须在 try 之外: ASSET_IN_USE/ASSET_HAS_OUTASSET/HAS_DAMAGED_RECORDS
            # 原样抛给 batch_delete_execute,禁止误映射为 NOT_FOUND
            AssetService._delete_guarded(asset, operator_jobcode, operator_name)

        return BatchOperationMixin.batch_delete_execute(ids=asset_codes, process_fn=_delete_one)

    @staticmethod
    @transaction.atomic
    def change_asset_status(
        asset_code: str,
        new_status: str,
        description: str = "",
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> Asset:
        valid_statuses = dict(Asset.ASSET_STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise AppValidationError(detail=f"无效的资产状态: {new_status}", error_code="INVALID_ASSET_STATUS")
        asset = AssetSelector.get_asset_by_code(asset_code, user=user)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        # B12 TOCTOU 兜底: 锁内重取快照后再次校验行级可见性
        AssetSelector.ensure_asset_visible(asset, user)
        old_status = asset.asset_current_status
        target_state = AssetState.from_string(new_status)
        _run_manual_transition(asset, target_state)
        AuditLogger.log_state_change(
            asset=asset,
            from_state=old_status,
            to_state=new_status,
            trigger="manual_change",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        asset.save()
        return asset

    @staticmethod
    @transaction.atomic
    def change_outasset_employee(
        asset_code: str,
        applicant_jobcode: str,
        manager_jobcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code, user=user)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        # B12 TOCTOU 兜底: 锁内重取快照后再次校验行级可见性
        AssetSelector.ensure_asset_visible(asset, user)
        old_applicant = asset.asset_applicant_recordcode
        old_manager = asset.asset_manager_recordcode
        asset.asset_applicant_recordcode = applicant_jobcode  # type: ignore[assignment]
        asset.asset_manager_recordcode = manager_jobcode  # type: ignore[assignment]
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={"asset_applicant": str(old_applicant), "asset_manager": str(old_manager)},
            after_data={"asset_applicant": applicant_jobcode, "asset_manager": manager_jobcode},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        asset.save()
        return asset

    @staticmethod
    @transaction.atomic
    def transfer_asset_to_storage(
        asset_code: str,
        storage_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        *,
        user: Any,
    ) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code, user=user)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        # B12 TOCTOU 兜底: 锁内重取快照后再次校验行级可见性
        AssetSelector.ensure_asset_visible(asset, user)
        storage = StorageSelector.get_storage_by_code(storage_code)
        if not storage:
            raise AppValidationError(detail=f"仓库 {storage_code} 不存在", error_code="STORAGE_NOT_FOUND")
        old_storage = asset.asset_storage_recordcode
        asset.asset_storage_recordcode = storage
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={"asset_storage": old_storage.storage_name if old_storage else None},
            after_data={"asset_storage": storage.storage_name},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        asset.save()
        return asset

    @staticmethod
    def get_asset_statistics(user: Any = None) -> dict[str, Any]:
        return AssetSelector.get_asset_statistics(user=user)

    @staticmethod
    def generate_qr_code_image(asset: Any, base_url: str) -> bytes:
        """
        生成资产二维码 PNG 图片

        Args:
            asset: 资产实例
            base_url: 基础 URL(如 http://host:port)

        Returns:
            bytes: PNG 图片数据

        Raises:
            ImportError: 缺少 qrcode 依赖
        """
        from io import BytesIO

        import qrcode

        scan_url = f"{base_url}/scan/{asset.recordcode}/"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.getvalue()
