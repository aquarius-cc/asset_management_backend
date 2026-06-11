"""
自定义 QuerySet 优化模块

【AGENTS 规范 - 性能优化】
封装 select_related 链和 defer() 排除大字段，减少数据库查询和数据传输。
所有生命周期模型（OutAsset/RecycleAsset/DamagedAsset/WasteAsset）通过 Asset FK 关联查询详情。
"""

from django.db import models


class AssetQuerySet(models.QuerySet):
    """
    Asset 查询集优化

    提供预加载关联和字段精简方法，用于列表页和详情页的不同查询需求。
    """

    def with_basic_relations(self):
        """预加载基础关联（类型、合同、仓库）"""
        return self.select_related(
            'asset_type_code', 'asset_contract_code', 'asset_storage_code'
        )

    def with_person_relations(self):
        """预加载人员关联（入库人、申请人、保管人）"""
        return self.select_related(
            'asset_entry_person_jobcode', 'asset_applicant_jobcode', 'asset_manager_jobcode'
        )

    def with_all_relations(self):
        """预加载所有常用关联"""
        return self.with_basic_relations().with_person_relations()

    def with_harddisk_sns(self):
        """预加载硬盘序列号"""
        return self.prefetch_related('harddisk_sns')

    def for_list(self):
        """
        列表页专用：defer() 排除大字段，减少数据传输

        排除 asset_description（TextField，列表页不需要展示）
        保留所有其他字段，避免延迟加载陷阱
        """
        return self.with_basic_relations().with_person_relations().defer(
            'asset_description',
        )

    def for_search_list(self):
        """
        搜索结果列表（更精简的字段）

        只预加载类型和仓库，排除大字段
        """
        return self.select_related(
            'asset_type_code', 'asset_storage_code',
        ).defer(
            'asset_description',
        )


class OutAssetQuerySet(models.QuerySet):
    """
    OutAsset 查询集优化（方案1：通过 Asset FK 关联查询）

    去除冗余字段后，所有资产详情通过 outasset_code 双下划线关联查询。
    """

    def with_asset_details(self):
        """预加载资产完整信息（双下划线链式JOIN）"""
        return self.select_related(
            'outasset_code',
            'outasset_code__asset_type_code',
            'outasset_code__asset_contract_code',
            'outasset_code__asset_storage_code',
            'outasset_code__asset_applicant_jobcode',
            'outasset_code__asset_manager_jobcode',
        )

    def for_list(self):
        """出库列表页专用：defer() 排除大字段"""
        return self.with_asset_details().defer(
            'outasset_description',
        )


class RecycleAssetQuerySet(models.QuerySet):
    """
    RecycleAsset 查询集优化

    去除冗余字段后，资产详情通过 recycle_asset_code 关联查询。
    新增 operator_jobcode 记录回收操作人。
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            'recycle_asset_code',
            'recycle_asset_code__asset_type_code',
            'recycle_asset_code__asset_contract_code',
            'recycle_asset_code__asset_storage_code',
            'recycle_asset_code__asset_manager_jobcode',
            'operator_jobcode',
        )

    def for_list(self):
        """回收列表页专用：defer() 排除大字段"""
        return self.with_asset_details().defer(
            'recycle_asset_description',
        )


class DamagedAssetQuerySet(models.QuerySet):
    """
    DamagedAsset 查询集优化

    去除冗余字段后，资产详情通过 damaged_asset_code 关联查询。
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            'damaged_asset_code',
            'damaged_asset_code__asset_type_code',
            'damaged_asset_code__asset_contract_code',
            'damaged_asset_code__asset_storage_code',
            'damaged_asset_code__asset_manager_jobcode',
            'approver',
        )

    def for_list(self):
        """待报废列表页专用：defer() 排除大字段"""
        return self.with_asset_details().defer(
            'damaged_asset_description',
        )


class WasteAssetQuerySet(models.QuerySet):
    """
    WasteAsset 查询集优化

    去除冗余字段后，资产详情通过 waste_asset_code 关联查询。
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            'waste_asset_code',
            'waste_asset_code__asset_type_code',
            'waste_asset_code__asset_contract_code',
            'waste_asset_code__asset_storage_code',
            'waste_asset_code__asset_manager_jobcode',
            'source_damaged_asset',
        )

    def for_list(self):
        """已报废列表页专用：defer() 排除大字段"""
        return self.with_asset_details().defer(
            'waste_asset_description',
        )
