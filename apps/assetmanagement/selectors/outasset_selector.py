# TECHNICAL_DEBT: >500 lines
"""
出库/回收/报废查询选择器

提供出库、回收、待报废、已报废记录的查询方法。
"""

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import Q, QuerySet

from apps.assetmanagement.models import (
    Asset,
    BrokenAsset,
    DamagedAsset,
    FoundAsset,
    LostAsset,
    OutAsset,
    RecycleAsset,
    RepairAsset,
    WasteAsset,
)
from core.department_scope import get_asset_linked_queryset_for_user


class OutAssetSelector:
    """出库记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[OutAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, OutAsset.objects.for_list().filter(is_deleted=False))

    @staticmethod
    def get_outassets_for_list() -> QuerySet[OutAsset]:
        return OutAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_outassets_with_asset_details() -> QuerySet[OutAsset]:
        return OutAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcodes_for_list() -> QuerySet[OutAsset]:
        return OutAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_asset_recordcodes_with_asset_details() -> QuerySet[OutAsset]:
        return OutAsset.objects.with_asset_details().filter(is_deleted=False)

    # 搜索参数配置：前端参数名 → 数据库查询字段
    # icontains: 模糊匹配, exact: 精确匹配
    RECYCLABLE_FILTER_CONFIG = {
        "asset_code": {"field": "asset_recordcode__asset_code", "lookup": "icontains"},
        "asset_name": {"field": "asset_recordcode__asset_name", "lookup": "icontains"},
        "asset_specification": {"field": "asset_recordcode__asset_specification", "lookup": "icontains"},
        "asset_brand": {"field": "asset_recordcode__asset_brand", "lookup": "icontains"},
        "outasset_applicant_recordcode_name": {
            "field": "asset_recordcode__asset_applicant_recordcode__employee_name",
            "lookup": "icontains",
        },
        "outasset_manager_recordcode_name": {
            "field": "asset_recordcode__asset_manager_recordcode__employee_name",
            "lookup": "icontains",
        },
        "department": {
            "field": "asset_recordcode__asset_manager_recordcode__employee_department__department_name",
            "lookup": "icontains",
        },
        "department_code": {
            "field": "asset_recordcode__asset_manager_recordcode__employee_department__department_code",
            "lookup": "exact",
        },
        "employee_jobcode": {
            "field": "asset_recordcode__asset_applicant_recordcode__employee_jobcode",
            "lookup": "exact",
        },
    }

    @staticmethod
    def _apply_flexible_filters(
        queryset: QuerySet[OutAsset], filters: dict[str, Any], filter_config: dict[str, dict[str, str]]
    ) -> QuerySet[OutAsset]:
        """
        灵活的过滤器：根据配置自动应用过滤条件

        Args:
            queryset: 查询集
            filters: 前端传入的过滤参数
            filter_config: 过滤配置 {参数名: {field: '数据库字段', lookup: '查询类型'}}

        Returns:
            QuerySet: 过滤后的查询集
        """
        for param_name, config in filter_config.items():
            value = filters.get(param_name)
            if value and isinstance(value, str):
                value = value.strip()
                if value:
                    field = config["field"]
                    lookup = config["lookup"]
                    queryset = queryset.filter(**{f"{field}__{lookup}": value})
        return queryset

    @staticmethod
    def _apply_filters(queryset: QuerySet[OutAsset], filters: dict[str, Any]) -> QuerySet[OutAsset]:
        # 应用灵活过滤器
        queryset = OutAssetSelector._apply_flexible_filters(
            queryset, filters, OutAssetSelector.RECYCLABLE_FILTER_CONFIG
        )

        # 关键词搜索（特殊处理）
        keyword = filters.get("keyword")
        search_type = filters.get("search_type", "all")
        if keyword:
            keyword = keyword.strip()
            asset_cond = Q(asset_recordcode__asset_code__icontains=keyword) | Q(
                asset_recordcode__asset_name__icontains=keyword
            )
            user_cond = (
                Q(asset_recordcode__asset_applicant_recordcode__employee_jobcode__icontains=keyword)
                | Q(asset_recordcode__asset_applicant_recordcode__employee_name__icontains=keyword)
                | Q(asset_recordcode__asset_manager_recordcode__employee_jobcode__icontains=keyword)
                | Q(asset_recordcode__asset_manager_recordcode__employee_name__icontains=keyword)
            )
            if search_type == "asset":
                queryset = queryset.filter(asset_cond)
            elif search_type == "user":
                queryset = queryset.filter(user_cond)
            else:
                queryset = queryset.filter(asset_cond | user_cond)

        # 年数过滤（特殊处理）
        years = filters.get("years")
        if years:
            try:
                years_int = int(years)
                if years_int > 0:
                    threshold_date = date.today() - relativedelta(years=years_int)
                    queryset = queryset.filter(outasset_date__lte=threshold_date)
            except (ValueError, TypeError):
                pass

        # 排序
        ordering = filters.get("ordering")
        ALLOWED_ORDERING = {"-outasset_date", "outasset_date", "-outasset_number", "outasset_number"}
        if ordering and ordering in ALLOWED_ORDERING:
            queryset = queryset.order_by(ordering)
        elif not queryset.query.order_by:
            queryset = queryset.order_by("-outasset_date")
        return queryset

    @staticmethod
    def get_recyclable_outassets(filters: dict[str, Any] | None = None) -> QuerySet[OutAsset]:
        # 【P0-25 修复】跨表 JOIN 过滤关联表 is_deleted=False，防止返回已删除资产的出库记录
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法，添加额外 FK
        base_queryset = (
            OutAsset.objects.filter(asset_recordcode__asset_current_status=Asset.AssetStatus.IN_USE, asset_recordcode__is_deleted=False)
            .exclude(recordcode__in=RecycleAsset.objects.values("outasset_recordcode"))
            .with_asset_details()
            .select_related(
                "asset_recordcode__asset_manager_recordcode__employee_department",
                "asset_recordcode__asset_applicant_recordcode__employee_department",
            )
            .order_by("-outasset_date")
        )
        if filters:
            base_queryset = OutAssetSelector._apply_filters(base_queryset, filters)
        return base_queryset

    @staticmethod
    def get_all_out_assets() -> QuerySet[OutAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return OutAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_outasset_by_record_code(record_code: str) -> OutAsset | None:
        try:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            return OutAsset.objects.with_asset_details().get(recordcode=record_code, is_deleted=False)
        except OutAsset.DoesNotExist:
            return None

    @staticmethod
    def get_outassets_by_applicant(applicant_jobcode: str) -> QuerySet[OutAsset]:
        return (
            OutAsset.objects.filter(
                asset_recordcode__asset_applicant_recordcode__employee_jobcode=applicant_jobcode,
                is_deleted=False,
            )
            .with_asset_details()
            .order_by("-outasset_date")
        )

    @staticmethod
    def get_outassets_by_asset(asset_code: str) -> QuerySet[OutAsset]:
        return (
            OutAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False)
            .with_asset_details()
            .order_by("-outasset_date")
        )

    @staticmethod
    def get_outassets_by_status(status: str) -> QuerySet[OutAsset]:
        return OutAsset.objects.filter(
            asset_recordcode__asset_current_status=status, is_deleted=False
        ).select_related("asset_recordcode")

    @staticmethod
    def get_active_outasset_by_asset(asset_code: str, statuses: list[str] | None = None) -> OutAsset | None:
        if statuses is None:
            statuses = [Asset.AssetStatus.IN_USE]
        try:
            return (
                OutAsset.objects.filter(
                    asset_recordcode__asset_code=asset_code,
                    asset_recordcode__asset_current_status__in=statuses,
                    is_deleted=False,
                )
                .select_related("asset_recordcode")
                .first()
            )
        except OutAsset.DoesNotExist:
            return None

    @staticmethod
    def get_outasset_by_asset_and_status(asset: "Asset", statuses: list[str]) -> OutAsset | None:
        try:
            return OutAsset.objects.filter(
                asset_recordcode=asset, asset_recordcode__asset_current_status__in=statuses, is_deleted=False
            ).first()
        except OutAsset.DoesNotExist:
            return None

    @staticmethod
    def get_outasset_statistics() -> dict[str, Any]:
        from django.db.models import Count

        total = OutAsset.objects.filter(is_deleted=False).count()
        type_counts = OutAsset.objects.filter(is_deleted=False).values("outasset_type").annotate(count=Count("id"))
        return {"total_outassets": total, "by_type": {item["outasset_type"]: item["count"] for item in type_counts}}


class RecycleAssetSelector:
    """回收资产查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[RecycleAsset]:
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
    def get_by_asset_code(asset_code: str) -> QuerySet[RecycleAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return RecycleAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).with_asset_details()

    @staticmethod
    def get_by_outasset_recordcode(outasset_recordcode: str) -> RecycleAsset | None:
        """按出库记录编码查询回收记录"""
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return RecycleAsset.objects.filter(
            outasset_recordcode__recordcode=outasset_recordcode, is_deleted=False
        ).with_asset_details().first()


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
        获取待报废记录并加行锁（用于事务更新）

        【性能优化】合并存在性检查和行锁获取为单次查询。

        Args:
            asset_recordcode: 关联资产的 recordcode

        Returns:
            DamagedAsset: 待报废记录实例（已加行锁）

        Raises:
            DamagedAsset.DoesNotExist: 记录不存在或已被删除
        """
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return DamagedAsset.objects.with_asset_details().select_for_update().get(
            asset_recordcode__recordcode=asset_recordcode, 
            is_deleted=False
        )

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return DamagedAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_by_asset_code(asset_code: str) -> QuerySet[DamagedAsset]:
        return DamagedAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "approver",
        )


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
    def get_by_asset_code(asset_code: str) -> QuerySet[WasteAsset]:
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return WasteAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).with_asset_details()


class BrokenAssetSelector:
    """损坏记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[BrokenAsset]:
        """RBAC 行级过滤"""
        return get_asset_linked_queryset_for_user(user, BrokenAsset.objects.for_list().filter(is_deleted=False))

    @staticmethod
    def get_broken_assets_for_list() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.for_list().filter(is_deleted=False)

    @staticmethod
    def get_broken_assets_with_details() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.with_asset_details().filter(is_deleted=False)

    @staticmethod
    def get_broken_asset_by_recordcode(recordcode: str) -> BrokenAsset | None:
        try:
            return BrokenAsset.objects.with_asset_details().get(recordcode=recordcode, is_deleted=False)
        except BrokenAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        return BrokenAsset.objects.filter(asset_recordcode__asset_code=asset_code, is_deleted=False).exists()


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


class RepairAssetSelector:
    """维修记录查询选择器"""

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[RepairAsset]:
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
        return RepairAsset.objects.filter(
            asset_recordcode__asset_code=asset_code, is_deleted=False
        ).exists()
