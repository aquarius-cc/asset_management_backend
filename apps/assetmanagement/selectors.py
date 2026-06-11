"""
资产管理查询层

该模块提供资产管理的数据查询接口，封装复杂的数据库查询逻辑，
为业务层提供简洁的数据访问方法。所有查询方法均支持软删除过滤，
并通过select_related/prefetch_related优化查询性能。

包含以下选择器类：
- AssetSelector: 资产查询选择器
- OutAssetSelector: 出库记录查询选择器
- StorageSelector: 仓库查询选择器
- ContractSelector: 合同查询选择器
- AssetTypeSelector: 资产类型查询选择器
- RecycleAssetSelector: 回收资产查询选择器
- DamagedAssetSelector: 待报废资产查询选择器
- WasteAssetSelector: 已报废资产查询选择器
- HardDiskSNSelector: 硬盘序列号查询选择器
"""

from typing import Optional, Dict, Any, List
from datetime import date
from dateutil.relativedelta import relativedelta

from django.db.models import QuerySet, Count, Sum, Q
from django.db import models

from apps.assetmanagement.models import (
    Asset,
    AssetType,
    Contract,
    Storage,
    OutAsset,
    RecycleAsset,
    DamagedAsset,
    WasteAsset,
    HardDiskSN,
)


class AssetSelector:
    """
    资产管理查询选择器

    提供资产数据的查询方法，支持多种查询条件组合，
    包括按状态筛选、关键词搜索、资产类型筛选等。
    所有方法均自动过滤已删除的记录。
    """

    @staticmethod
    def get_all_assets() -> QuerySet[Asset]:
        """
        获取所有资产（排除已删除）

        Returns:
            QuerySet[Asset]: 所有未删除资产的查询集
        """
        return Asset.objects.filter(is_deleted=False)

    @staticmethod
    def get_available_assets() -> QuerySet[Asset]:
        """
        获取可用资产（在库资产）

        返回状态为在库、未删除且激活的资产列表。

        Returns:
            QuerySet[Asset]: 可用资产查询集，预加载关联的类型和仓库信息
        """
        return Asset.objects.filter(
            Q(asset_current_status='in_store') | Q(asset_current_status='recycled_pending'),
            is_deleted=False,
            is_active=True
        ).select_related(
            'asset_type_code',
            'asset_storage_code'
        )

    @staticmethod
    def get_assets_by_status(status: str) -> QuerySet[Asset]:
        """
        按状态获取资产

        根据指定的资产状态筛选资产列表。

        Args:
            status: 资产状态（in_store/in_use/in_scrapped）

        Returns:
            QuerySet[Asset]: 符合状态条件的资产查询集
        """
        return Asset.objects.filter(
            asset_current_status=status,
            is_deleted=False
        )

    @staticmethod
    def get_asset_by_code(asset_code: str) -> Optional[Asset]:
        """
        通过编码获取资产

        根据资产编码精确查询单个资产对象。

        Args:
            asset_code: 资产编码

        Returns:
            Optional[Asset]: 资产实例或 None（未找到时）
        """
        try:
            return Asset.objects.select_related(
                'asset_type_code',
                'asset_storage_code',
                'asset_contract_code'
            ).get(
                asset_code=asset_code,
                is_deleted=False
            )
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def get_asset_detail_by_code(asset_code: str) -> Optional[Asset]:
        """
        通过编码获取资产详情（含完整关联预加载）

        【AGENTS 规范 - P2-12】供 CombinedAssetSerializer.get_asset_details_data 使用，
        预加载类型、仓库、合同、入库人、管理人等关联字段，避免 N+1 查询。
        与 get_asset_by_code 的区别：额外 select_related asset_entry_person_jobcode
        和 asset_manager_jobcode，且不过滤 is_deleted（与原始行为保持一致）。

        Args:
            asset_code: 资产编码

        Returns:
            Optional[Asset]: 资产实例或 None（未找到时）
        """
        try:
            return Asset.objects.select_related(
                'asset_type_code',
                'asset_storage_code',
                'asset_contract_code',
                'asset_entry_person_jobcode',
                'asset_manager_jobcode'
            ).get(asset_code=asset_code)
        except Asset.DoesNotExist:
            return None

    @staticmethod
    def search_assets(
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        asset_type_code: Optional[str] = None,
        storage_code: Optional[str] = None,
        contract_code: Optional[str] = None,
    ) -> QuerySet[Asset]:
        """
        搜索资产

        支持按关键词、状态、资产类型、仓库、合同等条件组合查询资产。

        Args:
            keyword: 搜索关键词（匹配资产编码、名称、品牌、规格）
            status: 资产状态筛选（in_store/in_use/in_scrapped）
            asset_type_code: 资产类型编码筛选
            storage_code: 仓库编码筛选
            contract_code: 合同编码筛选

        Returns:
            QuerySet[Asset]: 符合条件的资产查询集，预加载关联信息
        """
        queryset = Asset.objects.filter(is_deleted=False).select_related(
            'asset_type_code',
            'asset_storage_code',
            'asset_contract_code'
        )

        if keyword:
            queryset = queryset.filter(
                Q(asset_code__icontains=keyword) |
                Q(asset_name__icontains=keyword) |
                Q(asset_brand__icontains=keyword) |
                Q(asset_specification__icontains=keyword)
            )

        if status:
            queryset = queryset.filter(asset_current_status=status)

        if asset_type_code:
            queryset = queryset.filter(asset_type_code__asset_type_code=asset_type_code)

        if storage_code:
            queryset = queryset.filter(asset_storage_code__storage_code=storage_code)

        if contract_code:
            queryset = queryset.filter(asset_contract_code__contract_code=contract_code)

        return queryset.order_by('-asset_entry_date')

    @staticmethod
    def get_asset_statistics() -> Dict[str, Any]:
        """
        获取资产统计

        统计资产总数及各状态分布情况。

        Returns:
            Dict[str, Any]: 统计信息字典，包含总数和状态分布
        """
        queryset = Asset.objects.filter(is_deleted=False)

        # 【修复 H2】使用 annotate + values 替代循环 count()，将 N+1 查询优化为 1 次查询
        status_counts = queryset.values('asset_current_status').annotate(
            count=Count('id')
        ).order_by('asset_current_status')

        status_choices = dict(Asset.ASSET_STATUS_CHOICES)
        status_distribution = {}
        for item in status_counts:
            status_code = item['asset_current_status']
            status_distribution[status_code] = {
                'name': status_choices.get(status_code, status_code),
                'count': item['count']
            }

        # 补充未出现的状态（数量为 0）
        for status_code, status_name in status_choices.items():
            if status_code not in status_distribution:
                status_distribution[status_code] = {
                    'name': status_name,
                    'count': 0
                }

        total_value = queryset.aggregate(Sum('asset_purchase_price'))[
            'asset_purchase_price__sum'
        ] or 0

        return {
            'total_count': queryset.count(),
            'total_value': total_value,
            'status_distribution': status_distribution,
        }

    @staticmethod
    def get_assets_by_type(asset_type_code: str) -> QuerySet[Asset]:
        """
        按类型获取资产

        根据资产类型编码查询资产列表。

        Args:
            asset_type_code: 资产类型编码

        Returns:
            QuerySet[Asset]: 该类型的资产查询集
        """
        return Asset.objects.filter(
            asset_type_code__asset_type_code=asset_type_code,
            is_deleted=False
        )

    @staticmethod
    def exists_by_code(asset_code: str) -> bool:
        """
        【AGENTS 规范 - P2-03】检查资产编码是否已存在

        【业务场景】创建资产前校验编码唯一性，避免直接在 Service 层调用 ORM。

        Args:
            asset_code: 资产编码

        Returns:
            bool: 资产编码是否已存在
        """
        return Asset.objects.filter(asset_code=asset_code).exists()

    @staticmethod
    def get_assets_by_storage(storage_code: str) -> QuerySet[Asset]:
        """
        按仓库获取资产

        根据仓库编码查询资产列表。

        Args:
            storage_code: 仓库编码

        Returns:
            QuerySet[Asset]: 该仓库中的资产查询集
        """
        return Asset.objects.filter(
            asset_storage_code__storage_code=storage_code,
            is_deleted=False
        )


