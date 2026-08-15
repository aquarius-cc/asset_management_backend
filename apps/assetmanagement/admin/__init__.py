"""
资产管理后台管理包

提供Django Admin后台管理配置,用于系统管理员管理数据。

模块结构:
- storage.py: StorageAdmin
- asset_type.py: AssetTypeAdmin
- contract.py: ContractAdmin
- asset.py: AssetAdmin
- out_asset.py: OutAssetAdmin
- recycle_asset.py: RecycleAssetAdmin
- damaged_asset.py: DamagedAssetAdmin
- waste_asset.py: WasteAssetAdmin
- hard_disk_sn.py: HardDiskSNAdmin
- broken_asset.py: BrokenAssetAdmin
- lost_asset.py: LostAssetAdmin
- found_asset.py: FoundAssetAdmin

使用方式:
    # 注意:由于原始admin.py已经注册了这些Admin配置,
    # 新的admin_new目录中的配置文件不使用@admin.register装饰器,
    # 而是导出Admin类供其他地方使用。
"""

# from apps.assetmanagement.admin.broken_asset import BrokenAssetAdmin
# from apps.assetmanagement.admin.found_asset import FoundAssetAdmin
# from apps.assetmanagement.admin.lost_asset import LostAssetAdmin
from apps.assetmanagement.admin.asset_admin import (
    AssetAdmin,
    AssetTypeAdmin,
    ContractAdmin,
    DamagedAssetAdmin,
    HardDiskSNAdmin,
    OutAssetAdmin,
    RecycleAssetAdmin,
    StorageAdmin,
    WasteAssetAdmin,
)
from apps.usermanagement.admin import DepartmentAdmin, EmployeeAdmin


__all__ = [
    "AssetAdmin",
    "AssetTypeAdmin",
    "BrokenAssetAdmin",
    "ContractAdmin",
    "DamagedAssetAdmin",
    "DepartmentAdmin",
    "EmployeeAdmin",
    "FoundAssetAdmin",
    "HardDiskSNAdmin",
    "LostAssetAdmin",
    "OutAssetAdmin",
    "RecycleAssetAdmin",
    "StorageAdmin",
    "WasteAssetAdmin",
]
