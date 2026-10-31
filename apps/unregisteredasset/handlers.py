"""
未登记资产审批处理函数

封装 S1/S2/S3 场景的具体处理逻辑,由 UnregisteredAssetService.approve_and_handle() 调用。

函数列表:
- _validate_handle_type(): 验证处理方式与场景匹配
- _generate_asset_code(): 生成唯一资产编码
- _handle_s1_create_and_recycle(): S1场景创建并回收
- _handle_s1_create_and_damaged(): S1场景创建并待报废
- _handle_s2_supplement_and_recycle(): S2场景补建并回收
- _handle_s3_correct_and_recycle(): S3场景修正并回收
"""

from __future__ import annotations

import secrets
import string
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.unregisteredasset.models import UnregisteredAsset
from core.exceptions import AppValidationError


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset


def _validate_handle_type(scenario_type: str, handle_type: str) -> None:
    """
    验证处理方式与场景类型匹配

    Args:
        scenario_type: 场景类型
        handle_type: 处理方式

    Raises:
        AppValidationError: 不匹配时抛出
    """
    valid_mapping = {
        "s1_no_record": ["create_and_recycle", "create_and_damaged", "reject"],
        "s2_no_outasset": ["supplement_and_recycle", "reject"],
        "s3_status_mismatch": ["correct_and_recycle", "reject"],
    }

    valid_types = valid_mapping.get(scenario_type, [])
    if handle_type not in valid_types:
        raise AppValidationError(
            detail=f"场景 {scenario_type} 不支持处理方式 {handle_type},有效选项: {', '.join(valid_types)}"
        )


def _generate_asset_code() -> str:
    """
    生成唯一资产编码

    Returns:
        str: 格式为 AST-YYYYMMDD-XXXXXX 的唯一编码
    """
    prefix = "AST"
    date_str = timezone.now().strftime("%Y%m%d")
    random_suffix = "".join(secrets.choice(string.digits) for _ in range(6))
    return f"{prefix}-{date_str}-{random_suffix}"


def _create_unregistered_asset(unregistered: UnregisteredAsset) -> Asset:
    """构建并创建新资产记录(S1 两个处理方式共用)"""
    from apps.assetmanagement.models import Asset

    asset_data = {
        "asset_code": _generate_asset_code(),
        "asset_name": unregistered.asset_name,
        "asset_brand": unregistered.asset_brand,
        "asset_specification": unregistered.asset_specification,
        "asset_type_recordcode": unregistered.unregistered_asset_type,
        "asset_purchase_price": unregistered.estimated_value or Decimal("0"),
        "asset_purchase_date": unregistered.discovery_date,
        "asset_entry_date": timezone.now().date(),
        "asset_storage_recordcode": unregistered.unregistered_asset_storage,
    }
    return Asset.objects.create(**asset_data)  # type: ignore[no-any-return]


def _create_receive_outasset(unregistered: UnregisteredAsset, asset: Asset, description: str) -> OutAsset:
    """补建 receive 类型出库记录(S1/S2/S3 共用),description 由调用方参数化"""
    from apps.assetmanagement.models import OutAsset

    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": description,
    }
    return OutAsset.objects.create(**outasset_data)  # type: ignore[no-any-return]


def _create_recycle_record(
    asset: Asset,
    outasset: OutAsset,
    operator_employee: Any,
    description: str,
) -> RecycleAsset:
    """创建回收记录(S1/S2/S3 同构块收敛),description 由调用方参数化"""
    from apps.assetmanagement.models import RecycleAsset

    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_employee,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": description,
    }
    return RecycleAsset.objects.create(**recycle_data)  # type: ignore[no-any-return]


