"""
资产管理查询层包

提供资产管理的数据查询接口，封装复杂的数据库查询逻辑，
为业务层提供简洁的数据访问方法。所有查询方法均支持软删除过滤，
并通过select_related/prefetch_related优化查询性能。

模块结构：
- __init__.py: 统一导入入口，保持向后兼容
- asset_selector.py: 资产查询选择器 (AssetSelector, AssetTypeSelector)
- outasset_selector.py: 出库/回收/报废查询选择器
    (OutAssetSelector, RecycleAssetSelector, DamagedAssetSelector, WasteAssetSelector)
- base_selector.py: 基础查询选择器 (StorageSelector, ContractSelector, HardDiskSNSelector, DashboardSelector)

使用方式：
    # 方式1: 从包导入（推荐）
    from apps.assetmanagement.selectors import AssetSelector

    # 方式2: 从具体模块导入
    from apps.assetmanagement.selectors.asset_selector import AssetSelector
"""

# 导入所有选择器类，保持向后兼容
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
    RepairAssetSelector,
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
    "RepairAssetSelector",
    "StorageSelector",
    "WasteAssetSelector",
]