class OutAssetSelector:
    """
    出库记录查询选择器

    提供出库记录数据的查询方法，支持按记录编码、申请人、资产等条件查询。
    """
    @staticmethod
    def _apply_filters(queryset: QuerySet[OutAsset], filters: Dict[str, Any]) -> QuerySet[OutAsset]:
        """
        通用过滤方法：根据给定的过滤条件筛选出库记录查询集

        Args:
            queryset: 初始查询集
            filters: 过滤条件字典，支持以下键：
                - keyword: 搜索关键词（匹配资产编码/名称、员工工号/姓名）
                - search_type: 搜索类型（'asset', 'user', 'all' 或 None）
                - asset_code: 资产编码精确匹配
                - employee_jobcode: 员工工号精确匹配（适用于申请人或保管人）
                - department_code: 部门编码（关联员工部门）
                - years: 出库年份（整数）
                - ordering: 排序字段（如 '-outasset_date'）

        Returns:
            过滤后的查询集
        """
        keyword = filters.get('keyword')
        search_type = filters.get('search_type', 'all')
        asset_code = filters.get('asset_code')
        employee_jobcode = filters.get('employee_jobcode')
        department_code = filters.get('department_code')
        years = filters.get('years')
        ordering = filters.get('ordering')

        # 1. 关键词搜索
        if keyword:
            keyword = keyword.strip()
            asset_cond = Q(outasset_code__asset_code__icontains=keyword) | \
                         Q(outasset_code__asset_name__icontains=keyword)
            user_cond = Q(outasset_code__asset_applicant_jobcode__employee_jobcode__icontains=keyword) | \
                        Q(outasset_code__asset_applicant_jobcode__employee_name__icontains=keyword) | \
                        Q(outasset_code__asset_manager_jobcode__employee_jobcode__icontains=keyword) | \
                        Q(outasset_code__asset_manager_jobcode__employee_name__icontains=keyword)

            if search_type == 'asset':
                queryset = queryset.filter(asset_cond)
            elif search_type == 'user':
                queryset = queryset.filter(user_cond)
            else:  # all
                queryset = queryset.filter(asset_cond | user_cond)

        # 2. 精确匹配资产编码
        if asset_code:
            queryset = queryset.filter(outasset_code__asset_code=asset_code)

        # 3. 精确匹配员工工号（申请人或保管人）
        if employee_jobcode:
            queryset = queryset.filter(
                Q(outasset_code__asset_applicant_jobcode__employee_jobcode=employee_jobcode) |
                Q(outasset_code__asset_manager_jobcode__employee_jobcode=employee_jobcode)
            )

        # 4. 按部门过滤（通过保管人或申请人的部门）
        if department_code:
            queryset = queryset.filter(
                Q(outasset_code__asset_manager_jobcode__employee_department__department_code=department_code) |
                Q(outasset_code__asset_applicant_jobcode__employee_department__department_code=department_code)
            )

        # 5. 按出库时长过滤（出库日期距离今天 >= years 年）
        years = filters.get('years')
        if years:
            try:
                years_int = int(years)
                if years_int > 0:
                    threshold_date = date.today() - relativedelta(years=years_int)
                    queryset = queryset.filter(outasset_date__lte=threshold_date)
            except (ValueError, TypeError):
                pass

        # 6. 排序
        if ordering:
            queryset = queryset.order_by(ordering)
        elif not queryset.query.order_by:  # 如果没有显式排序，使用默认倒排出库日期
            queryset = queryset.order_by('-outasset_date')

        return queryset

    @staticmethod
    def get_recyclable_outassets(filters: Optional[Dict[str, Any]] = None) -> QuerySet[OutAsset]:
        """
        获取所有可回收的出库记录（状态为 in_use）

        Args:
            filters: 可选过滤条件字典，支持 _apply_filters 中的所有键
                    例如 {'keyword': '笔记本', 'years': 2026, 'department_code': 'RD01'}

        Returns:
            预加载关联信息的 QuerySet，状态为 in_use 且应用了额外过滤条件
        """
        base_queryset = OutAsset.objects.filter(
            outasset_code__asset_current_status='in_use'
        ).exclude(
    outasset_recordcode__in=RecycleAsset.objects.values('outasset_recordcode')
).select_related(
            'outasset_code',
            'outasset_code__asset_manager_jobcode',
            'outasset_code__asset_manager_jobcode__employee_department',
            'outasset_code__asset_applicant_jobcode',
            'outasset_code__asset_applicant_jobcode__employee_department',
            'outasset_code__asset_contract_code'
        ).order_by('-outasset_date')   # ✅ 添加排序

        if filters:
            base_queryset = OutAssetSelector._apply_filters(base_queryset, filters)

        return base_queryset

    @staticmethod
    def get_all_out_assets() -> QuerySet[OutAsset]:
        """
        获取所有出库记录

        Returns:
            QuerySet[OutAsset]: 所有出库记录查询集，预加载关联信息
        """
        return OutAsset.objects.select_related(
            'outasset_code',
            'outasset_code__asset_applicant_jobcode',
            'outasset_code__asset_manager_jobcode',
            'outasset_code__asset_contract_code'
        ).all()

    @staticmethod
    def get_outasset_by_record_code(record_code: str) -> Optional[OutAsset]:
        """
        通过记录编码获取出库记录

        根据出库记录编码精确查询单个出库记录对象。

        Args:
            record_code: 出库记录编码

        Returns:
            Optional[OutAsset]: 出库记录实例或 None（未找到时）
        """
        try:
            return OutAsset.objects.select_related(
                'outasset_code',
                'outasset_code__asset_applicant_jobcode',
                'outasset_code__asset_manager_jobcode'
            ).get(outasset_recordcode=record_code)
        except OutAsset.DoesNotExist:
            return None

    @staticmethod
    def get_outassets_by_applicant(applicant_jobcode: str) -> QuerySet[OutAsset]:
        """
        获取申请人的所有出库记录

        根据申请人工号查询其提交的所有出库记录。

        Args:
            applicant_jobcode: 申请人工号

        Returns:
            QuerySet[OutAsset]: 该申请人的出库记录查询集
        """
        return OutAsset.objects.filter(
            outasset_code__asset_applicant_jobcode__employee_jobcode=applicant_jobcode
        ).select_related(
            'outasset_code',
            'outasset_code__asset_manager_jobcode'
        ).order_by('-outasset_date')

    @staticmethod
    def get_outassets_by_asset(asset_code: str) -> QuerySet[OutAsset]:
        """
        获取指定资产的出库记录

        根据资产编码查询该资产的所有出库记录。

        Args:
            asset_code: 资产编码

        Returns:
            QuerySet[OutAsset]: 该资产的出库记录查询集
        """
        return OutAsset.objects.filter(
            outasset_code__asset_code=asset_code
        ).select_related(
            'outasset_code',
            'outasset_code__asset_applicant_jobcode',
            'outasset_code__asset_manager_jobcode'
        ).order_by('-outasset_date')

    @staticmethod
    def get_outassets_by_status(status: str) -> QuerySet[OutAsset]:
        """
        按状态获取出库记录

        根据出库记录状态筛选记录列表。

        Args:
            status: 出库状态（in_use/recycled/damaged/scrapped）

        Returns:
            QuerySet[OutAsset]: 符合状态条件的出库记录查询集
        """
        return OutAsset.objects.filter(
            outasset_code__asset_current_status=status
        ).select_related(
            'outasset_code',
            'outasset_code__asset_applicant_jobcode'
        ).order_by('-outasset_date')

    @staticmethod
    def get_active_outasset_by_asset(asset_code: str, statuses: Optional[List[str]] = None) -> Optional[OutAsset]:
        """
        【AGENTS 规范 - P2-07】获取指定资产在指定状态下的出库记录（取第一条）

        【业务场景】取消待报废申请时，查找该资产关联的活跃出库记录，以便恢复出库状态。
        默认查找 in_use 和 damaged 状态的出库记录。

        Args:
            asset_code: 资产编码
            statuses: 出库状态列表，默认为 ['damaged', 'in_use']

        Returns:
            Optional[OutAsset]: 出库记录实例或 None
        """
        if statuses is None:
            statuses = ['damaged', 'in_use']
        return OutAsset.objects.filter(
            outasset_code__asset_code=asset_code,
            outasset_code__asset_current_status__in=statuses
        ).first()

    @staticmethod
    def get_outasset_by_asset_and_status(asset: Asset, statuses: List[str]) -> Optional[OutAsset]:
        """
        【AGENTS 规范 - P2-08】获取指定资产实例在指定状态下的出库记录（取第一条）

        【业务场景】AssetStateManager 中状态变更时，查找关联的出库记录以同步更新状态。
        注意：此方法返回的 QuerySet 未加 select_for_update()，
        调用方（StateManager）如需行锁请自行在后续操作中处理。

        Args:
            asset: 资产实例（非编码），用于直接关联查询
            statuses: 出库状态列表，如 ['in_use'] 或 ['damaged']

        Returns:
            Optional[OutAsset]: 出库记录实例或 None
        """
        return OutAsset.objects.filter(
            outasset_code=asset,
            outasset_code__asset_current_status__in=statuses
        ).first()

    @staticmethod
    def get_outasset_statistics() -> Dict[str, Any]:
        """
        获取出库统计信息

        统计出库总数及各类型出库数量。

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        queryset = OutAsset.objects.all()
        type_choices = dict(OutAsset.OUTASSET_TYPE_CHOICES)

        type_stats = {}
        for type_code, type_name in type_choices.items():
            count = queryset.filter(outasset_type=type_code).count()
            type_stats[type_code] = {
                'name': type_name,
                'count': count
            }

        return {
            'total_out_assets': queryset.count(),
            'by_type': type_stats,
            'by_status': {
                'in_use': queryset.filter(outasset_code__asset_current_status='in_use').count(),
                'recycled': queryset.filter(outasset_code__asset_current_status='recycled').count()
            }
        }


class StorageSelector:
    """
    仓库查询选择器

    提供仓库数据的查询方法。
    """

    @staticmethod
    def get_all_storages() -> QuerySet[Storage]:
        """
        获取所有仓库

        Returns:
            QuerySet[Storage]: 所有仓库查询集
        """
        return Storage.objects.filter(is_deleted=False)

    @staticmethod
    def get_storage_by_code(storage_code: str) -> Optional[Storage]:
        """
        通过编码获取仓库

        Args:
            storage_code: 仓库编码

        Returns:
            Optional[Storage]: 仓库实例或 None
        """
        try:
            return Storage.objects.get(storage_code=storage_code, is_deleted=False)
        except Storage.DoesNotExist:
            return None

    @staticmethod
    def get_storages_by_type(storage_type: str) -> QuerySet[Storage]:
        """
        按类型获取仓库

        Args:
            storage_type: 仓库类型（newasset/recycle/damaged）

        Returns:
            QuerySet[Storage]: 该类型的仓库查询集
        """
        return Storage.objects.filter(
            storage_type=storage_type,
            is_deleted=False
        )

    @staticmethod
    def exists_by_code(storage_code: str) -> bool:
        """
        【AGENTS 规范 - P2-04】检查仓库编码是否已存在

        【业务场景】创建仓库前校验编码唯一性，避免直接在 Service 层调用 ORM。

        Args:
            storage_code: 仓库编码

        Returns:
            bool: 仓库编码是否已存在
        """
        return Storage.objects.filter(storage_code=storage_code).exists()

    @staticmethod
    def exists_by_name(storage_name: str) -> bool:
        """
        【AGENTS 规范 - P2-04】检查仓库名称是否已存在

        【业务场景】创建仓库前校验名称唯一性，避免直接在 Service 层调用 ORM。

        Args:
            storage_name: 仓库名称

        Returns:
            bool: 仓库名称是否已存在
        """
        return Storage.objects.filter(storage_name=storage_name).exists()

    @staticmethod
    def search_storages(keyword: str) -> QuerySet[Storage]:
        """
        搜索仓库

        按仓库编码、名称或地址模糊搜索。

        Args:
            keyword: 搜索关键词

        Returns:
            QuerySet[Storage]: 匹配的仓库查询集
        """
        return Storage.objects.filter(
            Q(storage_code__icontains=keyword) |
            Q(storage_name__icontains=keyword) |
            Q(storage_address__icontains=keyword),
            is_deleted=False
        )


class ContractSelector:
    """
    合同查询选择器

    提供合同数据的查询方法。
    """

    @staticmethod
    def get_all_contracts() -> QuerySet[Contract]:
        """
        获取所有合同

        Returns:
            QuerySet[Contract]: 所有合同查询集
        """
        return Contract.objects.filter(is_deleted=False)

    @staticmethod
    def get_contract_by_code(contract_code: str) -> Optional[Contract]:
        """
        通过编码获取合同

        Args:
            contract_code: 合同编码

        Returns:
            Optional[Contract]: 合同实例或 None
        """
        try:
            return Contract.objects.get(contract_code=contract_code, is_deleted=False)
        except Contract.DoesNotExist:
            return None

    @staticmethod
    def search_contracts(keyword: str) -> QuerySet[Contract]:
        """
        搜索合同

        按合同编码、名称、供应商模糊搜索。

        Args:
            keyword: 搜索关键词

        Returns:
            QuerySet[Contract]: 匹配的合同查询集
        """
        return Contract.objects.filter(
            Q(contract_code__icontains=keyword) |
            Q(contract_name__icontains=keyword) |
            Q(contract_supplier__icontains=keyword),
            is_deleted=False
        ).order_by('-contract_signing_date')

    @staticmethod
    def get_contracts_by_type(contract_type: str) -> QuerySet[Contract]:
        """
        按类型获取合同

        Args:
            contract_type: 合同类型

        Returns:
            QuerySet[Contract]: 该类型的合同查询集
        """
        return Contract.objects.filter(
            contract_type=contract_type,
            is_deleted=False
        ).order_by('-contract_signing_date')

    @staticmethod
    def get_contract_statistics() -> Dict[str, Any]:
        """
        获取合同统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        queryset = Contract.objects.filter(is_deleted=False)

        total_contracts = queryset.count()
        total_amount = queryset.aggregate(Sum('contract_price'))['contract_price__sum'] or 0
        avg_amount = total_amount / total_contracts if total_contracts > 0 else 0

        type_stats = {}
        for type_code, type_name in Contract.CONTRACT_TYPE_CHOICES:
            count = queryset.filter(contract_type=type_code).count()
            type_stats[type_code] = {'name': type_name, 'count': count}

        status_stats = {}
        for status_code, status_name in Contract.CONTRACT_SETTLEMENT_CHOICES:
            count = queryset.filter(contract_settlment_status=status_code).count()
            status_stats[status_code] = {'name': status_name, 'count': count}

        return {
            'total_contracts': total_contracts,
            'total_amount': total_amount,
            'avg_amount': round(avg_amount, 2),
            'by_type': type_stats,
            'by_status': status_stats
        }


