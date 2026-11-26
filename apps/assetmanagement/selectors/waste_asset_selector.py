"""
已报废资产查询选择器

提供已报废资产记录的查询方法。
"""

from datetime import date
from typing import Any

from django.db.models import QuerySet

from apps.assetmanagement.models import WasteAsset
from core.department_scope import get_asset_linked_queryset_for_user
from core.locks import lock_row_or_409


class WasteAssetSelector:
    """已报废资产查询选择器"""

    @staticmethod
    def get_queryset_for_user(user: Any) -> QuerySet[WasteAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, WasteAsset.objects.filter(is_deleted=False))

    @staticmethod
    def apply_date_range_filter(
        queryset: QuerySet[WasteAsset],
        start_date: date | None,
        end_date: date | None,
    ) -> QuerySet[WasteAsset]:
        """[M-LAY-02] 报废日期区间过滤唯一实现（空值短路，谓词不变）。"""
        if start_date is not None:
            queryset = queryset.filter(waste_asset_date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(waste_asset_date__lte=end_date)
        return queryset

    @staticmethod
    def get_all_asset_recordcodes() -> QuerySet[WasteAsset]:
        return WasteAsset.objects.filter(is_deleted=False)

    @staticmethod
    def get_for_update_by_asset_code(asset_code: str) -> WasteAsset:
        """按资产编码取已报废记录行锁(M-CONC-01)。

        过滤 asset_recordcode__asset_code 会 JOIN am_asset;of=("self",) 确保
        只锁 am_waste_asset 主表,不扩大阻塞到资产行(对齐 damaged_asset_selector)。
        锁查询自带 is_deleted=False,锁内取到行即锁内复检;锁超时映射 409。
        """
        return lock_row_or_409(
            WasteAsset.objects.filter(
                asset_recordcode__asset_code=asset_code,
                is_deleted=False,
            ).select_for_update(of=("self",))
        )

    @staticmethod
    def get_by_asset_code(asset_code: str, user: Any = None) -> QuerySet[WasteAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        qs = WasteAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).with_asset_details()
        if user:
            qs = get_asset_linked_queryset_for_user(user, qs)  # type: ignore[assignment]
        return qs
