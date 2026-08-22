"""
找回记录查询选择器

提供找回资产记录的查询方法。
"""

from django.db.models import QuerySet

from apps.assetmanagement.models import FoundAsset
from core.department_scope import get_asset_linked_queryset_for_user


class FoundAssetSelector:
    """找回记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[FoundAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, FoundAsset.objects.for_list().filter(is_deleted=False))

    @staticmethod
    def get_found_assets_for_list() -> QuerySet[FoundAsset]:
        return FoundAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_found_assets_with_details() -> QuerySet[FoundAsset]:
        return FoundAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_found_asset_by_recordcode(recordcode: str) -> FoundAsset | None:
        try:
            return FoundAsset.objects.with_asset_details().get(recordcode=recordcode, is_deleted=False)
        except FoundAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_lost_asset_recordcode(lost_asset_recordcode: str) -> bool:
        return FoundAsset.objects.filter(
            lost_asset_recordcode__recordcode=lost_asset_recordcode, is_deleted=False
        ).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user=None) -> QuerySet[FoundAsset]:
        qs = FoundAsset.objects.filter(
            lost_asset_recordcode__asset_recordcode__asset_code=asset_code,
            is_deleted=False,
        ).select_related(
            "lost_asset_recordcode",
            "lost_asset_recordcode__asset_recordcode",
            "lost_asset_recordcode__asset_recordcode__asset_type_recordcode",
            "lost_asset_recordcode__asset_recordcode__asset_contract_recordcode",
            "lost_asset_recordcode__asset_recordcode__asset_storage_recordcode",
            "lost_asset_recordcode__asset_recordcode__asset_manager_recordcode",
        )
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs
