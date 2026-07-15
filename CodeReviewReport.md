# 资产管理系统后端 - 代码审查报告

> 审查时间: 2026-06-25
> 审查范围: 逻辑性、安全性、健壮性、架构设计、性能优化
> 审查方式: 全量代码逐文件审查

---

## 一、安全性问题 (Security)

### S1. 生产环境配置环境变量命名不一致 [高]
**文件**: `config/settings/production.py:9` vs `config/settings/base.py:15`
**问题**: `base.py` 从 `SECRET_KEY` 读取密钥，`production.py` 从 `DJANGO_SECRET_KEY` 读取。若生产环境只设置了 `DJANGO_SECRET_KEY` 而未设置 `SECRET_KEY`，会回退到 base.py 的不安全默认值。
**建议**: 统一为同一个环境变量名，或在 production.py 中覆盖 `SECRET_KEY` 而非定义新变量。

### S2. 生产环境 CORS 配置逻辑缺陷 [高]
**文件**: `config/settings/base.py:209-210`
**问题**: `if not DEBUG and ALLOWED_HOSTS: CORS_ALLOWED_ORIGINS = []` — 当生产环境 `DEBUG=False` 且 `ALLOWED_HOSTS` 非空时，会清空 CORS 白名单，导致所有跨域请求被拒绝。如果前端和后端不同域，这会直接阻断前端访问。
**建议**: 生产环境应从环境变量读取 CORS 白名单，而非强制清空。

### S3. 健康检查接口泄露数据库错误信息 [中]
**文件**: `config/urls.py:64-65`
**问题**: `db_status = f'unhealthy: {str(e)}` 将异常详情返回给客户端，可能泄露数据库类型、连接信息。
**建议**: 生产环境仅返回 `'unhealthy'`，不暴露异常详情。

### S4. 用户注册无频率限制 [中]
**文件**: `apps/authusermanagement/views.py:154-156`
**问题**: `RegisterAPIView.throttle_classes = []` 注释说"使用全局 throttle 配置"，但全局配置 anon 为 `20/minute`，对于注册接口仍然过于宽松，容易被批量注册攻击。
**建议**: 为注册接口单独设置更严格的频率限制（如 `5/minute`）。

### S5. AssetOperationLog 只读保护不完整 [中]
**文件**: `apps/assetmanagement/models.py:1320-1324`
**问题**: `save()` 中检查 `if self.pk: raise PermissionError()`，但 `PermissionError` 是 Python 内置异常，不会被 DRF 的 `exception_handler` 捕获，会返回 500 而非 400。
**建议**: 改为抛出 `AppValidationError` 或在 `custom_exception_handler` 中捕获 `PermissionError`。

### S6. production.py 使用 os.getenv 而非 decouple [低]
**文件**: `config/settings/production.py:9,14,23-27,56`
**问题**: `base.py` 使用 `python-decouple` 的 `config()` 读取环境变量（支持 `.env` 文件），而 `production.py` 直接用 `os.getenv()`，两者行为不一致。
**建议**: 统一使用 `decouple.config()` 或 `os.environ`。

---

## 二、逻辑性问题 (Logic)

### L1. AssetTypeViewSet.destroy() 传递错误字段 [高]
**文件**: `apps/assetmanagement/views.py:333`
**问题**: `AssetTypeService.delete_asset_type(asset_type.asset_type)` — `AssetType` 模型没有 `asset_type` 字段，应该是 `asset_type.asset_type_code`。
**后果**: 调用时会抛 `AttributeError`，删除功能完全不可用。
**建议**: 改为 `AssetTypeService.delete_asset_type(asset_type.asset_type_code)`。

### L2. DamagedAssetViewSet.destroy() 使用错误的 kwargs [高]
**文件**: `apps/assetmanagement/views.py:1618`
**问题**: `damaged_asset = self.kwargs.get('damaged_asset')` — URL 参数名是 `pk`（ModelViewSet 默认），不是 `damaged_asset`，这会返回 `None`。
**后果**: 取消待报废申请功能不可用。
**建议**: 改为 `self.kwargs.get('pk')` 或 `self.kwargs[self.lookup_url_kwarg or self.lookup_field]`。