class AssetTypeSelector:
    """
    资产类型查询选择器

    提供资产类型数据的查询方法。
    """

    @staticmethod
    def get_all_asset_types() -> QuerySet[AssetType]:
        """
        获取所有资产类型

        Returns:
            QuerySet[AssetType]: 所有资产类型查询集
        """
        return AssetType.objects.filter(is_deleted=False)

    @staticmethod
    def get_asset_type_by_code(asset_type_code: str) -> Optional[AssetType]:
        """
        通过编码获取资产类型

        Args:
            asset_type_code: 资产类型编码

        Returns:
            Optional[AssetType]: 资产类型实例或 None
        """
        try:
            return AssetType.objects.get(
                asset_type_code=asset_type_code,
                is_deleted=False
            )
        except AssetType.DoesNotExist:
            return None

    @staticmethod
    def exists_by_code(asset_type_code: str) -> bool:
        """
        【AGENTS 规范 - P2-05】检查资产类型编码是否已存在

        【业务场景】创建资产类型前校验编码唯一性，避免直接在 Service 层调用 ORM。

        Args:
            asset_type_code: 资产类型编码

        Returns:
            bool: 资产类型编码是否已存在
        """
        return AssetType.objects.filter(asset_type_code=asset_type_code).exists()

    @staticmethod
    def get_asset_types_by_category(category: str) -> QuerySet[AssetType]:
        """
        按分类获取资产类型

        Args:
            category: 资产分类（hardware/software/other）

        Returns:
            QuerySet[AssetType]: 该分类的资产类型查询集
        """
        return AssetType.objects.filter(
            asset_type_category=category,
            is_deleted=False
        )


