"""
资产管理视图包

提供所有资产管理相关的视图集，向后兼容原有导入路径。
"""

from .storage_view import StorageViewSet
from .asset_type_view import AssetTypeViewSet
from .contract_view import ContractViewSet
from .asset_view import AssetViewSet
from .out_asset_view import OutAssetViewSet
from .recycle_asset_view import RecycleAssetViewSet
from .damaged_asset_view import DamagedAssetViewSet
from .waste_asset_view import WasteAssetViewSet
from .hard_disk_sn_view import HardDiskSNViewSet
from .dashboard_view import DashboardViewSet
from .asset_lifecycle_view import (
    BrokenAssetViewSet,
    LostAssetViewSet,
    FoundAssetViewSet,
    RepairAssetViewSet,
)

__all__ = [
    "StorageViewSet",
    "AssetTypeViewSet",
    "ContractViewSet",
    "AssetViewSet",
    "OutAssetViewSet",
    "RecycleAssetViewSet",
    "DamagedAssetViewSet",
    "WasteAssetViewSet",
    "HardDiskSNViewSet",
    "DashboardViewSet",
    "BrokenAssetViewSet",
    "LostAssetViewSet",
    "FoundAssetViewSet",
    "RepairAssetViewSet",
]
