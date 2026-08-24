"""
维修记录查询选择器

提供维修资产记录的查询方法。
"""

from typing import Any

from django.db.models import QuerySet

from apps.assetmanagement.models import RepairAsset
from core.department_scope import get_asset_linked_queryset_for_user


class RepairAssetSelector:
    """维修记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user: Any) -> QuerySet[RepairAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, RepairAsset.objects.filter(is_deleted=False))

    @staticmethod
    def get_repair_assets_for_list() -> QuerySet[RepairAsset]:
        # 【性能优化】复用模型 QuerySet 的 for_list() 方法
        return RepairAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_repair_asset_by_recordcode(recordcode: str) -> RepairAsset | None:
        try:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            return RepairAsset.objects.with_asset_details().get(recordcode=recordcode, is_deleted=False)
        except RepairAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return RepairAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user: Any = None) -> QuerySet[RepairAsset]:
        qs = RepairAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
        )
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)  # type: ignore[assignment]
        return qs