class RecycleAssetSelector:
    """
    回收资产查询选择器

    提供回收资产数据的查询方法。
    """

    @staticmethod
    def get_all_recycle_assets() -> QuerySet[RecycleAsset]:
        """
        获取所有回收资产记录

        Returns:
            QuerySet[RecycleAsset]: 所有回收记录查询集，预加载关联信息
        """
        return RecycleAsset.objects.select_related(
            'outasset_recordcode',
            'recycle_asset_code',
            'recycle_asset_code__asset_storage_code',
            'outasset_recordcode__outasset_code__asset_applicant_jobcode',
            'operator_jobcode'
        ).all()

    @staticmethod
    def get_recycle_asset_by_outasset_code(outasset_recordcode: str) -> Optional[RecycleAsset]:
        """
        通过出库记录编码获取回收记录

        Args:
            outasset_recordcode: 出库记录编码

        Returns:
            Optional[RecycleAsset]: 回收记录实例或 None
        """
        try:
            return RecycleAsset.objects.select_related(
                'outasset_recordcode',
                'recycle_asset_code'
            ).get(outasset_recordcode__outasset_recordcode=outasset_recordcode)
        except RecycleAsset.DoesNotExist:
            return None

    @staticmethod
    def get_recycle_assets_by_asset(asset_code: str) -> QuerySet[RecycleAsset]:
        """
        获取指定资产的回收记录

        Args:
            asset_code: 资产编码

        Returns:
            QuerySet[RecycleAsset]: 该资产的回收记录查询集
        """
        return RecycleAsset.objects.filter(
            recycle_asset_code__asset_code=asset_code
        ).select_related(
            'outasset_recordcode',
            'recycle_asset_code'
        ).order_by('-recycle_asset_date')

    @staticmethod
    def get_recycle_asset_by_record_code(recycle_record_code: str) -> Optional[RecycleAsset]:
        """
        【AGENTS 规范 - 业务唯一编码】通过回收记录编码获取回收记录

        Args:
            recycle_record_code: 回收记录编码（格式: RECYCLE-YYYYMMDD-XXXXXXXX）

        Returns:
            Optional[RecycleAsset]: 回收记录实例或 None
        """
        try:
            return RecycleAsset.objects.select_related(
                'outasset_recordcode',
                'recycle_asset_code',
                'recycle_asset_code__asset_storage_code',
                'outasset_recordcode__outasset_code__asset_applicant_jobcode',
                'operator_jobcode'
            ).get(recycle_record_code=recycle_record_code)
        except RecycleAsset.DoesNotExist:
            return None


