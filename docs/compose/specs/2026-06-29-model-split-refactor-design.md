# AssetManagement 模块按模型拆分重构方案

> 版本: v2.0 | 日期: 2026-06-29 | 状态: 待审批

---

## 1. 背景与目标

当前 `apps/assetmanagement/` 模块存在文件过大、职责混杂的问题，影响代码可维护性和开发效率。本方案将按模型拆分各层文件，使每个模型拥有独立的 models、serializers、selectors、services、views、admin 文件。

### 1.1 当前问题

| 文件 | 大小 | 问题 |
|------|------|------|
| models.py | 52KB | 12个模型混在一起，修改任一模型需浏览整个文件 |
| views.py | 114KB | 所有ViewSet混在一起，职责不清晰 |
| serializers/outasset_serializers.py | 37KB | 4个模型的序列化器混在一起 |
| selectors/outasset_selector.py | - | 多个模型的Selector混在一起 |

### 1.2 拆分目标

- 每个模型拥有独立的文件目录
- 单个文件大小控制在10KB以内
- 文件职责单一，便于维护
- 新增模型时只需新增目录，不影响现有代码

---

## 2. 拆分范围

### 2.1 涉及的模型（12个）

| 模型 | 当前位置 | 拆分优先级 |
|------|---------|-----------|
| Storage | models.py | 高 |
| AssetType | models.py | 高 |
| Contract | models.py | 高 |
| Asset | models.py | 高 |
| OutAsset | models.py | 高 |
| RecycleAsset | models.py | 高 |
| DamagedAsset | models.py | 高 |
| WasteAsset | models.py | 高 |
| HardDiskSN | models.py | 中 |
| BrokenAsset | models.py | 高 |
| LostAsset | models.py | 高 |
| FoundAsset | models.py | 高 |
| AssetOperationLog | models.py | 中 |

### 2.2 涉及的层级

| 层级 | 当前结构 | 拆分方式 | 说明 |
|------|---------|---------|------|
| models | models.py | models/{model_name}.py | 模型定义 |
| querysets | querysets.py | models/{model_name}.py（内联） | 拆分后删除querysets.py |
| serializers | serializers/{group}.py | serializers/{model_name}.py | 序列化器 |
| selectors | selectors/{group}.py | selectors/{model_name}.py | 查询选择器 |
| services | services/{model_name}.py | 保持不变，统一命名 | 已拆分，需统一命名 |
| views | views.py | views/{model_name}.py | 视图层 |
| admin | admin.py | admin/{model_name}.py | 后台管理 |

---

## 3. 目标目录结构

