"""
回收资产查询选择器

提供回收资产记录的查询方法。
"""

from typing import Any

from django.db.models import QuerySet

from apps.assetmanagement.models import RecycleAsset
from core.department_scope import get_asset_linked_queryset_for_user


class RecycleAssetSelector:
    """回收资产查询选择器"""

    @staticmethod
    def get_queryset_for_user(user: Any) -> QuerySet[RecycleAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, RecycleAsset.objects.for_list().filter(is_deleted=False))

    @staticmethod
    def get_asset_recordcodes_for_list() -> QuerySet[RecycleAsset]:
        return RecycleAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcodes_with_asset_details() -> QuerySet[RecycleAsset]:
        return RecycleAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_all_asset_recordcodes() -> QuerySet[RecycleAsset]:
        return RecycleAsset.objects.filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcode_by_record_code(record_code: str) -> RecycleAsset | None:
        try:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            return RecycleAsset.objects.with_asset_details().get(recordcode=record_code, is_deleted=False)
        except RecycleAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_outasset(recordcode: str) -> bool:
        return RecycleAsset.objects.filter(outasset_recordcode__recordcode=recordcode, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user: Any = None) -> QuerySet[RecycleAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        qs: QuerySet[RecycleAsset] = RecycleAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).with_asset_details()
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs

    @staticmethod
    def get_by_outasset_recordcode(outasset_recordcode: str, user: Any = None) -> RecycleAsset | None:
        """按出库记录编码查询回收记录"""
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        qs: QuerySet[RecycleAsset] = RecycleAsset.objects.filter(
            outasset_recordcode__recordcode=outasset_recordcode, is_deleted=False
        ).with_asset_details()
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs.first()
