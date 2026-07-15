# 资产管理系统后端 - 综合审查报告（修复后）

> 审查时间: 2026-06-25
> 审查范围: 全量代码修复后的综合审查

---

## 一、已修复问题汇总

### P0 级（功能不可用）- 已全部修复

| 编号 | 文件 | 问题 | 修复内容 |
|------|------|------|----------|
| L1 | views.py:333 | AssetTypeViewSet.destroy 传错字段 | `asset_type.asset_type` → `asset_type.asset_type_code` |
| L2 | views.py:1618 | DamagedAssetViewSet.destroy kwargs 错误 | 使用 `self.get_object()` + FK traversal |
| L2b | views.py:1758,1797 | DamagedAssetViewSet approve/reject kwargs 错误 | 同上修复 |
| L3 | views.py:2091 | HardDiskSNViewSet select_related 错误 | `harddisksn_asset` → `asset_code` |
| L4 | views.py:976-983 | OutAssetViewSet select_related 错误 | `outasset_asset` → `outasset_code` |
| L5 | views.py:1306 | RecycleAssetViewSet select_related 错误 | `operator_employee` → `operator_jobcode` |
| L6 | views.py:1901-1908 | WasteAssetViewSet select_related 错误 | `waste_asset` → `waste_asset_code` |
| - | querysets.py 全文 | 所有 QuerySet select_related 错误 | 全部修正为正确 FK 字段名 |
| - | selectors/ 全文 | 所有 Selector filter/traversal 错误 | 全部修正为正确 FK 字段名 |
| - | services/ 全文 | 所有 Service 字段引用错误 | 全部修正为正确 FK 字段名 |

### P1 级（安全/逻辑风险）- 已全部修复

| 编号 | 文件 | 问题 | 修复内容 |
|------|------|------|----------|
| S1 | production.py | SECRET_KEY 变量名不一致 | 统一为 `SECRET_KEY` |
| S2 | base.py:209 | 生产 CORS 被强制清空 | 移除强制覆盖逻辑 |
| L7 | views.py:406 | Contract filterset_fields 拼写错误 | `contract_settledment_status` → `contract_settlment_status` |
| R1 | core/models.py | recordcode 碰撞无重试 | 添加 IntegrityError 重试机制 |

### P2 级（健壮性/配置）- 已全部修复

| 编号 | 文件 | 问题 | 修复内容 |
|------|------|------|----------|
| S3 | urls.py:65 | 健康检查泄露数据库错误 | 仅返回 `'unhealthy'` |
| S4 | views.py:156 | 注册无频率限制 | 添加 RegisterRateThrottle (5/min) |
| S5 | exception_handler.py | PermissionError 不被 DRF 捕获 | 添加 PermissionError 处理返回 403 |
| L8 | models.py:555 | Asset.save() 使用系统时区 | 改为 `timezone.now()` |
| L9 | models.py:1375 | AuditLog 使用系统时区 | 改为 `timezone.now()` |
| L10 | models.py:159 | Department 未过滤软删除父部门 | 添加 `is_deleted=False` |
| L11 | models.py:260 | Employee 默认部门值无效 | 移除 `default='Error'`，改 `SET_NULL` |
| L17 | unregisteredasset/views.py:78 | filterset_fields 字段名错误 | 修正为模型实际字段名 |

---

## 二、架构设计评价

### 优点

1. **分层清晰**: View → Serializer → Service → Selector → Model 单向依赖，职责分离良好
2. **软删除 + recordcode 模式**: 设计成熟，条件唯一约束处理得当
3. **审计日志**: AssetOperationLog 只读表设计，JSONField 存储变更前后数据
4. **状态机**: AssetFSM 管理资产状态流转，逻辑清晰
5. **批量操作**: BatchOperationMixin 统一处理批量创建/删除，单条失败不影响其他
6. **统一响应格式**: `{"code": 200, "msg": "", "data": {}}` 全局一致

### 待改进

1. **字段命名不一致**: FK 字段使用 `asset_type_code` 而非 `asset_type`，容易混淆
2. **合同字段拼写错误**: `contract_settlment_status` 已在数据库中，修改成本高
3. **Proxy 模型冗余**: 8 个 proxy 模型疑似无实际引用

---

## 三、剩余风险点

### 高风险

1. **并发安全**: 批量操作未使用 `select_for_update()`，高并发下可能出现数据不一致
2. **OperationLogService 字段**: 已修复 `operation_asset` 引用，但需确认所有调用路径正确

### 中风险

1. **RecycleAsset 碰撞重试**: `_generate_recycle_record_code()` 注释提到重试但未实现
2. **Pagination 内部属性修改**: `request._full_path` 直接修改可能在 ASGI 下不兼容

### 低风险

1. **Proxy 模型**: 8 个兼容性质的 proxy 模型增加维护负担
2. **CHOICES 重复定义**: `constants.py` 和 models 中各定义一次

---

## 四、优化建议

### 短期（1-2 周）

1. **为批量操作添加行锁**: 在 `batch_delete_execute` 中使用 `select_for_update()`
2. **统一时区处理**: 所有时间相关操作使用 `timezone.now()`，添加 lint 规则禁止 `datetime.now()`
3. **清理 Proxy 模型**: 确认是否有旧代码依赖，若无则删除

### 中期（1 个月）

1. **统一 CHOICES 数据源**: 在 models 中定义，constants.py 从 models 导入
2. **添加集成测试**: 覆盖核心业务流程（出库→回收→报废）
3. **API 限流优化**: 为不同接口配置独立的 throttle rate

### 长期

1. **字段命名规范化**: 考虑统一 FK 字段命名约定（如 `asset_type` 而非 `asset_type_code`）
2. **数据库迁移**: 修正 `contract_settlment_status` 拼写（需要数据迁移）
3. **性能监控**: 添加慢查询日志和 API 响应时间监控

---

## 五、文件修改清单

| 文件 | 修改类型 |
|------|----------|
| `apps/assetmanagement/views.py` | 修复 6 处字段名错误 + 3 处 kwargs 错误 |
| `apps/assetmanagement/querysets.py` | 重写所有 QuerySet 的 select_related |
| `apps/assetmanagement/selectors/base_selector.py` | 修复字段名引用 |
| `apps/assetmanagement/selectors/asset_selector.py` | 修复字段名引用 |
| `apps/assetmanagement/selectors/outasset_selector.py` | 修复字段名引用 |
| `apps/assetmanagement/services/asset_service.py` | 修复 whitelist 和字段引用 |
| `apps/assetmanagement/services/outasset_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/recycle_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/damaged_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/waste_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/harddisk_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/contract_service.py` | 修复字段引用 |
| `apps/assetmanagement/services/operation_log_service.py` | 移除无效字段引用 |
| `apps/unregisteredasset/views.py` | 修复 filterset_fields |
| `apps/usermanagement/models.py` | 修复 Department.clean() 和 Employee 默认值 |
| `config/settings/base.py` | 移除 CORS 强制覆盖 + 添加 register throttle |
| `config/settings/production.py` | 统一环境变量名 |
| `config/urls.py` | 移除健康检查错误泄露 |
| `core/models.py` | 添加 recordcode 碰撞重试 |
| `core/exception_handler.py` | 添加 PermissionError 处理 |
| `core/throttles.py` | 新增 RegisterRateThrottle |
| `apps/authusermanagement/views.py` | 注册接口添加 throttle |

---

*报告结束*