```
apps/assetmanagement/
├── __init__.py
├── apps.py
├── urls.py
├── dashboard_urls.py
├── interfaces.py
├── audit.py
│
├── models/                            # 模型层
│   ├── __init__.py                    # 统一导出所有模型
│   ├── storage.py                     # Storage
│   ├── asset_type.py                  # AssetType
│   ├── contract.py                    # Contract
│   ├── asset.py                       # Asset
│   ├── out_asset.py                   # OutAsset
│   ├── recycle_asset.py               # RecycleAsset
│   ├── damaged_asset.py               # DamagedAsset
│   ├── waste_asset.py                 # WasteAsset
│   ├── hard_disk_sn.py                # HardDiskSN
│   ├── broken_asset.py                # BrokenAsset
│   ├── lost_asset.py                  # LostAsset
│   ├── found_asset.py                 # FoundAsset
│   └── operation_log.py               # AssetOperationLog
│
├── serializers/                       # 序列化器层
│   ├── __init__.py                    # 统一导出
│   ├── storage.py                     # Storage序列化器
│   ├── asset_type.py                  # AssetType序列化器
│   ├── contract.py                    # Contract序列化器
│   ├── asset.py                       # Asset序列化器
│   ├── out_asset.py                   # OutAsset序列化器
│   ├── recycle_asset.py               # RecycleAsset序列化器
│   ├── damaged_asset.py               # DamagedAsset序列化器
│   ├── waste_asset.py                 # WasteAsset序列化器
│   ├── hard_disk_sn.py                # HardDiskSN序列化器
│   ├── broken_asset.py                # BrokenAsset序列化器
│   ├── lost_asset.py                  # LostAsset序列化器
│   ├── found_asset.py                 # FoundAsset序列化器
│   ├── operation_log.py               # AssetOperationLog序列化器
│   ├── batch.py                       # 批量操作序列化器
│   └── common.py                      # 通用序列化器
│
├── selectors/                         # 查询层
│   ├── __init__.py                    # 统一导出
│   ├── storage.py                     # StorageSelector
│   ├── asset_type.py                  # AssetTypeSelector
│   ├── contract.py                    # ContractSelector
│   ├── asset.py                       # AssetSelector
│   ├── out_asset.py                   # OutAssetSelector
│   ├── recycle_asset.py               # RecycleAssetSelector
│   ├── damaged_asset.py               # DamagedAssetSelector
│   ├── waste_asset.py                 # WasteAssetSelector
│   ├── hard_disk_sn.py                # HardDiskSNSelector
│   ├── broken_asset.py                # BrokenAssetSelector
│   ├── lost_asset.py                  # LostAssetSelector
│   ├── found_asset.py                 # FoundAssetSelector
│   ├── dashboard.py                   # DashboardSelector
│   └── operation_log.py               # OperationLogSelector
│
├── services/                          # 服务层（已拆分，需统一命名）
│   ├── __init__.py
│   ├── storage_service.py
│   ├── asset_type_service.py
│   ├── contract_service.py
│   ├── asset_service.py
│   ├── out_asset_service.py           # 统一命名（原outasset_service.py）
│   ├── recycle_asset_service.py       # 统一命名（原recycle_service.py）
│   ├── damaged_asset_service.py       # 统一命名（原damaged_service.py）
│   ├── waste_asset_service.py         # 统一命名（原waste_service.py）
│   ├── hard_disk_sn_service.py        # 统一命名（原harddisk_service.py）
│   └── operation_log_service.py
│
├── views/                             # 视图层
│   ├── __init__.py                    # 统一导出
│   ├── storage.py                     # StorageViewSet
│   ├── asset_type.py                  # AssetTypeViewSet
│   ├── contract.py                    # ContractViewSet
│   ├── asset.py                       # AssetViewSet
│   ├── out_asset.py                   # OutAssetViewSet
│   ├── recycle_asset.py               # RecycleAssetViewSet
│   ├── damaged_asset.py               # DamagedAssetViewSet
│   ├── waste_asset.py                 # WasteAssetViewSet
│   ├── hard_disk_sn.py                # HardDiskSNViewSet
│   ├── broken_asset.py                # BrokenAssetViewSet
│   ├── lost_asset.py                  # LostAssetViewSet
│   ├── found_asset.py                 # FoundAssetViewSet
│   ├── dashboard.py                   # DashboardViewSet
│   └── operation_log.py               # 操作日志视图
│
├── admin/                             # 后台管理
│   ├── __init__.py                    # 统一注册
│   ├── storage.py
│   ├── asset_type.py
│   ├── contract.py
│   ├── asset.py
│   ├── out_asset.py
│   ├── recycle_asset.py
│   ├── damaged_asset.py
│   ├── waste_asset.py
│   ├── hard_disk_sn.py
│   ├── broken_asset.py
│   ├── lost_asset.py
│   └── found_asset.py
│
├── state_machine/                     # 状态机（保持不变）
│   ├── __init__.py
│   └── core.py
│
├── management/                        # 管理命令（保持不变）
│   └── commands/
│
├── migrations/                        # 数据库迁移（保持不变）
│
└── tests/                             # 测试（保持不变）
```

