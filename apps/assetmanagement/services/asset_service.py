"""
资产管理服务

提供资产管理的核心业务逻辑,包括资产的创建、更新、删除、状态变更等操作。
"""

import string
import uuid
from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors import (
    AssetSelector,
    StorageSelector,
)
from apps.assetmanagement.state_machine import AssetFSM
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError

from .asset_lifecycle_mixin import AssetLifecycleMixin


# 字段白名单,防止通过 setattr 修改任意字段
ASSET_UPDATE_ALLOWED_FIELDS = frozenset(
    [
        "asset_name",
        "asset_type_recordcode",
        "asset_storage_recordcode",
        "asset_brand",
        "asset_specification",
        "asset_purchase_date",
        "asset_purchase_price",
        "asset_warranty_period",
        "asset_description",
        "asset_current_status",
        "asset_manager_recordcode",
        "is_active",
    ]
)


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
    def _get_type_path(cls, asset_type) -> str:
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
    def generate(cls, asset_type, purchase_number: int = 1) -> list[str]:
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
    def generate_with_unique_check(cls, asset_type, purchase_number: int = 1) -> list[str]:
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
        codes = AssetCodeGenerator.generate_with_unique_check(
            asset_type=asset_type,
            purchase_number=purchase_number,
        )
        created_assets = []
        for code in codes:
            single_data = {**asset_data, "asset_code": code}
            # 自动生成 qr_code 内容(JSON 格式,供前端扫码使用)
            if not single_data.get("qr_code"):
                import json

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
    ) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        before_data = {}
        for key in update_data.keys():
            if key in ASSET_UPDATE_ALLOWED_FIELDS:
                field_value = getattr(asset, key)
                if hasattr(field_value, "pk"):
                    before_data[key] = str(field_value)
                else:
                    before_data[key] = field_value
        for key, value in update_data.items():
            if key in ASSET_UPDATE_ALLOWED_FIELDS:
                setattr(asset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}", error_code="FIELD_NOT_ALLOWED")
        asset.save()
        AuditLogger.log_asset_update(
            asset=asset,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return asset

    @staticmethod
    @transaction.atomic
    def delete_asset(asset_code: str, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        if asset.asset_current_status != "in_store":
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status},不允许删除", error_code="ASSET_IN_USE"
            )
        from apps.assetmanagement.models import DamagedAsset, OutAsset

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
    def batch_create_asset(
        asset_data_list: list[dict[str, Any]], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        def _create_item(idx: int, asset_data: dict[str, Any]) -> Asset:
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
        asset_codes: list[str], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> dict[str, Any]:
        MAX_BATCH_SIZE = 100
        if len(asset_codes) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )
        success_ids: list[str] = []
        fail_items: list[dict[str, Any]] = []
        for asset_code in asset_codes:
            try:
                with transaction.atomic():
                    asset = Asset.objects.select_for_update().filter(asset_code=asset_code, is_deleted=False).first()
                    if not asset:
                        fail_items.append(
                            {"id": asset_code, "error_code": "NOT_FOUND", "error_message": f"资产 {asset_code} 不存在"}
                        )
                        continue
                    if asset.asset_current_status != "in_store":
                        fail_items.append(
                            {
                                "id": asset_code,
                                "error_code": "ASSET_IN_USE",
                                "error_message": f"资产当前状态为 {asset.asset_current_status},不允许删除",
                            }
                        )
                        continue
                    from apps.assetmanagement.models import DamagedAsset, OutAsset

                    if OutAsset.objects.filter(asset_recordcode=asset, is_deleted=False).exists():
                        fail_items.append(
                            {
                                "id": asset_code,
                                "error_code": "HAS_OUTASSET_RECORDS",
                                "error_message": "资产存在关联出库记录,不允许删除",
                            }
                        )
                        continue
                    if DamagedAsset.objects.filter(asset_recordcode=asset, is_deleted=False).exists():
                        fail_items.append(
                            {
                                "id": asset_code,
                                "error_code": "HAS_DAMAGED_RECORDS",
                                "error_message": "资产存在待报废记录,不允许删除",
                            }
                        )
                        continue
                    AuditLogger.log_asset_delete(
                        asset_code=asset.asset_code,
                        asset_name=asset.asset_name,
                        asset=asset,
                        operator_jobcode=operator_jobcode,
                        operator_name=operator_name,
                    )
                    asset.delete()
                    success_ids.append(asset_code)
            except Exception:
                fail_items.append(
                    {"id": asset_code, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误,请稍后重试"}
                )
        return {
            "total": len(asset_codes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items,
        }

    @staticmethod
    @transaction.atomic
    def change_asset_status(
        asset_code: str,
        new_status: str,
        description: str = "",
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Asset:
        valid_statuses = dict(Asset.ASSET_STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise AppValidationError(detail=f"无效的资产状态: {new_status}", error_code="INVALID_ASSET_STATUS")
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status
        from apps.assetmanagement.state_machine import AssetState

        target_state = AssetState.from_string(new_status)
        AssetFSM._transition(asset, target_state)
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
    def change_outasset_employee(asset_code: str, applicant_jobcode: str, manager_jobcode: str) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_applicant = asset.asset_applicant_recordcode
        old_manager = asset.asset_manager_recordcode
        asset.asset_applicant_recordcode = applicant_jobcode
        asset.asset_manager_recordcode = manager_jobcode
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={"asset_applicant": str(old_applicant), "asset_manager": str(old_manager)},
            after_data={"asset_applicant": applicant_jobcode, "asset_manager": manager_jobcode},
            operator_jobcode=None,
            operator_name=None,
        )
        asset.save()
        return asset

    @staticmethod
    @transaction.atomic
    def transfer_asset_to_storage(asset_code: str, storage_code: str) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在", error_code="ASSET_NOT_FOUND")
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        storage = StorageSelector.get_storage_by_code(storage_code)
        if not storage:
            raise AppValidationError(detail=f"仓库 {storage_code} 不存在", error_code="STORAGE_NOT_FOUND")
        old_storage = asset.asset_storage_recordcode
        asset.asset_storage_recordcode = storage
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={"asset_storage": old_storage.storage_name if old_storage else None},
            after_data={"asset_storage": storage.storage_name},
            operator_jobcode=None,
            operator_name=None,
        )
        asset.save()
        return asset

    @staticmethod
    def get_asset_statistics(user: Any = None) -> dict[str, Any]:
        return AssetSelector.get_asset_statistics(user=user)

    @staticmethod
    def generate_qr_code_image(asset, base_url: str) -> bytes:
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
