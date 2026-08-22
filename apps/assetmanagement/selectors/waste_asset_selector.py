"""
已报废资产查询选择器

提供已报废资产记录的查询方法。
"""

from django.db.models import QuerySet

from apps.assetmanagement.models import WasteAsset
from core.department_scope import get_asset_linked_queryset_for_user


class WasteAssetSelector:
    """已报废资产查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[WasteAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, WasteAsset.objects.filter(is_deleted=False))

    @staticmethod
    def get_all_asset_recordcodes() -> QuerySet[WasteAsset]:
        return WasteAsset.objects.filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcode_by_asset_code(asset_code: str) -> WasteAsset | None:
        try:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            return WasteAsset.objects.with_asset_details().get(
                asset_recordcode__asset_code=asset_code, is_deleted=False
            )
        except WasteAsset.DoesNotExist:
            return None

    @staticmethod
    def get_by_asset_code(asset_code: str, user=None) -> QuerySet[WasteAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        qs = WasteAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).with_asset_details()
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs
