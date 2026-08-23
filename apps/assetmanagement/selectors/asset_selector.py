"""
资产查询选择器

提供资产数据的查询方法。
"""

from typing import Any, cast

from django.db.models import Count, Q, QuerySet, Sum

from apps.assetmanagement.models import Asset, AssetOperationLog, AssetType
from core.department_scope import build_asset_owned_department_q, get_department_codes_for_user


class AssetSelector:
    """资产管理查询选择器"""

    @staticmethod
    def apply_user_scope(queryset: QuerySet[Asset], user: Any) -> QuerySet[Asset]:
        """
        RBAC 行级部门范围过滤(全项目唯一实现入口)。

        - dept_codes is None(无限制) → 原样返回
        - dept_codes 为空(部门级角色无部门,最严兜底) → 空集
        - 非空 → 按资产三路径部门归属过滤
        """
        dept_codes = get_department_codes_for_user(user)
        if dept_codes is None:
            return queryset
        if not dept_codes:
            return queryset.none()
        return queryset.filter(build_asset_owned_department_q(dept_codes))

    @staticmethod
    def get_queryset_for_user(user) -> QuerySet[Asset]:
        """
        根据用户角色返回行级过滤后的 QuerySet(RBAC 行级数据隔离)。

        - system_admin / auditor / is_superuser: 无限制
        - dept_manager: 本部门 + 下级部门的资产
        - asset_admin / regular_user: 本部门资产
        """
        return AssetSelector.apply_user_scope(Asset.objects.for_list(), user)

    @staticmethod
    def get_all_assets() -> QuerySet[Asset]:
        return Asset.objects.filter(is_deleted=False)

    @staticmethod
    def get_assets_for_list() -> QuerySet[Asset]:
        return Asset.objects.for_list().all()

    @staticmethod
    def get_assets_with_all_relations() -> QuerySet[Asset]:
        return Asset.objects.with_all_relations().with_harddisk_sns().all()

    @staticmethod
    def get_available_assets(
        asset_code: str | None = None,
        asset_name: str | None = None,
        asset_specification: str | None = None,
        asset_brand: str | None = None,
        asset_contract_code: str | None = None,
        asset_contract_name: str | None = None,
    ) -> QuerySet[Asset]:
        """
        获取可用资产列表(支持多条件搜索)

        Args:
            asset_code: 资产编码(模糊匹配)
            asset_name: 资产名称(模糊匹配)
            asset_specification: 资产规格(模糊匹配)
            asset_brand: 资产品牌(模糊匹配)
            asset_contract_code: 合同编码(精确匹配)
            asset_contract_name: 合同名称(模糊匹配)

        Returns:
            QuerySet[Asset]: 可用资产列表
        """
        queryset = Asset.objects.filter(
            Q(asset_current_status="in_store") | Q(asset_current_status="recycled_pending"),
            is_deleted=False,
            is_active=True,
        ).select_related("asset_type_recordcode", "asset_storage_recordcode", "asset_contract_recordcode")

        if asset_code:
            queryset = queryset.filter(asset_code__icontains=asset_code)
        if asset_name:
            queryset = queryset.filter(asset_name__icontains=asset_name)
        if asset_specification:
            queryset = queryset.filter(asset_specification__icontains=asset_specification)
        if asset_brand:
            queryset = queryset.filter(asset_brand__icontains=asset_brand)
        if asset_contract_code:
            # 【修复】改为模糊匹配,支持部分合同编码模糊搜索则添加'__icontains',删掉就是精确匹配
            queryset = queryset.filter(asset_contract_recordcode__contract_code__icontains=asset_contract_code)
        if asset_contract_name:
            queryset = queryset.filter(asset_contract_recordcode__contract_name__icontains=asset_contract_name)

        return queryset

    @staticmethod
    def get_assets_by_status(status: str) -> QuerySet[Asset]:
        return Asset.objects.filter(asset_current_status=status, is_deleted=False)

    @staticmethod
    def get_asset_by_code(asset_code: str) -> Asset | None:
        try:
            return Asset.objects.select_related(
                "asset_type_recordcode", "asset_storage_recordcode", "asset_contract_recordcode"
            ).get(asset_code=asset_code, is_deleted=False)
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def get_asset_by_recordcode(recordcode: str) -> Asset | None:
        """按 recordcode 查询单条资产(未软删除)"""
        try:
            return cast(Asset, Asset.objects.get(recordcode=recordcode, is_deleted=False))
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def get_asset_for_public_scan(recordcode: str) -> Asset | None:
        """公开扫码查询:按 recordcode 获取资产,预加载类型/仓库/保管人。

        与 get_asset_by_recordcode 的区别:本方法带 select_related,
        用于 public_scan_view 等需要关联数据的只读场景。
        """
        try:
            return Asset.objects.select_related(
                "asset_type_recordcode",
                "asset_storage_recordcode",
                "asset_manager_recordcode",
            ).get(recordcode=recordcode, is_deleted=False)
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def get_asset_detail_by_code(asset_code: str) -> Asset | None:
        try:
            return Asset.objects.select_related(
                "asset_type_recordcode",
                "asset_storage_recordcode",
                "asset_contract_recordcode",
                "asset_entry_person_recordcode",
                "asset_manager_recordcode",
            ).get(asset_code=asset_code)
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def search_assets(
        keyword: str | None = None,
        status: str | None = None,
        asset_type: str | None = None,
        storage_code: str | None = None,
        contract_code: str | None = None,
    ) -> QuerySet[Asset]:
        queryset = Asset.objects.filter(is_deleted=False).select_related(
            "asset_type_recordcode", "asset_storage_recordcode", "asset_contract_recordcode"
        )
        if keyword:
            queryset = queryset.filter(
                Q(asset_code__icontains=keyword)
                | Q(asset_name__icontains=keyword)
                | Q(asset_brand__icontains=keyword)
                | Q(asset_specification__icontains=keyword)
            )
        if status:
            queryset = queryset.filter(asset_current_status=status)
        if asset_type:
            queryset = queryset.filter(asset_type_recordcode__type_code=asset_type)
        if storage_code:
            queryset = queryset.filter(asset_storage_recordcode__storage_code=storage_code)
        if contract_code:
            queryset = queryset.filter(asset_contract_recordcode__contract_code=contract_code)
        return queryset.order_by("-asset_entry_date")

    @staticmethod
    def get_asset_statistics(user: Any = None) -> dict[str, Any]:
        queryset = Asset.objects.filter(is_deleted=False)
        if user is not None:
            queryset = AssetSelector.apply_user_scope(queryset, user)
        status_counts = (
            queryset.values("asset_current_status").annotate(count=Count("id")).order_by("asset_current_status")
        )
        status_choices = dict(Asset.ASSET_STATUS_CHOICES)
        status_distribution = {}
        for item in status_counts:
            status_code = item["asset_current_status"]
            status_distribution[status_code] = {
                "name": status_choices.get(status_code, status_code),
                "count": item["count"],
            }
        for status_code, status_name in status_choices.items():
            if status_code not in status_distribution:
                status_distribution[status_code] = {"name": status_name, "count": 0}
        total_value = queryset.aggregate(Sum("asset_purchase_price"))["asset_purchase_price__sum"] or 0
        return {
            "total_count": queryset.count(),
            "total_value": total_value,
            "status_distribution": status_distribution,
        }

    @staticmethod
    def get_assets_by_type(asset_type: str) -> QuerySet[Asset]:
        return Asset.objects.filter(asset_type_recordcode__type_code=asset_type, is_deleted=False)

    @staticmethod
    def exists_by_code(asset_code: str) -> bool:
        # 【P0-19 修复】显式过滤 is_deleted=False,防御性编码
        return Asset.objects.filter(asset_code=asset_code, is_deleted=False).exists()

    @staticmethod
    def get_assets_by_storage(storage_code: str) -> QuerySet[Asset]:
        return Asset.objects.filter(asset_storage_recordcode__storage_code=storage_code, is_deleted=False)

    @staticmethod
    def combine_search(field_filters: dict[str, str], exact_filters: dict[str, str]):
        """
        多字段 AND 模糊搜索

        支持前端传入:
        - asset_type_code: 类型代码或 recordcode,自动转换
        - asset_type_category: 类型分类,通过 AssetType 关联查询

        :param field_filters: 模糊字段名和值的映射
        :param exact_filters: 精确字段名和值的映射
        :return: QuerySet
        """
        queryset = Asset.objects.filter(is_deleted=False)

        # 1. 如果没有传入任何过滤条件,返回空集(避免全表扫描)
        if not field_filters and not exact_filters:
            return queryset.none()

        # 【修复】字段名映射:前端字段名 → 模型字段名
        FIELD_NAME_MAPPING = {
            "asset_contract": "asset_contract_recordcode__contract_code",
            "asset_contract_name": "asset_contract_recordcode__contract_name",
            "asset_type": "asset_type_recordcode__type_code",
            "asset_storage": "asset_storage_recordcode__storage_code",
        }

        # 2. 构造 AND 组合的 Q 对象(模糊字段)
        if field_filters:
            q_objects = []
            for field, value in field_filters.items():
                if not value:
                    continue
                # 使用映射后的字段名
                mapped_field = FIELD_NAME_MAPPING.get(field, field)
                q_objects.append(Q(**{f"{mapped_field}__icontains": value}))
            if q_objects:
                combined_q = q_objects[0]
                for q in q_objects[1:]:
                    combined_q &= q
                queryset = queryset.filter(combined_q)

        # 3. 处理精确过滤条件
        if exact_filters:
            # 【修复】asset_type 字段:前端传类型代码,需转换为 recordcode
            # 注意:模型字段已重命名为 asset_type_recordcode
            if exact_filters.get("asset_type"):
                type_code = exact_filters.pop("asset_type")
                # 先尝试作为 recordcode 匹配
                asset_type = AssetTypeSelector.get_asset_type_by_recordcode(type_code)
                if not asset_type:
                    # 不是 recordcode,尝试按 asset_type_code 匹配
                    asset_type = AssetTypeSelector.get_asset_type_by_code(type_code)

                if asset_type:
                    # 【修复】使用正确的字段名 asset_type_recordcode
                    exact_filters["asset_type_recordcode"] = asset_type.recordcode
                else:
                    # 找不到对应类型,返回空集
                    return queryset.none()

            # asset_type_category 字段:通过 AssetType 关联查询
            if exact_filters.get("asset_type_category"):
                category = exact_filters.pop("asset_type_category")
                # 查找该分类下所有 AssetType 的 recordcode
                type_recordcodes = AssetType.objects.filter(type_code=category, is_deleted=False).values_list(
                    "recordcode", flat=True
                )
                if type_recordcodes:
                    exact_filters["asset_type_recordcode__in"] = list(type_recordcodes)
                else:
                    return queryset.none()

            # 叠加精确过滤条件(AND 关系)
            queryset = queryset.filter(**{k: v for k, v in exact_filters.items() if v is not None})

        # 4. 预加载关联数据
        queryset = queryset.select_related(
            "asset_type_recordcode", "asset_contract_recordcode", "asset_storage_recordcode"
        )

        return queryset

    @staticmethod
    def get_operation_logs_for_asset(asset: Asset, limit: int = 50) -> QuerySet[AssetOperationLog]:
        """获取资产的操作日志"""
        return (
            AssetOperationLog.objects.filter(asset_code=asset.asset_code)
            .order_by("-operation_time")[:limit]
        )


class AssetTypeSelector:
    """
    资产类型查询选择器

    树形关联设计(方案 D):
    - 使用 parent FK 查询父子关系
    - 使用 path 字段加速子孙查询和面包屑导航
    """

    @staticmethod
    def get_all_asset_types() -> QuerySet[AssetType]:
        return AssetType.objects.filter(is_deleted=False)

    @staticmethod
    def get_asset_type_by_code(type_code: str) -> AssetType | None:
        """按类型代码查询"""
        try:
            return AssetType.objects.get(type_code=type_code, is_deleted=False)
        except AssetType.DoesNotExist:
            return None

    @staticmethod
    def get_asset_type_by_recordcode(recordcode: str) -> AssetType | None:
        """按 recordcode 查询"""
        try:
            return AssetType.objects.get(recordcode=recordcode, is_deleted=False)
        except AssetType.DoesNotExist:
            return None

    @staticmethod
    def exists_by_code(type_code: str) -> bool:
        # 显式过滤 is_deleted=False,防御性编码
        return AssetType.objects.filter(type_code=type_code, is_deleted=False).exists()

    @staticmethod
    def get_root_types() -> QuerySet[AssetType]:
        """获取所有顶级资产类型(parent FK 为 null)"""
        return AssetType.objects.filter(parent__isnull=True).order_by("sort_order", "type_code")

    @staticmethod
    def get_children(type_code: str) -> QuerySet[AssetType]:
        """获取指定资产类型的直接子类型"""
        parent = AssetTypeSelector.get_asset_type_by_code(type_code)
        if not parent:
            return AssetType.objects.none()
        return AssetType.objects.filter(parent=parent).order_by("sort_order", "type_code")

    @staticmethod
    def get_all_descendants(type_code: str) -> list[str]:
        """获取指定资产类型的所有后代 type_code(基于 path 查询)"""
        at = AssetTypeSelector.get_asset_type_by_code(type_code)
        if not at or not at.path:
            return []
        return list(AssetType.objects.filter(path__startswith=f"{at.path}/").values_list("type_code", flat=True))

    @staticmethod
    def get_type_path(type_code: str) -> list[AssetType]:
        """获取从顶级到当前类型的路径(用于面包屑导航)"""
        at = AssetTypeSelector.get_asset_type_by_code(type_code)
        if not at or not at.path:
            return []
        codes = [c for c in at.path.split("/") if c]
        departments = {d.type_code: d for d in AssetType.objects.filter(type_code__in=codes, is_deleted=False)}
        return [departments[c] for c in codes if c in departments]
