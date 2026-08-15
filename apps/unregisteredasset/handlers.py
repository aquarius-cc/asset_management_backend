"""
未登记资产审批处理函数,按场景类型(S1/S2/S3)拆分的独立处理逻辑

函数:
  - validate_handle_type: 验证处理方式与场景类型匹配
  - generate_asset_code: 生成唯一资产编码(AST-YYYYMMDD-XXXXXX)
  - handle_s1_create_and_recycle: S1场景 — 创建资产并回收入库
  - handle_s1_create_and_damaged: S1场景 — 创建资产并进入待报废
  - handle_s2_supplement_and_recycle: S2场景 — 补建出库记录并回收
  - handle_s3_correct_and_recycle: S3场景 — 修正状态并回收

调用链:
  本模块被 services.py 的 approve_and_handle 调用
  本模块依赖 assetmanagement(Asset, OutAsset, RecycleAsset, DamagedAsset, AssetFSM)
"""

import logging
import secrets
import string
from decimal import Decimal
from typing import Any

from django.db import IntegrityError
from django.utils import timezone

from apps.unregisteredasset.models import UnregisteredAsset
from core.exceptions import AppValidationError


logger = logging.getLogger(__name__)


def validate_handle_type(scenario_type: str, handle_type: str) -> None:
    """验证处理方式与场景类型匹配"""
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


def generate_asset_code() -> str:
    """生成唯一资产编码(格式:AST-YYYYMMDD-XXXXXX)"""
    prefix = "AST"
    date_str = timezone.now().strftime("%Y%m%d")
    random_suffix = "".join(secrets.choice(string.digits) for _ in range(6))
    return f"{prefix}-{date_str}-{random_suffix}"


def handle_s1_create_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """S1场景:创建资产并回收入库"""
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset_data = {
        "asset_code": generate_asset_code(),
        "asset_name": unregistered.asset_name,
        "asset_brand": unregistered.asset_brand,
        "asset_specification": unregistered.asset_specification,
        "asset_type_recordcode": unregistered.unregistered_asset_type,
        "asset_purchase_price": unregistered.estimated_value or Decimal("0"),
        "asset_purchase_date": unregistered.discovery_date,
        "asset_entry_date": timezone.now().date(),
        "asset_storage_recordcode": unregistered.unregistered_asset_storage,
    }
    try:
        asset = Asset.objects.create(**asset_data)
    except IntegrityError:
        raise AppValidationError(
            detail=f"资产编码 {asset_data.get('asset_code', '')} 生成冲突,请重试",
            error_code="CODE_COLLISION",
        )

    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"不在账资产出库,来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    AssetFSM.unregistered_create_and_recycle(asset)
    asset.save(update_fields=["asset_current_status"])

    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_jobcode,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": f"不在账资产回收,来源: {unregistered.unregistered_code}",
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle_asset

    return {
        "action": "create_and_recycle",
        "asset_code": asset.asset_code,
        "recycle_id": recycle_asset.id,
        "recordcode": recycle_asset.recordcode,
    }


def handle_s1_create_and_damaged(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """S1场景:创建资产并进入待报废"""
    from apps.assetmanagement.models import Asset, DamagedAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset_data = {
        "asset_code": generate_asset_code(),
        "asset_name": unregistered.asset_name,
        "asset_brand": unregistered.asset_brand,
        "asset_specification": unregistered.asset_specification,
        "asset_type_recordcode": unregistered.unregistered_asset_type,
        "asset_purchase_price": unregistered.estimated_value or Decimal("0"),
        "asset_purchase_date": unregistered.discovery_date,
        "asset_entry_date": timezone.now().date(),
        "asset_storage_recordcode": unregistered.unregistered_asset_storage,
    }
    try:
        asset = Asset.objects.create(**asset_data)
    except IntegrityError:
        raise AppValidationError(
            detail=f"资产编码 {asset_data.get('asset_code', '')} 生成冲突,请重试",
            error_code="CODE_COLLISION",
        )

    AssetFSM.unregistered_create_and_damaged(asset)
    asset.save(update_fields=["asset_current_status"])

    damaged_data = {
        "asset_recordcode": asset,
        "damaged_asset_number": 1,
        "damaged_date": timezone.now().date(),
        "approval_status": "pending",
        "damaged_asset_description": f"不在账资产待报废,来源: {unregistered.unregistered_code}",
    }
    damaged_asset = DamagedAsset.objects.create(**damaged_data)

    unregistered.result_asset = asset
    unregistered.result_damaged_asset = damaged_asset

    return {
        "action": "create_and_damaged",
        "asset_code": asset.asset_code,
        "damaged_id": damaged_asset.id,
    }


def handle_s2_supplement_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """S2场景:补建出库记录并回收"""
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S2场景必须有关联资产")

    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"补建出库记录,来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    AssetFSM.force_recycle_from_any(asset)
    asset.asset_storage_recordcode = unregistered.unregistered_asset_storage
    asset.save(update_fields=["asset_current_status", "asset_storage_recordcode"])

    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_jobcode,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": f"不在账资产回收(补建出库),来源: {unregistered.unregistered_code}",
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle_asset

    return {
        "action": "supplement_and_recycle",
        "asset_code": asset.asset_code,
        "asset_recordcode": outasset.recordcode,
        "recycle_id": recycle_asset.id,
        "recordcode": recycle_asset.recordcode,
    }


def handle_s3_correct_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """S3场景:修正状态并回收"""
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S3场景必须有关联资产")

    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"不在账资产出库(状态修正),来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    old_status = asset.asset_current_status

    AssetFSM.force_recycle_from_any(asset)
    asset.asset_storage_recordcode = unregistered.unregistered_asset_storage
    asset.save(update_fields=["asset_current_status", "asset_storage_recordcode"])

    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_jobcode,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": (
            f"不在账资产回收(状态修正 {old_status}→recycled_pending),来源: {unregistered.unregistered_code}"
        ),
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    unregistered.result_asset = asset
    unregistered.result_recycle_asset = recycle_asset

    return {
        "action": "correct_and_recycle",
        "asset_code": asset.asset_code,
        "old_status": old_status,
        "recycle_id": recycle_asset.id,
        "recordcode": recycle_asset.recordcode,
    }
