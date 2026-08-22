"""
遗失记录查询选择器

提供遗失资产记录的查询方法。
"""

from django.db.models import QuerySet

from apps.assetmanagement.models import LostAsset
from core.department_scope import get_asset_linked_queryset_for_user


class LostAssetSelector:
    """遗失记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[LostAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, LostAsset.objects.for_list().filter(is_deleted=False))

    @staticmethod
    def get_lost_assets_for_list() -> QuerySet[LostAsset]:
        return LostAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_lost_assets_with_details() -> QuerySet[LostAsset]:
        return LostAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_lost_asset_by_recordcode(recordcode: str) -> LostAsset | None:
        try:
            return LostAsset.objects.with_asset_details().get(recordcode=recordcode, is_deleted=False)
        except LostAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return LostAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user=None) -> QuerySet[LostAsset]:
        qs = LostAsset.objects.filter(
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
