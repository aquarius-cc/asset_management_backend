"""
待报废资产查询选择器

提供待报废资产记录的查询方法。
"""

from django.db.models import QuerySet

from apps.assetmanagement.models import DamagedAsset
from core.department_scope import get_asset_linked_queryset_for_user


class DamagedAssetSelector:
    """待报废资产查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[DamagedAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, DamagedAsset.objects.filter(is_deleted=False))

    @staticmethod
    def get_all_asset_recordcodes() -> QuerySet[DamagedAsset]:
        return DamagedAsset.objects.filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcode_by_asset_code(asset_code: str) -> DamagedAsset | None:
        try:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            return DamagedAsset.objects.with_asset_details().get(
                asset_recordcode__asset_code=asset_code, is_deleted=False
            )
        except DamagedAsset.DoesNotExist:
            return None

    @staticmethod
    def get_asset_recordcode_for_update(asset_recordcode: str) -> DamagedAsset:
        """
        获取待报废记录并加行锁(用于事务更新)

        【性能优化】合并存在性检查和行锁获取为单次查询。

        Args:
            asset_recordcode: 关联资产的 recordcode

        Returns:
            DamagedAsset: 待报废记录实例(已加行锁)

        Raises:
            DamagedAsset.DoesNotExist: 记录不存在或已被删除
        """
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return (
            DamagedAsset.objects.with_asset_details()
            .select_for_update()
            .get(asset_recordcode__recordcode=asset_recordcode, is_deleted=False)
        )

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return DamagedAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str, user=None) -> QuerySet[DamagedAsset]:
        qs = DamagedAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "approver",
        )
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)
        return qs
