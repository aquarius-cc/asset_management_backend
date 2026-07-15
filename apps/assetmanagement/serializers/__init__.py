"""
资产管理序列化器包

提供资产管理系统所有模型的序列化器，用于API数据的序列化和反序列化。
所有序列化器遵循DRF最佳实践，支持完整的CRUD操作和数据验证。

模块结构：
- __init__.py: 统一导入入口，保持向后兼容
- base_model_serializers.py: 基础模型序列化器 (Storage, AssetType, Contract, HardDiskSN)
- lifecycle_serializers.py: 生命周期序列化器 (BrokenAsset, LostAsset, FoundAsset)
- asset_crud_serializers.py: 资产 CRUD 序列化器 (Asset, AssetCreate, AssetDetail, CombinedAsset)
- asset_batch_serializers.py: 资产批量操作序列化器 (AssetBatchItem, AssetBatchCreate, AssetBatchDelete)
- out_asset_serializers.py: 出库相关序列化器 (OutAsset)
- recycle_asset_serializers.py: 回收资产序列化器 (RecycleAsset)
- damaged_asset_serializers.py: 待报废资产序列化器 (DamagedAsset)
- waste_asset_serializers.py: 已报废资产序列化器 (WasteAsset)
- batch_serializers.py: 通用批量操作序列化器 (Contract/Storage/AssetType 批量)
- common_serializers.py: 通用序列化器 (DashboardStat, ErrorResponse, Empty)

使用方式：
    # 方式1: 从包导入（推荐）
    from apps.assetmanagement.serializers import AssetSerializer

    # 方式2: 从具体模块导入
    from apps.assetmanagement.serializers.asset_crud_serializers import AssetSerializer
"""

# 导入所有序列化器类，保持向后兼容
from apps.assetmanagement.serializers.asset_batch_serializers import (
    AssetBatchCreateSerializer,
    AssetBatchDeleteSerializer,
    AssetBatchItemSerializer,
)
from apps.assetmanagement.serializers.asset_crud_serializers import (
    AssetCreateSerializer,
    AssetDetailSerializer,
    AssetListSerializer,
    AssetOperationLogSerializer,
    AssetSerializer,
    AssetUpdateSerializer,
    CombinedAssetSerializer,
)
from apps.assetmanagement.serializers.base_model_serializers import (
    AssetTypeSerializer,
    AssettypeSimpleSerializer,
    CodeField,
    ContractCreateSerializer,
    ContractDetailSerializer,
    ContractListSerializer,
    ContractSimpleSerializer,
    ContractUpdateSerializer,
    DiskItemSerializer,
    HardDiskSNBatchSerializer,
    HardDiskSNCreateSerializer,
    HardDiskSNSerializer,
    HardDiskSNSimpleSerializer,
    StorageSerializer,
    StorageSimpleSerializer,
)
from apps.assetmanagement.serializers.lifecycle_serializers import (
    BrokenAssetCreateSerializer,
    BrokenAssetDetailSerializer,
    BrokenAssetListSerializer,
    BrokenAssetSerializer,
    BrokenAssetUpdateSerializer,
    FoundAssetCreateSerializer,
    FoundAssetDetailSerializer,
    FoundAssetListSerializer,
    FoundAssetSerializer,
    FoundAssetUpdateSerializer,
    LostAssetCreateSerializer,
    LostAssetDetailSerializer,
    LostAssetListSerializer,
    LostAssetSerializer,
    LostAssetUpdateSerializer,
)
from apps.assetmanagement.serializers.common_serializers import (
    DashboardStatSerializer,
    EmptySerializer,
    ErrorResponseSerializer,
)
from apps.assetmanagement.serializers.out_asset_serializers import (
    OutAssetBatchCreateSerializer,
    OutAssetBatchDeleteSerializer,
    OutAssetBatchItemSerializer,
    OutAssetCreateSerializer,
    OutAssetDetailSerializer,
    OutAssetListSerializer,
    OutAssetSerializer,  # 向后兼容别名
    OutAssetUpdateSerializer,
)
from apps.assetmanagement.serializers.recycle_asset_serializers import (
    RecycleAssetBatchCreateSerializer,
    RecycleAssetBatchDeleteSerializer,
    RecycleAssetBatchItemSerializer,
    RecycleAssetCreateSerializer,
    RecycleAssetDetailSerializer,
    RecycleAssetListSerializer,
    RecycleAssetSerializer,  # 向后兼容别名
    RecycleAssetUpdateSerializer,
)
from apps.assetmanagement.serializers.damaged_asset_serializers import (
    DamagedAssetAproveSerializer,
    DamagedAssetBatchDeleteSerializer,
    DamagedAssetCreateSerializer,
    DamagedAssetDetailSerializer,
    DamagedAssetListSerializer,
    DamagedAssetSerializer,  # 向后兼容别名
    DamagedAssetUpdateSerializer,
)
from apps.assetmanagement.serializers.waste_asset_serializers import (
    WasteAssetBatchDeleteSerializer,
    WasteAssetCreateSerializer,
    WasteAssetDetailSerializer,
    WasteAssetListSerializer,
    WasteAssetSerializer,  # 向后兼容别名
)
from apps.assetmanagement.serializers.batch_serializers import (
    AssetTypeBatchCreateItemSerializer,
    AssetTypeBatchCreateSerializer,
    AssetTypeBatchDeleteSerializer,
    ContractBatchCreateItemSerializer,
    ContractBatchCreateSerializer,
    ContractBatchDeleteSerializer,
    StorageBatchCreateItemSerializer,
    StorageBatchCreateSerializer,
    StorageBatchDeleteSerializer,
)
from apps.assetmanagement.serializers.repair_asset_serializers import (
    RepairAssetCreateSerializer,
    RepairAssetDetailSerializer,
    RepairAssetListSerializer,
    RepairAssetUpdateSerializer,
)


__all__ = [
    # 基础序列化器
    "StorageSerializer",
    "AssetTypeSerializer",
    "ContractListSerializer",
    "ContractCreateSerializer",
    "ContractUpdateSerializer",
    "ContractDetailSerializer",
    "HardDiskSNSimpleSerializer",
    "HardDiskSNSerializer",
    "HardDiskSNCreateSerializer",
    "DiskItemSerializer",
    "HardDiskSNBatchSerializer",
    "CodeField",
    "ContractSimpleSerializer",
    "StorageSimpleSerializer",
    "AssettypeSimpleSerializer",
    # BrokenAsset 序列化器
    "BrokenAssetListSerializer",
    "BrokenAssetCreateSerializer",
    "BrokenAssetUpdateSerializer",
    "BrokenAssetDetailSerializer",
    "BrokenAssetSerializer",
    # LostAsset 序列化器
    "LostAssetListSerializer",
    "LostAssetCreateSerializer",
    "LostAssetUpdateSerializer",
    "LostAssetDetailSerializer",
    "LostAssetSerializer",
    # FoundAsset 序列化器
    "FoundAssetListSerializer",
    "FoundAssetCreateSerializer",
    "FoundAssetUpdateSerializer",
    "FoundAssetDetailSerializer",
    "FoundAssetSerializer",
    # 资产序列化器
    "AssetSerializer",
    "AssetListSerializer",
    "AssetDetailSerializer",
    "AssetCreateSerializer",
    "AssetUpdateSerializer",
    "CombinedAssetSerializer",
    "AssetOperationLogSerializer",
    "AssetBatchItemSerializer",
    "AssetBatchCreateSerializer",
    "AssetBatchDeleteSerializer",
    # OutAsset 序列化器
    "OutAssetListSerializer",
    "OutAssetCreateSerializer",
    "OutAssetUpdateSerializer",
    "OutAssetDetailSerializer",
    "OutAssetSerializer",  # 向后兼容别名
    # RecycleAsset 序列化器
    "RecycleAssetListSerializer",
    "RecycleAssetCreateSerializer",
    "RecycleAssetUpdateSerializer",
    "RecycleAssetDetailSerializer",
    "RecycleAssetSerializer",  # 向后兼容别名
    # DamagedAsset 序列化器
    "DamagedAssetSerializer",
    "DamagedAssetCreateSerializer",
    "DamagedAssetUpdateSerializer",
    "DamagedAssetAproveSerializer",
    "DamagedAssetListSerializer",
    "DamagedAssetDetailSerializer",
    # WasteAsset 序列化器
    "WasteAssetSerializer",
    "WasteAssetCreateSerializer",
    "WasteAssetListSerializer",
    "WasteAssetDetailSerializer",
    # 批量操作序列化器
    "ContractBatchDeleteSerializer",
    "ContractBatchCreateItemSerializer",
    "ContractBatchCreateSerializer",
    "StorageBatchDeleteSerializer",
    "StorageBatchCreateItemSerializer",
    "StorageBatchCreateSerializer",
    "AssetTypeBatchDeleteSerializer",
    "AssetTypeBatchCreateItemSerializer",
    "AssetTypeBatchCreateSerializer",
    "RecycleAssetBatchItemSerializer",
    "RecycleAssetBatchCreateSerializer",
    "RecycleAssetBatchDeleteSerializer",
    "OutAssetBatchItemSerializer",
    "OutAssetBatchCreateSerializer",
    "OutAssetBatchDeleteSerializer",
    "DamagedAssetBatchDeleteSerializer",
    "WasteAssetBatchDeleteSerializer",
    # RepairAsset 序列化器
    "RepairAssetListSerializer",
    "RepairAssetCreateSerializer",
    "RepairAssetUpdateSerializer",
    "RepairAssetDetailSerializer",
]