### L3. HardDiskSNViewSet queryset 字段名错误 [高]
**文件**: `apps/assetmanagement/views.py:2080`
**问题**: `queryset = HardDiskSN.objects.select_related('harddisksn_asset')` — `HardDiskSN` 模型的外键字段名是 `asset_code`，不是 `harddisksn_asset`。
**后果**: 查询时会抛 `FieldError`。
**建议**: 改为 `select_related('asset_code')`。

### L4. OutAssetViewSet queryset 字段名错误 [高]
**文件**: `apps/assetmanagement/views.py:976-983`
**问题**: `select_related` 中使用 `'outasset_asset'`，但 `OutAsset` 模型的外键字段名是 `outasset_code`。
**后果**: 查询时会抛 `FieldError`。
**建议**: 改为 `select_related('outasset_code', 'outasset_code__asset_type', ...)`。

### L5. RecycleAssetViewSet queryset 字段名错误 [高]
**文件**: `apps/assetmanagement/views.py:1306`
**问题**: `select_related` 中使用 `'operator_employee'`，但 `RecycleAsset` 模型的外键字段名是 `operator_jobcode`。
**建议**: 改为 `select_related('operator_jobcode')`（并确认 related_name 匹配）。

### L6. WasteAssetViewSet queryset 字段名错误 [高]
**文件**: `apps/assetmanagement/views.py:1896`
**问题**: `select_related` 中使用 `'waste_damaged_asset'`，但 `WasteAsset` 模型的外键字段名是 `source_damaged_asset`。
**建议**: 改为 `select_related('source_damaged_asset')`。

### L7. ContractViewSet filterset_fields 拼写错误 [中]
**文件**: `apps/assetmanagement/views.py:406`
**问题**: `filterset_fields = ['contract_type', 'contract_settledment_status']` — 字段名拼写错误（多了 `d`），应为 `contract_settlment_status`（模型字段本身的拼写是 `contract_settlment_status`，少了 `e`）。
**后果**: 按结算状态过滤功能不可用。

### L8. Asset.save() 使用 date.today() 而非 timezone.now() [中]
**文件**: `apps/assetmanagement/models.py:555-556`
**问题**: `today = date.today()` — 项目配置了 `USE_TZ=True` 和 `TIME_ZONE='Asia/Shanghai'`，但 `date.today()` 使用系统时区而非 Django 当前时区，可能导致跨时区部署时日期不一致。
**建议**: 改为 `timezone.now().date()`。

### L9. AssetOperationLog.get_recent_operations() 使用 datetime.now() [中]
**文件**: `apps/assetmanagement/models.py:1375`
**问题**: `start_time = datetime.now() - timedelta(days=days)` — 同上，应使用 `timezone.now()`。
**建议**: 改为 `timezone.now() - timedelta(days=days)`。

### L10. Department.clean() 未过滤软删除部门 [中]
**文件**: `apps/usermanagement/models.py:159-163`
**问题**: `Department.objects.filter(department_code=self.parent_code).exists()` — 未排除已软删除的部门，已删除的部门仍可作为父部门。
**建议**: 改为 `Department.objects.filter(department_code=self.parent_code, is_deleted=False).exists()`。

### L11. Employee.employee_department 默认值无效 [中]
**文件**: `apps/usermanagement/models.py:259`
**问题**: `default='Error'` — `employee_department` 是外键到 `Department`（通过 `recordcode`），默认值 `'Error'` 不是有效的 recordcode，创建员工时不指定部门会报数据库错误。
**建议**: 改为 `default=None` 并允许 `null=True`（已有）。

---

## 三、健壮性问题 (Robustness)