def _force_finalize_recycle(unregistered: UnregisteredAsset, asset: Asset, operator_jobcode: Any) -> tuple[Asset, str]:
    """行级锁强制回收并更新目标仓库(S2/S3 共用),返回 (asset, 原状态)

    [M-16] force_recycle_from_any 为 M-60 声明例外的 FSM 旁路,前态留痕在
    helper 内补 state_change 审计(audit.py log_state_change,同事务内)。
    注:沿 S1/S2/S3 既有形态,operator_jobcode 形参实际承载 Employee 实例
    (下游 _create_recycle_record 以 FK 消费),此处取 employee_jobcode 传给
    log_state_change(其签名收 str)。
    """
    # [M-16] audit 不得直连导入：audit:33→services/__init__→asset_service:14→audit
    # 构成入口次序敏感环（audit 直连即 ImportError）。先经 operation_log_service
    # 链完整加载 audit（audit_adapter 同款模式），再取 AuditLogger。
    from apps.assetmanagement.audit import AuditLogger
    from apps.assetmanagement.models import Asset
    from apps.assetmanagement.services.operation_log_service import OperationLogService  # noqa: F401
    from apps.assetmanagement.state_machine import AssetFSM, AssetState

    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    old_status = asset.asset_current_status
    AssetFSM.force_recycle_from_any(asset)
    asset.asset_storage_recordcode = unregistered.unregistered_asset_storage
    asset.save(update_fields=["asset_current_status", "asset_storage_recordcode"])
    jobcode = getattr(operator_jobcode, "employee_jobcode", operator_jobcode)
    AuditLogger.log_state_change(
        asset=asset,
        from_state=old_status,
        to_state=AssetState.RECYCLED_PENDING.value,
        trigger="force_recycle",
        operator_jobcode=jobcode,
    )
    return asset, old_status


def _handle_s1_create_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S1 场景:创建资产 → unregistered_create_and_recycle → 创建回收记录

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人(实收 Employee 实例)

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.state_machine import AssetFSM

    asset = _create_unregistered_asset(unregistered)
    outasset = _create_receive_outasset(unregistered, asset, f"不在账资产出库,来源: {unregistered.unregistered_code}")

    AssetFSM.unregistered_create_and_recycle(asset)
    asset.save(update_fields=["asset_current_status"])

    recycle = _create_recycle_record(
        asset, outasset, operator_jobcode, f"不在账资产回收,来源: {unregistered.unregistered_code}"
    )
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle

    return {
        "action": "create_and_recycle",
        "asset_code": asset.asset_code,
        "recycle_id": recycle.id,
        "recordcode": recycle.recordcode,
    }


def _handle_s1_create_and_damaged(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S1 场景:创建资产 → unregistered_create_and_damaged → 创建待报废记录

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人(实收 Employee 实例)

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import DamagedAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset = _create_unregistered_asset(unregistered)

    AssetFSM.unregistered_create_and_damaged(asset)
    asset.save(update_fields=["asset_current_status"])

    damaged_data = {
        "asset_recordcode": asset,
        "damaged_asset_number": 1,
        "damaged_date": timezone.now().date(),
        "approval_status": "pending",
        "damaged_asset_description": f"不在账资产待报废,来源: {unregistered.unregistered_code}",
    }
    asset_recordcode = DamagedAsset.objects.create(**damaged_data)

    unregistered.result_asset = asset
    unregistered.result_damaged_asset = asset_recordcode

    return {
        "action": "create_and_damaged",
        "asset_code": asset.asset_code,
        "damaged_id": asset_recordcode.id,
    }


def _handle_s2_supplement_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S2 场景:补建出库记录 → 强制回收 → 创建回收记录

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人(实收 Employee 实例)

    Returns:
        Dict[str, Any]: 处理结果
    """
    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S2场景必须有关联资产")

    outasset = _create_receive_outasset(unregistered, asset, f"补建出库记录,来源: {unregistered.unregistered_code}")
    asset, _ = _force_finalize_recycle(unregistered, asset, operator_jobcode)

    recycle = _create_recycle_record(
        asset, outasset, operator_jobcode, f"不在账资产回收(补建出库),来源: {unregistered.unregistered_code}"
    )
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle

    return {
        "action": "supplement_and_recycle",
        "asset_code": asset.asset_code,
        "asset_recordcode": outasset.recordcode,
        "recycle_id": recycle.id,
        "recordcode": recycle.recordcode,
    }


def _handle_s3_correct_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S3 场景:补建出库记录 → 强制回收(带原状态) → 创建回收记录

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人(实收 Employee 实例)

    Returns:
        Dict[str, Any]: 处理结果
    """
    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S3场景必须有关联资产")

    outasset = _create_receive_outasset(
        unregistered, asset, f"不在账资产出库(状态修正),来源: {unregistered.unregistered_code}"
    )
    asset, old_status = _force_finalize_recycle(unregistered, asset, operator_jobcode)

    recycle = _create_recycle_record(
        asset,
        outasset,
        operator_jobcode,
        f"不在账资产回收(状态修正 {old_status}→recycled_pending),来源: {unregistered.unregistered_code}",
    )
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle

    return {
        "action": "correct_and_recycle",
        "asset_code": asset.asset_code,
        "old_status": old_status,
        "recycle_id": recycle.id,
        "recordcode": recycle.recordcode,
    }