class DamagedAssetSelector:
    """
    待报废资产查询选择器

    提供待报废资产数据的查询方法。
    """

    @staticmethod
    def get_all_damaged_assets() -> QuerySet[DamagedAsset]:
        """
        获取所有待报废资产记录

        Returns:
            QuerySet[DamagedAsset]: 所有待报废记录查询集，预加载关联信息
        """
        return DamagedAsset.objects.select_related(
            'damaged_asset_code',
            'damaged_asset_code__asset_storage_code',
            'damaged_asset_code__asset_contract_code',
            'approver'
        ).all()

    @staticmethod
    def get_damaged_asset_by_asset_code(asset_code: str) -> Optional[DamagedAsset]:
        """
        通过资产编码获取待报废记录

        Args:
            asset_code: 资产编码

        Returns:
            Optional[DamagedAsset]: 待报废记录实例或 None
        """
        try:
            return DamagedAsset.objects.select_related(
                'damaged_asset_code',
                'damaged_asset_code__asset_storage_code'
            ).get(damaged_asset_code__asset_code=asset_code)
        except DamagedAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset: Asset) -> bool:
        """
        【AGENTS 规范 - P2-06】检查资产是否已存在待报废记录

        【业务场景】创建待报废记录前校验唯一性，避免直接在 Service 层调用 ORM。

        Args:
            asset: 资产实例（非编码），用于直接关联查询

        Returns:
            bool: 是否已存在待报废记录
        """
        return DamagedAsset.objects.filter(damaged_asset_code=asset).exists()

    @staticmethod
    def get_damaged_assets_by_status(approval_status: str) -> QuerySet[DamagedAsset]:
        """
        按审批状态获取待报废记录

        Args:
            approval_status: 审批状态（pending/approved/rejected）

        Returns:
            QuerySet[DamagedAsset]: 符合状态的待报废记录查询集
        """
        return DamagedAsset.objects.filter(approval_status=approval_status).select_related(
            'damaged_asset_code',
            'approver'
        ).order_by('-damaged_date')

    @staticmethod
    def get_damaged_assets_by_asset(asset_code: str) -> QuerySet[DamagedAsset]:
        """
        【AGENTS 规范 - P1-02】获取指定资产的所有待报废记录

        Args:
            asset_code: 资产编码

        Returns:
            QuerySet[DamagedAsset]: 该资产的待报废记录查询集，预加载关联信息
        """
        return DamagedAsset.objects.filter(
            damaged_asset_code__asset_code=asset_code
        ).select_related(
            'damaged_asset_code',
            'damaged_asset_code__asset_storage_code',
            'damaged_asset_code__asset_contract_code',
            'approver'
        ).order_by('-damaged_date')


