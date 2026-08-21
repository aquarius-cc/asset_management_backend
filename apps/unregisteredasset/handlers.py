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

import secrets
import string
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.unregisteredasset.models import UnregisteredAsset
from core.exceptions import AppValidationError


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


def _handle_s1_create_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S1场景:创建资产并回收入库

    步骤:
    1. 创建 Asset 记录(状态默认为 in_store)
    2. 使用状态机适配器设置状态为 recycled_pending
    3. 创建 RecycleAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    # 1. 创建资产
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
    asset = Asset.objects.create(**asset_data)

    # 2. 创建出库记录(S1场景需要先出库再回收)
    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"不在账资产出库,来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    # 3. 设置状态为已回收待发放
    AssetFSM.unregistered_create_and_recycle(asset)
    asset.save(update_fields=["asset_current_status"])

    # 4. 创建回收记录
    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_jobcode,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": f"不在账资产回收,来源: {unregistered.unregistered_code}",
    }
    asset_recordcode = RecycleAsset.objects.create(**recycle_data)

    # 5. 更新关联
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = asset_recordcode

    return {
        "action": "create_and_recycle",
        "asset_code": asset.asset_code,
        "recycle_id": asset_recordcode.id,
        "recordcode": asset_recordcode.recordcode,
    }


def _handle_s1_create_and_damaged(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S1场景:创建资产并进入待报废

    步骤:
    1. 创建 Asset 记录
    2. 使用状态机适配器设置状态为 damaged
    3. 创建 DamagedAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, DamagedAsset
    from apps.assetmanagement.state_machine import AssetFSM

    # 1. 创建资产
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
    asset = Asset.objects.create(**asset_data)

    # 2. 设置状态为待报废
    AssetFSM.unregistered_create_and_damaged(asset)
    asset.save(update_fields=["asset_current_status"])

    # 3. 创建待报废记录
    damaged_data = {
        "asset_recordcode": asset,
        "damaged_asset_number": 1,
        "damaged_date": timezone.now().date(),
        "approval_status": "pending",
        "damaged_asset_description": f"不在账资产待报废,来源: {unregistered.unregistered_code}",
    }
    asset_recordcode = DamagedAsset.objects.create(**damaged_data)

    # 4. 更新关联
    unregistered.result_asset = asset
    unregistered.result_damaged_asset = asset_recordcode

    return {
        "action": "create_and_damaged",
        "asset_code": asset.asset_code,
        "damaged_id": asset_recordcode.id,
    }


def _handle_s2_supplement_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S2场景:补建出库记录并回收

    步骤:
    1. 补建 OutAsset 记录
    2. 使用状态机适配器强制回收
    3. 创建 RecycleAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S2场景必须有关联资产")

    # 1. 补建出库记录
    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"补建出库记录,来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    # 2. 强制回收(使用 select_for_update 加锁)
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    AssetFSM.force_recycle_from_any(asset)
    asset.asset_storage_recordcode = unregistered.unregistered_asset_storage
    asset.save(update_fields=["asset_current_status", "asset_storage_recordcode"])

    # 3. 创建回收记录
    recycle_data = {
        "outasset_recordcode": outasset,
        "asset_recordcode": asset,
        "recycle_asset_number": 1,
        "operator_employee": operator_jobcode,
        "recycle_asset_date": timezone.now().date(),
        "recycle_asset_description": f"不在账资产回收(补建出库),来源: {unregistered.unregistered_code}",
    }
    asset_recordcode = RecycleAsset.objects.create(**recycle_data)

    # 4. 更新关联
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = asset_recordcode

    return {
        "action": "supplement_and_recycle",
        "asset_code": asset.asset_code,
        "asset_recordcode": outasset.recordcode,
        "recycle_id": asset_recordcode.id,
        "recordcode": asset_recordcode.recordcode,
    }


def _handle_s3_correct_and_recycle(unregistered: UnregisteredAsset, operator_jobcode: str) -> dict[str, Any]:
    """
    S3场景:修正状态并回收

    步骤:
    1. 强制回收(使用状态机适配器)
    2. 创建 RecycleAsset 记录
    3. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
    from apps.assetmanagement.state_machine import AssetFSM

    asset = unregistered.related_asset
    if not asset:
        raise AppValidationError(detail="S3场景必须有关联资产")

    # 1. 创建出库记录(S3场景需要先出库再回收)
    outasset_data = {
        "asset_recordcode": asset,
        "outasset_number": 1,
        "outasset_date": unregistered.discovery_date,
        "outasset_type": "receive",
        "outasset_description": f"不在账资产出库(状态修正),来源: {unregistered.unregistered_code}",
    }
    outasset = OutAsset.objects.create(**outasset_data)

    # 2. 强制回收(使用 select_for_update 加锁)
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    old_status = asset.asset_current_status

    AssetFSM.force_recycle_from_any(asset)
    asset.asset_storage_recordcode = unregistered.unregistered_asset_storage
    asset.save(update_fields=["asset_current_status", "asset_storage_recordcode"])

    # 3. 创建回收记录
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
    asset_recordcode = RecycleAsset.objects.create(**recycle_data)

    # 4. 更新关联
    unregistered.result_asset = asset
    unregistered.result_recycle_asset = asset_recordcode

    return {
        "action": "correct_and_recycle",
        "asset_code": asset.asset_code,
        "old_status": old_status,
        "recycle_id": asset_recordcode.id,
        "recordcode": asset_recordcode.recordcode,
    }
