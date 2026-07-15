"""
资产管理后台管理包

提供Django Admin后台管理配置，用于系统管理员管理数据。

模块结构：
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

使用方式：
    # 注意：由于原始admin.py已经注册了这些Admin配置，
    # 新的admin_new目录中的配置文件不使用@admin.register装饰器，
    # 而是导出Admin类供其他地方使用。
"""

# from apps.assetmanagement.admin.broken_asset import BrokenAssetAdmin
# from apps.assetmanagement.admin.found_asset import FoundAssetAdmin
# from apps.assetmanagement.admin.lost_asset import LostAssetAdmin
from apps.assetmanagement.admin.asset_admin import AssetAdmin
from apps.assetmanagement.admin.asset_admin import OutAssetAdmin
from apps.assetmanagement.admin.asset_admin import RecycleAssetAdmin
from apps.assetmanagement.admin.asset_admin import DamagedAssetAdmin
from apps.assetmanagement.admin.asset_admin import WasteAssetAdmin
from apps.assetmanagement.admin.asset_admin import HardDiskSNAdmin
from apps.assetmanagement.admin.asset_admin import StorageAdmin
from apps.assetmanagement.admin.asset_admin import AssetTypeAdmin
from apps.assetmanagement.admin.asset_admin import ContractAdmin
from apps.usermanagement.admin import EmployeeAdmin
from apps.usermanagement.admin import DepartmentAdmin




__all__ = [
    "BrokenAssetAdmin",
    "FoundAssetAdmin",
    "LostAssetAdmin",
    "AssetAdmin",
    "OutAssetAdmin",
    "RecycleAssetAdmin",
    "DamagedAssetAdmin",
    "WasteAssetAdmin",
    "HardDiskSNAdmin",
    "StorageAdmin",
    "AssetTypeAdmin",
    "ContractAdmin",
    "EmployeeAdmin",
    "DepartmentAdmin",
]
