"""
资产管理视图包

提供所有资产管理相关的视图集,向后兼容原有导入路径。
"""

from .asset_lifecycle_view import (
    BrokenAssetViewSet,
    FoundAssetViewSet,
    LostAssetViewSet,
    RepairAssetViewSet,
)
from .asset_type_view import AssetTypeViewSet
from .asset_view import AssetViewSet
from .contract_view import ContractViewSet
from .damaged_asset_view import DamagedAssetViewSet
from .dashboard_view import DashboardViewSet
from .hard_disk_sn_view import HardDiskSNViewSet
from .out_asset_view import OutAssetViewSet
from .recycle_asset_view import RecycleAssetViewSet
from .storage_view import StorageViewSet
from .waste_asset_view import WasteAssetViewSet


__all__ = [
    "AssetTypeViewSet",
    "AssetViewSet",
    "BrokenAssetViewSet",
    "ContractViewSet",
    "DamagedAssetViewSet",
    "DashboardViewSet",
    "FoundAssetViewSet",
    "HardDiskSNViewSet",
    "LostAssetViewSet",
    "OutAssetViewSet",
    "RecycleAssetViewSet",
    "RepairAssetViewSet",
    "StorageViewSet",
    "WasteAssetViewSet",
]
