"""
资产管理模型包

提供资产管理系统所有数据模型，用于数据库设计和API数据交互。
所有模型均继承core.models.BaseModel以支持软删除和时间戳追踪。

模块结构：
- storage.py: Storage（仓库管理）
- asset_type.py: AssetType（资产类型管理）
- contract.py: Contract（合同管理）
- asset.py: Asset（资产管理）
- out_asset.py: OutAsset（出库资产管理）
- recycle_asset.py: RecycleAsset（回收资产管理）
- damaged_asset.py: DamagedAsset（待报废资产管理）
- waste_asset.py: WasteAsset（已报废资产管理）
- hard_disk_sn.py: HardDiskSN（硬盘序列号管理）
- broken_asset.py: BrokenAsset（已损坏资产管理）
- lost_asset.py: LostAsset（已遗失资产管理）
- found_asset.py: FoundAsset（资产找回记录）
- operation_log.py: AssetOperationLog（资产操作记录）

使用方式：
    # 方式1: 从包导入（推荐）
    from apps.assetmanagement.models import Asset, Storage

    # 方式2: 从具体模块导入
    from apps.assetmanagement.models.asset import Asset
"""

from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.models.asset_type import AssetType, MAX_ASSET_TYPE_LEVEL
from apps.assetmanagement.models.broken_asset import BrokenAsset
from apps.assetmanagement.models.contract import Contract
from apps.assetmanagement.models.damaged_asset import DamagedAsset
from apps.assetmanagement.models.found_asset import FoundAsset
from apps.assetmanagement.models.hard_disk_sn import HardDiskSN
from apps.assetmanagement.models.lost_asset import LostAsset
from apps.assetmanagement.models.operation_log import AssetOperationLog, AssetStateLog
from apps.assetmanagement.models.out_asset import OutAsset, generate_outassetrecordcode
from apps.assetmanagement.models.recycle_asset import RecycleAsset
from apps.assetmanagement.models.repair_asset import RepairAsset
from apps.assetmanagement.models.storage import Storage
from apps.assetmanagement.models.waste_asset import WasteAsset


__all__ = [
    "Asset",
    "AssetOperationLog",
    "AssetStateLog",
    "AssetType",
    "BrokenAsset",
    "Contract",
    "DamagedAsset",
    "FoundAsset",
    "HardDiskSN",
    "LostAsset",
    "OutAsset",
    "RecycleAsset",
    "RepairAsset",
    "Storage",
    "WasteAsset",
    "generate_outassetrecordcode",
]