**注意：** 不需要创建 `models/base.py`，公共基类已存在于 `core/models.py`：
- `BaseModel` — 提供 recordcode、is_active、is_deleted 字段和软删除方法
- `SoftDeleteManager` — 默认过滤已删除记录的管理器
- `TimestampModel` — 提供 created_at、updated_at 时间戳
- `generate_recordcode_with_prefix()` — 生成唯一记录编码

---

## 4. 详细拆分规则

### 4.1 models层拆分

**规则：**
- 每个模型一个文件，文件名使用snake_case
- 所有模型通过 `models/__init__.py` 统一导出
- QuerySet类内联到对应的模型文件中
- 公共基类从 `core.models` 导入，无需在assetmanagement中重复定义

**示例：models/asset.py**
```python
from django.db import models
from django.utils import timezone
from core.models import BaseModel, SoftDeleteManager  # 从core导入公共基类

class AssetQuerySet(models.QuerySet):
    def for_list(self):
        return self.with_basic_relations().with_person_relations()
    # ...

class Asset(BaseModel):
    RECORDCODE_PREFIX = "ENTRY"
    ASSET_STATUS_CHOICES = [...]
    # ... 字段定义
    
    objects = SoftDeleteManager.from_queryset(AssetQuerySet)()
    
    class Meta:
        db_table = "am_asset"
```

**models/__init__.py 示例：**
```python
from apps.assetmanagement.models.storage import Storage
from apps.assetmanagement.models.asset_type import AssetType
from apps.assetmanagement.models.contract import Contract
from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.models.out_asset import OutAsset
from apps.assetmanagement.models.recycle_asset import RecycleAsset
from apps.assetmanagement.models.damaged_asset import DamagedAsset
from apps.assetmanagement.models.waste_asset import WasteAsset
from apps.assetmanagement.models.hard_disk_sn import HardDiskSN
from apps.assetmanagement.models.broken_asset import BrokenAsset
from apps.assetmanagement.models.lost_asset import LostAsset
from apps.assetmanagement.models.found_asset import FoundAsset
from apps.assetmanagement.models.operation_log import AssetOperationLog

__all__ = [
    'Storage', 'AssetType', 'Contract', 'Asset', 'OutAsset',
    'RecycleAsset', 'DamagedAsset', 'WasteAsset', 'HardDiskSN',
    'BrokenAsset', 'LostAsset', 'FoundAsset', 'AssetOperationLog',
]
```

### 4.2 serializers层拆分

**规则：**
- 每个模型一个文件，包含List/Create/Update/Detail四个序列化器
- 批量操作序列化器放在 `serializers/batch.py`
- 通用序列化器放在 `serializers/common.py`
- 所有序列化器通过 `serializers/__init__.py` 统一导出

**示例：serializers/asset.py**
```python
from rest_framework import serializers
from apps.assetmanagement.models.asset import Asset

class AssetListSerializer(serializers.ModelSerializer):
    # ... 字段定义

class AssetCreateSerializer(serializers.ModelSerializer):
    # ... 字段定义

class AssetUpdateSerializer(serializers.ModelSerializer):
    # ... 字段定义

class AssetDetailSerializer(serializers.ModelSerializer):
    # ... 字段定义

AssetSerializer = AssetListSerializer  # 向后兼容
```

### 4.3 selectors层拆分

**规则：**
- 每个模型一个文件
- DashboardSelector放在 `selectors/dashboard.py`
- 所有Selector通过 `selectors/__init__.py` 统一导出

### 4.4 views层拆分

**规则：**
- 每个ViewSet一个文件
- 文件名与模型名一致
- 所有ViewSet通过 `views/__init__.py` 统一导出
- urls.py引用 `views/__init__.py` 中的导出

### 4.5 admin层拆分

**规则：**
- 每个模型的Admin配置一个文件
- 所有Admin通过 `admin/__init__.py` 统一注册

---

## 5. 导入路径变更

### 5.1 当前导入方式

```python
from apps.assetmanagement.models import Asset, Storage
from apps.assetmanagement.serializers import AssetSerializer
from apps.assetmanagement.views import AssetViewSet
```

