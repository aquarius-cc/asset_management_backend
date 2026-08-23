"""
损坏记录查询选择器

提供损坏资产记录的查询方法。
"""

from typing import Any

from django.db.models import QuerySet

from apps.assetmanagement.models import BrokenAsset
from core.department_scope import get_asset_linked_queryset_for_user


class BrokenAssetSelector:
    """损坏记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user: Any) -> QuerySet[BrokenAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, BrokenAsset.objects.for_list().filter(is_deleted=False))  # type: ignore[attr-defined,no-any-return]

    @staticmethod
    def get_broken_assets_for_list() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.for_list().filter(is_deleted=False)  # type: ignore[attr-defined,no-any-return]

    @staticmethod
    def get_broken_assets_with_details() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.with_asset_details().filter(is_deleted=False)  # type: ignore[attr-defined,no-any-return]

    @staticmethod
    def get_broken_asset_by_recordcode(recordcode: str) -> BrokenAsset | None:
        try:
            return BrokenAsset.objects.with_asset_details().get(recordcode=recordcode, is_deleted=False)  # type: ignore[attr-defined,no-any-return]
        except BrokenAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return BrokenAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user: Any = None) -> QuerySet[BrokenAsset]:
        qs = BrokenAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
        )
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs
