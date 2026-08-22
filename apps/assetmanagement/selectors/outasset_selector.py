"""
出库/回收/报废查询选择器

提供出库、回收、待报废、已报废记录的查询方法。
所有选择器类已拆分至独立模块,本文件仅做向后兼容 re-export。
"""

from apps.assetmanagement.selectors.broken_asset_selector import BrokenAssetSelector
from apps.assetmanagement.selectors.damaged_asset_selector import DamagedAssetSelector
from apps.assetmanagement.selectors.found_asset_selector import FoundAssetSelector
from apps.assetmanagement.selectors.lost_asset_selector import LostAssetSelector
from apps.assetmanagement.selectors.out_asset_selector import OutAssetSelector
from apps.assetmanagement.selectors.recycle_asset_selector import RecycleAssetSelector
from apps.assetmanagement.selectors.repair_asset_selector import RepairAssetSelector
from apps.assetmanagement.selectors.waste_asset_selector import WasteAssetSelector


__all__ = [
    "BrokenAssetSelector",
    "DamagedAssetSelector",
    "FoundAssetSelector",
    "LostAssetSelector",
    "OutAssetSelector",
    "RecycleAssetSelector",
    "RepairAssetSelector",
    "WasteAssetSelector",
]