### 5.2 拆分后导入方式

```python
# 方式1：从包导入（推荐，保持向后兼容）
from apps.assetmanagement.models import Asset, Storage
from apps.assetmanagement.serializers import AssetSerializer
from apps.assetmanagement.views import AssetViewSet

# 方式2：从具体模块导入（更精确）
from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.serializers.asset import AssetSerializer
from apps.assetmanagement.views.asset import AssetViewSet
```

**关键点：** `__init__.py` 统一导出，保持向后兼容，现有代码无需修改。

---

## 6. 实施步骤

### 6.1 第一阶段：准备（无代码变更）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1 | 创建新的目录结构 | 空目录 |
| 2 | 创建各层的 `__init__.py` | 统一导出（暂为空） |

### 6.2 第二阶段：模型层拆分

| 步骤 | 内容 | 影响范围 |
|------|------|---------|
| 1 | 拆分Storage到 `models/storage.py` | 无 |
| 2 | 拆分AssetType到 `models/asset_type.py` | 无 |
| 3 | 拆分Contract到 `models/contract.py` | 无 |
| 4 | 拆分Asset到 `models/asset.py` | 无 |
| 5 | 拆分OutAsset到 `models/out_asset.py` | 无 |
| 6 | 拆分RecycleAsset到 `models/recycle_asset.py` | 无 |
| 7 | 拆分DamagedAsset到 `models/damaged_asset.py` | 无 |
| 8 | 拆分WasteAsset到 `models/waste_asset.py` | 无 |
| 9 | 拆分HardDiskSN到 `models/hard_disk_sn.py` | 无 |
| 10 | 拆分BrokenAsset到 `models/broken_asset.py` | 无 |
| 11 | 拆分LostAsset到 `models/lost_asset.py` | 无 |
| 12 | 拆分FoundAsset到 `models/found_asset.py` | 无 |
| 13 | 拆分AssetOperationLog到 `models/operation_log.py` | 无 |
| 14 | 更新 `models/__init__.py` | 所有导入 |
| 15 | 删除旧的 `models.py` | - |
| 16 | 删除 `querysets.py`（QuerySet已内联到各模型文件） | - |
| 17 | 运行测试验证 | 全部通过 |

### 6.3 第三阶段：序列化器层拆分

| 步骤 | 内容 |
|------|------|
| 1 | 拆分各模型序列化器到独立文件 |
| 2 | 创建 `serializers/batch.py`（批量操作序列化器） |
| 3 | 创建 `serializers/common.py`（通用序列化器） |
| 4 | 更新 `serializers/__init__.py` |
| 5 | 删除旧的序列化器文件 |
| 6 | 运行测试验证 |

### 6.4 第四阶段：查询层拆分

| 步骤 | 内容 |
|------|------|
| 1 | 拆分各模型Selector到独立文件 |
| 2 | 更新 `selectors/__init__.py` |
| 3 | 删除旧的Selector文件 |
| 4 | 运行测试验证 |

### 6.5 第五阶段：服务层命名统一

| 步骤 | 内容 | 说明 |
|------|------|------|
| 1 | 重命名 `outasset_service.py` → `out_asset_service.py` | 统一命名规范 |
| 2 | 重命名 `recycle_service.py` → `recycle_asset_service.py` | 统一命名规范 |
| 3 | 重命名 `damaged_service.py` → `damaged_asset_service.py` | 统一命名规范 |
| 4 | 重命名 `waste_service.py` → `waste_asset_service.py` | 统一命名规范 |
| 5 | 重命名 `harddisk_service.py` → `hard_disk_sn_service.py` | 统一命名规范 |
| 6 | 更新 `services/__init__.py` | 更新导入 |
| 7 | 更新所有引用这些服务的文件 | views.py等 |
| 8 | 运行测试验证 | 全部通过 |

### 6.6 第六阶段：视图层拆分