class WasteAssetSelector:
    """
    已报废资产查询选择器

    提供已报废资产数据的查询方法。
    【查询规范】所有查询方法均支持通过 waste_asset_code（即 Asset.asset_code）进行查找。
    """

    @staticmethod
    def get_all_waste_assets() -> QuerySet[WasteAsset]:
        """
        获取所有已报废资产记录

        Returns:
            QuerySet[WasteAsset]: 所有已报废记录查询集，预加载关联信息
        """
        return WasteAsset.objects.select_related(
            'waste_asset_code',
            'waste_asset_code__asset_contract_code',
            'source_damaged_asset'  # 【新增】预加载来源待报废记录
        ).all()

    @staticmethod
    def get_waste_asset_by_asset_code(asset_code: str) -> Optional[WasteAsset]:
        """
        通过资产编码获取报废记录

        【查询规范】使用 waste_asset_code__asset_code 进行跨表查询。

        Args:
            asset_code: 资产编码（Asset.asset_code）

        Returns:
            Optional[WasteAsset]: 报废记录实例或 None
        """
        try:
            return WasteAsset.objects.select_related(
                'waste_asset_code',
                'waste_asset_code__asset_contract_code',
                'source_damaged_asset'  # 【新增】预加载来源待报废记录
            ).get(waste_asset_code__asset_code=asset_code)
        except WasteAsset.DoesNotExist:
            return None

    @staticmethod
    def exists_by_asset_code(asset_code: str) -> bool:
        """
        检查资产是否已存在已报废记录

        【业务场景】用于防止重复创建已报废记录。

        Args:
            asset_code: 资产编码（Asset.asset_code）

        Returns:
            bool: 是否存在已报废记录
        """
        return WasteAsset.objects.filter(
            waste_asset_code__asset_code=asset_code
        ).exists()

    @staticmethod
    def get_waste_asset_by_damaged_asset(damaged_asset_id: int) -> Optional[WasteAsset]:
        """
        通过待报废记录获取已报废记录

        【业务场景】用于追溯报废来源。

        Args:
            damaged_asset_id: 待报废记录ID

        Returns:
            Optional[WasteAsset]: 报废记录实例或 None
        """
        try:
            return WasteAsset.objects.select_related(
                'waste_asset_code',
                'waste_asset_code__asset_contract_code',
                'source_damaged_asset'
            ).get(source_damaged_asset__id=damaged_asset_id)
        except WasteAsset.DoesNotExist:
            return None

    @staticmethod
    def get_waste_assets_by_date_range(
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> QuerySet[WasteAsset]:
        """
        按日期范围获取已报废记录

        Args:
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            QuerySet[WasteAsset]: 符合条件的已报废记录查询集
        """
        queryset = WasteAsset.objects.select_related(
            'waste_asset_code',
            'waste_asset_code__asset_contract_code'
        )

        if start_date:
            queryset = queryset.filter(waste_asset_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(waste_asset_date__lte=end_date)

        return queryset.order_by('-waste_asset_date')

    @staticmethod
    def get_waste_assets_by_asset(asset_code: str) -> QuerySet[WasteAsset]:
        """
        获取指定资产的已报废记录

        Args:
            asset_code: 资产编码（Asset.asset_code）

        Returns:
            QuerySet[WasteAsset]: 该资产的已报废记录查询集
        """
        return WasteAsset.objects.filter(
            waste_asset_code__asset_code=asset_code
        ).select_related(
            'waste_asset_code',
            'waste_asset_code__asset_contract_code',
            'source_damaged_asset'
        ).order_by('-waste_asset_date')

    @staticmethod
    def get_waste_asset_statistics() -> Dict[str, Any]:
        """
        获取报废统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        from datetime import datetime

        queryset = WasteAsset.objects.all()
        total_waste_assets = queryset.count()

        current_year = datetime.now().year
        this_year_waste = queryset.filter(waste_asset_date__year=current_year).count()

        monthly_waste = []
        for month in range(1, 13):
            count = queryset.filter(
                waste_asset_date__year=current_year,
                waste_asset_date__month=month
            ).count()
            monthly_waste.append({'month': month, 'count': count})

        return {
            'total_waste_assets': total_waste_assets,
            'this_year_waste': this_year_waste,
            'monthly_waste': monthly_waste
        }


class HardDiskSNSelector:
    """
    硬盘序列号查询选择器

    提供硬盘序列号数据的查询方法。
    """

    @staticmethod
    def get_all_harddisk_sns() -> QuerySet[HardDiskSN]:
        """
        获取所有硬盘序列号记录

        Returns:
            QuerySet[HardDiskSN]: 所有硬盘序列号记录查询集，预加载关联信息
        """
        return HardDiskSN.objects.select_related('asset_code').all()

    @staticmethod
    def get_harddisk_sn_by_code(harddisk_sn_code: str) -> Optional[HardDiskSN]:
        """
        通过序列号获取硬盘记录

        Args:
            harddisk_sn_code: 硬盘序列号

        Returns:
            Optional[HardDiskSN]: 硬盘记录实例或 None
        """
        try:
            # print(f"harddisk_sn_code: {harddisk_sn_code}")
            # 【AGENTS 规范】通过 ORM 查询，自动预加载 asset_code 关联
            record = HardDiskSN.objects.select_related('asset_code').get(
                harddisk_sn_code=harddisk_sn_code
            )
            # print(f"查询硬盘序列号成功: {record}")
            return record
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def get_harddisk_sns_by_asset(asset_code: str) -> QuerySet[HardDiskSN]:
        """
        获取指定资产的硬盘序列号记录

        Args:
            asset_code: 资产编码

        Returns:
            QuerySet[HardDiskSN]: 该资产的硬盘序列号记录查询集
        """
        return HardDiskSN.objects.filter(
            asset_code__asset_code=asset_code
        ).select_related('asset_code').order_by('harddisk_no')

    @staticmethod
    def get_harddisk_sns_by_status(status: str) -> QuerySet[HardDiskSN]:
        """
        按状态获取硬盘序列号记录

        Args:
            status: 硬盘状态（active/repair/scrap/lost/damaged）

        Returns:
            QuerySet[HardDiskSN]: 符合状态的硬盘序列号记录查询集
        """
        return HardDiskSN.objects.filter(harddisk_status=status).select_related('asset_code')


class DashboardSelector:
    """
    【AGENTS 规范 - P1-08】仪表盘数据查询选择器

    封装 Dashboard 所需的所有统计查询，将原 ViewSet 中的直接 ORM 调用
    统一收敛到 Selector 层，遵循 View → Selector → ORM 的分层规范。
    """

    @staticmethod
    def get_overview_statistics() -> Dict[str, Any]:
        """
        获取仪表盘概览统计数据

        Returns:
            Dict: 包含资产总数、在用数、库存数、月度出库/回收数、待报废/已报废数等
        """
        from django.utils import timezone
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 【AGENTS 规范】所有统计查询通过 ORM 聚合，自动过滤 is_deleted=False
        total_assets = Asset.objects.filter(is_deleted=False).count()
        active_assets = Asset.objects.filter(is_deleted=False, asset_current_status='in_use').count()
        in_stock_assets = Asset.objects.filter(is_deleted=False, asset_current_status='in_store').count()

        pending_waste = DamagedAsset.objects.count()
        wasted_assets = WasteAsset.objects.count()

        monthly_distributed = OutAsset.objects.filter(outasset_date__gte=month_start).count()
        total_distributed = OutAsset.objects.count()

        monthly_recycled = RecycleAsset.objects.filter(recycle_asset_date__gte=month_start).count()
        total_recycled = RecycleAsset.objects.count()

        return {
            'total_assets': total_assets,
            'active_assets': active_assets,
            'in_stock_assets': in_stock_assets,
            'monthly_distributed': monthly_distributed,
            'monthly_recycled': monthly_recycled,
            'pending_waste': pending_waste,
            'wasted_assets': wasted_assets,
            'total_recycled': total_recycled,
            'total_distributed': total_distributed,
            'timestamp': now.isoformat()
        }

    @staticmethod
    def get_recent_out_assets(limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近出库的资产记录

        Args:
            limit: 返回记录数量上限

        Returns:
            List[Dict]: 出库记录列表，含资产名称、编码、领用人、部门等
        """
        records = OutAsset.objects.filter(
            outasset_code__asset_current_status='in_use'
        ).select_related(
            'outasset_code', 'outasset_code__asset_manager_jobcode',
            'outasset_code__asset_manager_jobcode__employee_department'
        ).order_by('-created_at')[:limit]

        # 【AGENTS 规范】在 Selector 中完成数据格式化，View 仅负责返回 Response
        return [
            {
                'id': r.id,
                'asset_name': r.outasset_code.asset_name if r.outasset_code else None,
                'asset_code': r.outasset_code.asset_code if r.outasset_code else None,
                'distribute_time': r.outasset_date.isoformat() if r.outasset_date else None,
                'recipient_name': r.outasset_code__asset_manager_jobcode.employee_name if r.outasset_code__asset_manager_jobcode else None,
                'department_name': (
                    r.outasset_code__asset_manager_jobcode.employee_department.department_name
                    if r.outasset_code__asset_manager_jobcode and r.outasset_code__asset_manager_jobcode.employee_department
                    else None
                )
            }
            for r in records
        ]

    @staticmethod
    def get_recent_recycle_assets(limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近回收的资产记录

        Args:
            limit: 返回记录数量上限

        Returns:
            List[Dict]: 回收记录列表，含资产名称、编码、归还人、部门等
        """
        records = RecycleAsset.objects.select_related(
            'recycle_asset_code', 'outasset_recordcode__outasset_code__asset_applicant_jobcode',
            'outasset_recordcode__outasset_code__asset_applicant_jobcode__employee_department'
        ).order_by('-created_at')[:limit]

        return [
            {
                'id': r.id,
                'asset_name': r.recycle_asset_code.asset_name if r.recycle_asset_code else None,
                'asset_code': r.recycle_asset_code.asset_code if r.recycle_asset_code else None,
                'recycle_time': r.recycle_asset_date.isoformat() if r.recycle_asset_date else None,
                'returner_name': r.outasset_recordcode.outasset_code.asset_applicant_jobcode.employee_name
                if r.outasset_recordcode.outasset_code.asset_applicant_jobcode else None,
                'department_name': (
                    r.outasset_recordcode.outasset_code.asset_applicant_jobcode.employee_department.department_name
                    if r.outasset_recordcode.outasset_code.asset_applicant_jobcode and r.outasset_recordcode.outasset_code.asset_applicant_jobcode.employee_department
                    else None
                )
            }
            for r in records
        ]
