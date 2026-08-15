"""
资产管理查询层

该模块提供资产管理的数据查询接口,封装复杂的数据库查询逻辑,
为业务层提供简洁的数据访问方法。所有查询方法均支持软删除过滤,
并通过select_related/prefetch_related优化查询性能。

【拆分说明】
为提高代码可维护性,各选择器类已拆分到独立文件中。
本文件保留所有导入以保持向后兼容性。

包含以下选择器类:
- AssetSelector: 资产查询选择器
- OutAssetSelector: 出库记录查询选择器
- StorageSelector: 仓库查询选择器
- ContractSelector: 合同查询选择器
- AssetTypeSelector: 资产类型查询选择器
- RecycleAssetSelector: 回收资产查询选择器
- DamagedAssetSelector: 待报废资产查询选择器
- WasteAssetSelector: 已报废资产查询选择器
- HardDiskSNSelector: 硬盘序列号查询选择器
- DashboardSelector: 仪表盘查询选择器
"""

# 导入所有选择器类,保持向后兼容
from apps.assetmanagement.selectors.asset_selector import (
    AssetSelector,
    AssetTypeSelector,
)
from apps.assetmanagement.selectors.base_selector import (
    ContractSelector,
    DashboardSelector,
    HardDiskSNSelector,
    StorageSelector,
)
from apps.assetmanagement.selectors.outasset_selector import (
    BrokenAssetSelector,
    DamagedAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
    OutAssetSelector,
    RecycleAssetSelector,
    WasteAssetSelector,
)


__all__ = [
    "AssetSelector",
    "AssetTypeSelector",
    "BrokenAssetSelector",
    "ContractSelector",
    "DamagedAssetSelector",
    "DashboardSelector",
    "FoundAssetSelector",
    "HardDiskSNSelector",
    "LostAssetSelector",
    "OutAssetSelector",
    "RecycleAssetSelector",
    "StorageSelector",
    "WasteAssetSelector",
]