| 步骤 | 内容 |
|------|------|
| 1 | 拆分各ViewSet到独立文件 |
| 2 | 更新 `views/__init__.py` |
| 3 | 删除旧的 `views.py` |
| 4 | 更新 `urls.py` |
| 5 | 运行测试验证 |

### 6.7 第七阶段：Admin层拆分

| 步骤 | 内容 |
|------|------|
| 1 | 拆分各Admin配置到独立文件 |
| 2 | 更新 `admin/__init__.py` |
| 3 | 删除旧的 `admin.py` |
| 4 | 运行测试验证 |

### 6.8 第八阶段：清理与验证

| 步骤 | 内容 |
|------|------|
| 1 | 删除所有旧文件 |
| 2 | 清理 `__pycache__` |
| 3 | 运行完整测试套件 |
| 4 | 运行 `mypy` 类型检查 |
| 5 | 运行 `ruff` 代码规范检查 |
| 6 | 更新文档 |

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 循环导入 | 高 | 先拆分底层模型，再拆分上层 |
| 测试失败 | 中 | 每步拆分后立即运行测试 |
| 迁移文件失效 | 低 | Django迁移基于模型路径，需确保正确配置 |
| 第三方库不兼容 | 低 | 检查Django Admin等对模型路径的依赖 |

---

## 8. 回滚方案

### 8.1 每阶段回滚

| 阶段 | 回滚方式 |
|------|---------|
| 模型层拆分 | 恢复旧的models.py，删除models/目录 |
| 序列化器层拆分 | 恢复旧的serializers/文件，删除新文件 |
| 查询层拆分 | 恢复旧的selectors/文件，删除新文件 |
| 视图层拆分 | 恢复旧的views.py，删除views/目录 |
| Admin层拆分 | 恢复旧的admin.py，删除admin/目录 |

### 8.2 完整回滚

若拆分过程中出现严重问题，可通过Git回退到拆分前的提交：
```bash
git log --oneline -10  # 查看拆分前的提交
git revert <commit-hash>  # 回退到拆分前状态
```

### 8.3 回滚验证

回滚后必须验证：
1. 所有测试通过
2. 所有API端点正常
3. 数据库迁移状态正确

---

## 9. 验证清单

- [ ] 所有模型正确导出
- [ ] 所有序列化器正确导出
- [ ] 所有Selector正确导出
- [ ] 所有ViewSet正确导出
- [ ] 所有Admin正确注册
- [ ] urls.py路由正确
- [ ] services命名统一（out_asset_service等）
- [ ] querysets.py已删除
- [ ] 所有测试通过
- [ ] mypy检查通过
- [ ] ruff检查通过
- [ ] 文档更新
- [ ] 回滚方案验证

---

## 10. 预期收益

| 指标 | 拆分前 | 拆分后 |
|------|-------|-------|
| models.py大小 | 52KB | 13个文件，每个<5KB |
| views.py大小 | 114KB | 13个文件，每个<10KB |
| 单文件职责 | 混杂 | 单一 |
| 新增模型影响 | 修改多个文件 | 只需新增目录 |
| 代码导航 | 困难 | 清晰 |

---

## 10. 变更文件清单

| 类型 | 文件数量 | 说明 |
|------|---------|------|
| 新增 | ~50个 | 各层拆分后的新文件 |
| 修改 | ~5个 | __init__.py, urls.py等 |
| 删除 | ~8个 | 旧的合并文件 |

---

## 11. 实施时间估计

| 阶段 | 预计时间 |
|------|---------|
| 准备 | 0.5小时 |
| 模型层拆分 | 2小时 |
| 序列化器层拆分 | 2小时 |
| 查询层拆分 | 1小时 |
| 服务层命名统一 | 1小时 |
| 视图层拆分 | 2小时 |
| Admin层拆分 | 0.5小时 |
| 清理与验证 | 1小时 |
| 回滚方案验证 | 0.5小时 |
| **总计** | **10.5小时** |
