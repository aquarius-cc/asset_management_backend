"""
资产管理查询层包

提供资产管理的数据查询接口,封装复杂的数据库查询逻辑,
为业务层提供简洁的数据访问方法。所有查询方法均支持软删除过滤,
并通过select_related/prefetch_related优化查询性能。

模块结构:
- __init__.py: 统一导入入口,保持向后兼容
- asset_selector.py: 资产查询选择器 (AssetSelector, AssetTypeSelector)
- broken_asset_selector.py / found_asset_selector.py / lost_asset_selector.py /
  repair_asset_selector.py: 破损/失物/遗失/送修查询选择器
- out_asset_selector.py / recycle_asset_selector.py / damaged_asset_selector.py /
  waste_asset_selector.py: 出库/回收/待报废/已报废查询选择器
- base_selector.py: 基础查询选择器 (StorageSelector, ContractSelector, HardDiskSNSelector, DashboardSelector)

使用方式:
    # 方式1: 从包导入(推荐)
    from apps.assetmanagement.selectors import AssetSelector

    # 方式2: 从具体模块导入
    from apps.assetmanagement.selectors.asset_selector import AssetSelector
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
from apps.assetmanagement.selectors.broken_asset_selector import BrokenAssetSelector
from apps.assetmanagement.selectors.damaged_asset_selector import DamagedAssetSelector
from apps.assetmanagement.selectors.found_asset_selector import FoundAssetSelector
from apps.assetmanagement.selectors.lost_asset_selector import LostAssetSelector
from apps.assetmanagement.selectors.out_asset_selector import OutAssetSelector
from apps.assetmanagement.selectors.recycle_asset_selector import RecycleAssetSelector
from apps.assetmanagement.selectors.repair_asset_selector import RepairAssetSelector
from apps.assetmanagement.selectors.waste_asset_selector import WasteAssetSelector


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