### R1. recordcode 碰撞风险 [中]
**文件**: `core/models.py:28`
**问题**: `uuid.uuid4().hex[:8]` 仅 8 位十六进制字符（32 bit 空间），在高并发写入时存在碰撞概率。虽然有 `unique=True` 约束，但碰撞会导致 `IntegrityError`，需要重试逻辑。
**建议**: 增加碰撞重试机制（如 `save()` 中捕获 `IntegrityError` 后重新生成）。

### R2. RecycleAsset 缺少碰撞重试 [低]
**文件**: `apps/assetmanagement/models.py:784-793`
**问题**: 注释提到"使用简单重试机制处理极端冲突情况"，但实际代码中没有重试逻辑。
**建议**: 添加 try/except 捕获 `IntegrityError` 并重试。

### R3. BaseModel.save() 的 update_fields 不完整 [低]
**文件**: `core/models.py:140`
**问题**: `self.save(using=using, update_fields=['is_deleted', 'updated_at'])` — 如果子类有其他需要更新的字段（如 `is_active`），此处不会触发。
**影响**: 当前无实际影响，但扩展性受限。

### R4. Pagination 直接修改 request 内部属性 [中]
**文件**: `core/pagination.py:56-60`
**问题**: `request._full_path = replace_query_param(...)` 和 `request.query_params[self.page_query_param] = '1'` — 直接修改 Django 内部属性，可能在 ASGI/异步场景下不兼容。
**建议**: 使用 DRF 提供的 `replace_query_param` 构造新的 URL，避免直接修改内部状态。

### R5. ResponseWrapperMixin 捕获过于宽泛的 Exception [低]
**文件**: `core/mixins.py:124,152,175,205,236`
**问题**: `except Exception as e:` 捕获所有异常，可能掩盖编程错误（如 `TypeError`, `NameError`）。
**建议**: 仅捕获预期的业务异常，让编程错误自然传播。

### R6. views.py 中 import 顺序不规范 [低]
**文件**: `apps/assetmanagement/views.py:1`
**问题**: `from core.exceptions import AppValidationError` 放在模块 docstring 之前，不符合 PEP 8。
**建议**: 移到标准 import 区域。

---

## 四、架构设计问题 (Architecture)

### A1. Proxy 模型增加维护负担 [低]
**文件**: `apps/assetmanagement/models.py:1054-1124`
**问题**: 定义了 8 个 proxy 模型（`Storagedatabasetable`, `Assettypedatabasetable` 等），注释说是"兼容旧代码"，但没有看到实际引用。
**建议**: 确认是否有旧代码依赖这些 proxy 模型，若无则删除。

### A2. Selector 层和 Service 层职责边界模糊 [低]
**问题**: 部分 Service 方法直接调用 ORM（如 `AssetTypeService.delete_asset_type`），而部分通过 Selector 查询。应统一使用 Selector 进行数据访问。
**建议**: 所有数据查询统一通过 Selector 层，Service 层仅包含业务逻辑。

### A3. constants.py 和 models.py 中 CHOICES 重复定义 [低]
**文件**: `core/constants.py` vs `apps/assetmanagement/models.py`
**问题**: `ASSET_STATUS_CHOICES` 在 `constants.py` 和 `Asset` 模型中各定义一次，需要手动保持同步。
**建议**: 模型中定义 CHOICES，`constants.py` 从模型导入，单一数据源。

---

## 五、性能问题 (Performance)

### P1. Asset 查询未使用 select_related [中]
**文件**: `apps/assetmanagement/views.py:615-619`
**问题**: `AssetViewSet.queryset` 定义了 `select_related`，但 `get_queryset()` 中 `Asset.objects.for_list().all()` 会覆盖 queryset 定义，导致 `select_related` 失效。
**建议**: 在 `for_list()` QuerySet 方法中内置 `select_related`。

### P2. 批量操作未使用 select_for_update [低]
**文件**: `core/batch_mixins.py:93-100`
**问题**: 批量操作逐条执行，但没有使用 `select_for_update()` 防止并发修改。
**影响**: 高并发场景下可能出现数据不一致。
**建议**: 在批量删除等关键操作中添加行锁。

---

## 六、代码质量问题 (Code Quality)

