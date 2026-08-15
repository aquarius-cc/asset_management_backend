"""
资产管理服务层

该模块提供资产管理的核心业务逻辑,封装资产的创建、更新、删除、出库、回收、报废等操作,
确保业务规则的一致性和数据完整性。所有写操作均使用事务装饰器确保数据一致性。

包含以下服务类:
- AssetService: 资产管理服务
- OutAssetService: 出库资产管理服务
- RecycleAssetService: 回收资产管理服务
- DamagedAssetService: 待报废资产管理服务
- WasteAssetService: 已报废资产管理服务
- ContractService: 合同管理服务
- StorageService: 仓库管理服务
- AssetTypeService: 资产类型管理服务
- HardDiskSNService: 硬盘序列号管理服务

【拆分说明】
为提高代码可维护性,各服务类已拆分到独立文件中。
本文件保留所有导入以保持向后兼容性。
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
