"""
资产类型管理服务

提供资产类型管理的业务逻辑。

树形关联设计(方案 D):
- 使用 parent FK 存储父子关系
- 使用 path 字段存储物化路径,加速子孙查询
"""

import copy
from typing import Any

from django.db import transaction

from apps.assetmanagement.models import MAX_ASSET_TYPE_LEVEL, Asset, AssetType
from apps.assetmanagement.selectors import AssetTypeSelector
from core.audit_service import GenericAuditService
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError


class AssetTypeService:
    """
    资产类型管理服务

    提供资产类型管理的业务逻辑。
    """

    @staticmethod
    def _generate_path(parent_path: str, type_code: str) -> str:
        """生成资产类型的物化路径"""
        return f"{parent_path}/{type_code}"

    @staticmethod
    @transaction.atomic
    def create_asset_type(asset_type_data: dict[str, Any]) -> AssetType:
        """
        创建单个资产类型

        Args:
            asset_type_data: 资产类型数据,支持 parent_type_code(业务编码)或 parent(recordcode)

        Returns:
            AssetType: 创建成功的资产类型实例

        Raises:
            AppValidationError: 资产类型编码已存在或层级超限
        """
        type_code = asset_type_data.get("type_code")

        if AssetTypeSelector.exists_by_code(type_code):
            raise AppValidationError(detail=f"资产类型编码 {type_code} 已存在", error_code="DUPLICATE_ASSET_TYPE_CODE")

        # 解析父类型:支持 parent_type_code(业务编码)或 parent(recordcode)
        parent = None
        parent_type_code = asset_type_data.pop("parent_type_code", None)
        parent_rc = asset_type_data.pop("parent", None)

        if parent_type_code:
            parent = AssetTypeSelector.get_asset_type_by_code(parent_type_code)
            if not parent:
                raise AppValidationError(
                    detail=f"父级类型 {parent_type_code} 不存在", error_code="PARENT_ASSET_TYPE_NOT_FOUND"
                )
        elif parent_rc:
            parent = AssetType.objects.filter(recordcode=parent_rc).first()
            if not parent:
                raise AppValidationError(detail="父级类型不存在", error_code="PARENT_ASSET_TYPE_NOT_FOUND")

        # 计算层级和路径
        if parent:
            asset_type_data["parent"] = parent
            asset_type_data["level"] = parent.level + 1
            asset_type_data["path"] = AssetTypeService._generate_path(parent.path, asset_type_data["type_code"])
        else:
            asset_type_data["parent"] = None
            asset_type_data["level"] = 0
            asset_type_data["path"] = f"/{asset_type_data['type_code']}"

        if asset_type_data["level"] > MAX_ASSET_TYPE_LEVEL:
            raise AppValidationError(
                detail=f"资产类型层级不能超过 {MAX_ASSET_TYPE_LEVEL} 层", error_code="ASSET_TYPE_LEVEL_EXCEEDED"
            )

        # 清理已废弃字段
        asset_type_data.pop("parent_code", None)

        asset_type = AssetType.objects.create(**asset_type_data)

        GenericAuditService.log_create(
            record_code=asset_type.recordcode,
            app_label="asset_type",
            description=f"创建资产类型: {asset_type.type_name}",
            after_data={
                "type_code": asset_type.type_code,
                "type_name": asset_type.type_name,
                "level": asset_type.level,
            },
        )

        return asset_type

    @staticmethod
    @transaction.atomic
    def delete_asset_type(type_code: str) -> None:
        """
        删除资产类型(软删除)

        Args:
            type_code: 资产类型编码

        Raises:
            AppValidationError: 资产类型不存在或存在关联资产时抛出
        """
        asset_type = AssetTypeSelector.get_asset_type_by_code(type_code)
        if not asset_type or asset_type.is_deleted:
            raise AppValidationError(detail=f"资产类型 {type_code} 不存在或已删除", error_code="ASSET_TYPE_NOT_FOUND")

        if Asset.objects.filter(asset_type_recordcode=asset_type, is_deleted=False).exists():
            raise AppValidationError(detail="资产类型下存在关联资产,不允许删除", error_code="HAS_RELATED_ASSETS")

        GenericAuditService.log_delete(
            record_code=asset_type.recordcode,
            app_label="asset_type",
            description=f"删除资产类型: {asset_type.type_name}",
            before_data={
                "type_code": asset_type.type_code,
                "type_name": asset_type.type_name,
            },
        )

        asset_type.delete()

    @staticmethod
    def batch_create_asset_type(
        asset_type_data_list: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        批量创建资产类型(逐条独立执行,返回详细结果)

        复用 AssetTypeService.create_asset_type() 单条创建逻辑。
        """
        MAX_BATCH_SIZE = 100
        if len(asset_type_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_items: list[AssetType] = []
        fail_items: list[dict[str, Any]] = []

        for idx, asset_type_data in enumerate(asset_type_data_list):
            try:
                result = AssetTypeService.create_asset_type(
                    copy.deepcopy(asset_type_data),
                )
                success_items.append(result)
            except AppValidationError as e:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": asset_type_data.get("row_number"),
                        "input_data": asset_type_data,
                        "error_code": e.error_code or "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                    }
                )
            except Exception:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": asset_type_data.get("row_number"),
                        "input_data": asset_type_data,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误,请稍后重试",
                    }
                )

        return {
            "total": len(asset_type_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items,
        }

    @staticmethod
    def batch_delete_asset_type(asset_type_codes: list[str]) -> dict[str, Any]:
        """
        批量删除资产类型(软删除,逐条独立执行)
        """

        def _delete_item(asset_type_code: str) -> None:
            AssetTypeService.delete_asset_type(asset_type_code)

        return BatchOperationMixin.batch_delete_execute(
            ids=asset_type_codes,
            process_fn=_delete_item,
            max_batch_size=100,
        )
