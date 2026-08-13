"""
资产管理服务层包

提供资产管理的核心业务逻辑,封装资产的创建、更新、删除、出库、回收、报废等操作,
确保业务规则的一致性和数据完整性。所有写操作均使用事务装饰器确保数据一致性。

模块结构:
- __init__.py: 统一导入入口,保持向后兼容
- asset_service.py: 资产管理服务 (AssetService, AssetCodeGenerator)
- out_asset_service.py: 出库资产管理服务 (OutAssetService)
- recycle_asset_service.py: 回收资产管理服务 (RecycleAssetService)
- damaged_asset_service.py: 待报废资产管理服务 (DamagedAssetService)
- waste_asset_service.py: 已报废资产管理服务 (WasteAssetService)
- contract_service.py: 合同管理服务 (ContractService)
- storage_service.py: 仓库管理服务 (StorageService)
- asset_type_service.py: 资产类型管理服务 (AssetTypeService)
- hard_disk_sn_service.py: 硬盘序列号管理服务 (HardDiskSNService)
- operation_log_service.py: 操作日志服务 (OperationLogService)

使用方式:
    # 方式1: 从包导入(推荐)
    from apps.assetmanagement.services import AssetService

    # 方式2: 从具体模块导入
    from apps.assetmanagement.services.asset_service import AssetService
"""

# 导入所有服务类,保持向后兼容
from apps.assetmanagement.services.asset_service import (
    ASSET_UPDATE_ALLOWED_FIELDS,
    AssetCodeGenerator,
    AssetService,
)
from apps.assetmanagement.services.asset_type_service import AssetTypeService
from apps.assetmanagement.services.contract_service import ContractService
from apps.assetmanagement.services.damaged_asset_service import DamagedAssetService
from apps.assetmanagement.services.hard_disk_sn_service import HardDiskSNService
from apps.assetmanagement.services.operation_log_service import OperationLogService
from apps.assetmanagement.services.out_asset_service import (
    OUTASSET_UPDATE_ALLOWED_FIELDS,
    OutAssetService,
)
from apps.assetmanagement.services.recycle_asset_service import RecycleAssetService
from apps.assetmanagement.services.storage_service import StorageService
from apps.assetmanagement.services.waste_asset_service import WasteAssetService


__all__ = [
    "ASSET_UPDATE_ALLOWED_FIELDS",
    "OUTASSET_UPDATE_ALLOWED_FIELDS",
    "AssetCodeGenerator",
    "AssetService",
    "AssetTypeService",
    "ContractService",
    "DamagedAssetService",
    "HardDiskSNService",
    "OperationLogService",
    "OutAssetService",
    "RecycleAssetService",
    "StorageService",
    "WasteAssetService",
]