### Q1. 合同模型字段拼写错误 [低]
**文件**: `apps/assetmanagement/models.py:263,270`
**问题**: `contract_settlment_status` 和 `contract_settlment_price` 拼写为 `settlment`（少 `e`），正确应为 `settlement`。
**影响**: 已在数据库中创建列名，修改成本高。建议添加注释说明。

### Q2. 部分 ViewSet 的 filterset_fields 引用了不存在的字段 [中]
**文件**: `apps/unregisteredasset/views.py:78`
**问题**: `filterset_fields = [..., 'discovery_person', 'related_asset']` — 模型字段名是 `discovery_person_jobcode` 和 `related_asset_code`。
**建议**: 改为正确的字段名。

### Q3. 废弃的注释代码未清理 [低]
**文件**: `core/pagination.py:126-150`, `apps/unregisteredasset/views.py:113-173`
**问题**: 大量注释掉的代码块，降低可读性。
**建议**: 删除已确认不需要的注释代码。

---

## 七、优化建议汇总

| 优先级 | 编号 | 类别 | 问题摘要 | 建议 |
|--------|------|------|----------|------|
| **P0** | L1 | 逻辑 | AssetTypeViewSet.destroy 传错字段 | 改为 `asset_type_code` |
| **P0** | L2 | 逻辑 | DamagedAssetViewSet.destroy kwargs 错误 | 改为 `pk` |
| **P0** | L3-L6 | 逻辑 | 多个 ViewSet 的 select_related 字段名错误 | 核对模型字段名修正 |
| **P1** | S1 | 安全 | 生产环境 SECRET_KEY 变量名不一致 | 统一变量名 |
| **P1** | S2 | 安全 | 生产环境 CORS 被强制清空 | 从环境变量读取 |
| **P1** | L7 | 逻辑 | Contract filterset_fields 拼写错误 | 修正字段名 |
| **P1** | R1 | 健壮 | recordcode 碰撞无重试 | 添加重试机制 |
| **P2** | S3 | 安全 | 健康检查泄露数据库错误 | 仅返回状态 |
| **P2** | S4 | 安全 | 注册接口无频率限制 | 添加独立 throttle |
| **P2** | S5 | 安全 | AssetOperationLog 保护异常类型错误 | 改为 DRF 异常 |
| **P2** | L8-L9 | 逻辑 | 使用系统时区而非 Django 时区 | 统一用 timezone.now() |
| **P2** | L10 | 逻辑 | Department 未过滤软删除父部门 | 添加 is_deleted=False |
| **P2** | L11 | 逻辑 | Employee 默认部门值无效 | 改为 None |
| **P2** | P1 | 性能 | Asset 列表查询 select_related 失效 | 在 QuerySet 中内置 |
| **P3** | A1 | 架构 | 无用 Proxy 模型 | 确认后删除 |
| **P3** | A3 | 架构 | CHOICES 重复定义 | 单一数据源 |
| **P3** | Q1 | 质量 | 合同字段拼写错误 | 添加注释说明 |
| **P3** | Q3 | 质量 | 注释代码未清理 | 删除 |

---

## 八、审查结论

### 整体评价

项目架构设计合理，分层清晰（View → Serializer → Service → Selector → Model），软删除 + recordcode 模式设计较好，审计日志和状态机的实现也较为完善。

### 主要风险

1. **L1-L6 共 6 处字段名错误**会导致多个核心功能（删除、查询）运行时报错，必须立即修复
2. **S1-S2 生产配置问题**可能导致部署后安全漏洞或功能异常
3. **R1 recordcode 碰撞**在高并发场景下可能引发数据完整性问题

### 建议修复顺序

1. **立即修复**: L1-L6（字段名错误，功能不可用）
2. **尽快修复**: S1-S2, L7-L11（安全和逻辑问题）
3. **计划修复**: R1-R6, P1-P2（健壮性和性能）
4. **低优先级**: A1-A3, Q1-Q3（架构和代码质量）

---

*报告结束*
