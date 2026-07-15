# 资产管理系统 — 全字段/关系/API 详细文档

> 共 **14 个模型** | **约 55 个序列化器** | **14 个 ViewSet + 4 个 APIView** | **约 158 个 API 端点**

---

## 目录

- [一、Models 字段与关系](#一models-字段与关系)
- [二、Serializers 字段详情](#二serializers-字段详情)
- [三、ViewSets API 端点详情](#三viewsets-api-端点详情)

---

## 一、Models 字段与关系

### 继承关系总览

```
models.Model
  └── TimestampModel (abstract)
        └── BaseModel (abstract)
              ├── Storage
              ├── AssetType
              ├── Contract
              ├── Asset
              ├── OutAsset
              ├── RecycleAsset
              ├── DamagedAsset
              ├── WasteAsset
              ├── HardDiskSN
              ├── UnregisteredAsset
              ├── Department
              └── Employee

models.Model
  └── AssetOperationLog（不继承BaseModel，只读表）

AbstractBaseUser + PermissionsMixin
  └── AuthUser
```
models.Model
  └── TimestampModel (abstract)
        └── BaseModel (abstract)
              ├── Storage
              ├── AssetType
              ├── Contract
              ├── Asset
              ├── OutAsset
              ├── RecycleAsset
              ├── DamagedAsset
              ├── WasteAsset
              ├── HardDiskSN
              └── UnregisteredAsset

models.Model
  ├── Department（不继承BaseModel，手动实现软删除）
  ├── Employee（不继承BaseModel，手动实现软删除）
  └── AssetOperationLog（不继承BaseModel，只读表）

AbstractBaseUser + PermissionsMixin
  └── AuthUser
```

### BaseModel 继承字段

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `created_at` | `DateTimeField` | `auto_now_add=True` | 记录创建时间 |
| `updated_at` | `DateTimeField` | `auto_now=True` | 最后修改时间 |
| `is_active` | `BooleanField` | `default=True` | 是否启用 |
| `is_deleted` | `BooleanField` | `default=False` | 软删除标记 |

---

### 1. Storage（仓库管理）

**db_table**: `am_storage` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `storage_code` | CharField | `max_length=20` | 仓库唯一编码 |
| `storage_name` | CharField | `max_length=100` | 仓库名称 |
| `storage_address` | CharField | `max_length=200` | 仓库地址 |
| `storage_type` | CharField | `max_length=50, choices=STORAGE_TYPE_CHOICES, default="newasset", blank=True, null=True` | 仓库类型 |
| `storage_description` | TextField | `blank=True, null=True` | 仓库描述 |

**Choices**: `STORAGE_TYPE_CHOICES = [("newasset", "新货仓库"), ("recycle", "回收仓库"), ("damaged", "待报废仓库")]`

**Constraints**: `UniqueConstraint(fields=["storage_code"], condition=Q(is_deleted=False))`, `UniqueConstraint(fields=["storage_name"], condition=Q(is_deleted=False))`

---

### 2. AssetType（资产类型管理）

**db_table**: `am_asset_type` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `asset_type_code` | CharField | `max_length=20` | 资产类型唯一编码 |
| `asset_type_secondary` | CharField | `max_length=100` | 资产二级分类名称 |
| `asset_type_primary` | CharField | `max_length=100` | 资产一级分类名称 |
| `asset_type_category` | CharField | `max_length=50, choices=ASSET_TYPE_CATEGORY_CHOICES, default="hardware", blank=True, null=True` | 分类类型 |
| `asset_type_description` | TextField | `blank=True, null=True` | 资产分类描述 |

**Choices**: `ASSET_TYPE_CATEGORY_CHOICES = [("hardware", "硬件"), ("software", "软件"), ("lowvalue", "低值易耗"), ("other", "其他")]`

---

### 3. Contract（合同管理）

**db_table**: `am_contract` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `contract_code` | CharField | `max_length=20` | 合同唯一编码 |
| `contract_name` | CharField | `max_length=100` | 合同名称 |
| `contract_type` | CharField | `max_length=30, choices=CONTRACT_TYPE_CHOICES, default="tender_procurement", blank=True, null=True` | 合同类型 |
| `contract_price` | DecimalField | `max_digits=10, decimal_places=2` | 合同总金额（元） |
| `contract_supplier` | CharField | `max_length=100` | 合同供应商 |
| `contract_signing_date` | DateField | | 合同签署日期 |
| `contract_warranty_period` | IntegerField | `default=0` | 保修期限（年） |
| `contract_preliminary_acceptance_date` | DateField | `blank=True, null=True` | 初步验收日期 |
| `contract_final_acceptance_date` | DateField | `blank=True, null=True` | 最终验收日期 |
| `contract_settledment_status` | CharField | `max_length=20, choices=CONTRACT_SETTLEMENT_CHOICES, default="pending"` | 结算状态 |
| `contract_settledment_price` | DecimalField | `max_digits=10, decimal_places=2, blank=True, null=True` | 实际结算金额 |
| `contract_paid_count_number` | IntegerField | `default=0` | 已付款次数 |
| `contract_paid_price` | DecimalField | `max_digits=10, decimal_places=2, default=0.00, blank=True, null=True` | 累计已付金额 |
| `contract_paid_record` | TextField | `blank=True, null=True` | 付款记录 |

**Choices**: `CONTRACT_TYPE_CHOICES = [("tender_procurement", "招标采购合同"), ("service", "服务合同"), ("information_construction", "信息化建设合同"), ("direct_procurement", "直接采购合同")]`

**Choices**: `CONTRACT_SETTLEMENT_CHOICES = [("pending", "待结算"), ("settled", "已结算")]`

---

### 4. Asset（资产管理 — 核心模型）

**db_table**: `am_asset` | **继承**: `BaseModel` | **ordering**: `["-created_at"]`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, default=generate_recordcode, blank=True, null=True` | 系统自动生成的入库记录编码 |
| `asset_code` | CharField | `max_length=64, unique=True, editable=False` | 资产唯一编码，不可修改 |
| `asset_name` | CharField | `max_length=100` | 资产名称 |
| `asset_purchase_price` | DecimalField | `max_digits=10, decimal_places=2` | 采购单价（元） |
| `asset_purchase_number` | IntegerField | `default=1` | 采购数量 |
| `asset_unit` | CharField | `max_length=50, blank=True, null=True` | 计量单位 |
| `asset_brand` | CharField | `max_length=100, blank=True, null=True` | 品牌 |
| `asset_specification` | CharField | `max_length=100, blank=True, null=True` | 规格型号 |
| `asset_type` | **ForeignKey** | → AssetType, `to_field="recordcode"`, `on_delete=DO_NOTHING`, `related_name="assets"` | 关联资产类型 |
| `asset_contract` | **ForeignKey** | → Contract, `to_field="recordcode"`, `on_delete=SET_NULL`, `related_name="assets"`, `null=True, blank=True` | 关联合同 |
| `asset_purchase_date` | DateField | | 采购日期 |
| `asset_warranty_period` | IntegerField | `default=0, blank=True, null=True` | 保修期限（年） |
| `asset_entry_date` | DateField | | 入库日期 |
| `asset_storage` | **ForeignKey** | → Storage, `to_field="recordcode"`, `on_delete=DO_NOTHING`, `related_name="assets"`, `blank=True, null=True` | 所在仓库 |
| `asset_entry_person` | **ForeignKey** | → Employee, `to_field="recordcode"`, `on_delete=SET_NULL`, `related_name="assets_entry"`, `blank=True, null=True` | 入库人 |
| `asset_applicant` | **ForeignKey** | → Employee, `to_field="recordcode"`, `on_delete=DO_NOTHING`, `related_name="assets_applicant"`, `null=True, blank=True` | 申请人 |
| `asset_manager` | **ForeignKey** | → Employee, `to_field="recordcode"`, `on_delete=DO_NOTHING`, `related_name="assets_manager"`, `null=True, blank=True` | 保管人 |
| `asset_using_location` | CharField | `max_length=100, blank=True, null=True` | 使用地点 |
| `asset_current_status` | CharField | `max_length=20, choices=ASSET_STATUS_CHOICES, default="in_store", db_index=True` | 资产状态 |
| `asset_description` | TextField | `blank=True, null=True` | 资产描述 |

**Choices**: `ASSET_STATUS_CHOICES = [("in_store", "在库"), ("recycled_pending", "已回收待发放"), ("in_use", "在用"), ("damaged", "待报废"), ("scrapped", "已报废")]`

**外键关系（6个）**:

| 外键字段 | 关联模型 | to_field | related_name | on_delete |
|----------|---------|----------|-------------|-----------|
| `asset_type` | AssetType | recordcode | assets | DO_NOTHING |
| `asset_contract` | Contract | recordcode | assets | SET_NULL |
| `asset_storage` | Storage | recordcode | assets | DO_NOTHING |
| `asset_entry_person` | Employee | recordcode | assets_entry | SET_NULL |
| `asset_applicant` | Employee | recordcode | assets_applicant | DO_NOTHING |
| `asset_manager` | Employee | recordcode | assets_manager | DO_NOTHING |

---

### 5. OutAsset（出库资产管理）

**db_table**: `am_out_asset` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=36, unique=True, default=generate_outassetrecordcode` | 出库记录唯一标识 |
| `outasset_asset` | **ForeignKey** | → Asset, `to_field="recordcode"`, `related_name="out_assets"`, `on_delete=SET_NULL`, `null=True, blank=True` | 关联资产 |
| `outasset_number` | IntegerField | `default=1` | 出库数量 |
| `outasset_previous_status` | CharField | `max_length=50, choices=[('in_store','在库'),('recycled_pending','已回收待发放')], default='in_store', null=True, blank=True` | 出库前状态 |
| `return_date` | DateField | `blank=True, null=True` | 归还日期 |
| `outasset_date` | DateField | `default=timezone.now` | 出库日期 |
| `outasset_type` | CharField | `max_length=50, choices=OUTASSET_TYPE_CHOICES, default="receive", blank=True, null=True` | 出库类型 |
| `outasset_description` | TextField | `blank=True, null=True` | 出库说明 |

**Choices**: `OUTASSET_TYPE_CHOICES = [("receive", "领用"), ("borrow", "借用")]`

---

### 6. RecycleAsset（回收资产管理）

**db_table**: `am_recycle_asset` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 回收记录唯一编码（继承自BaseModel） |
| `recycle_outasset` | **OneToOneField** | → OutAsset, `to_field="recordcode"`, `on_delete=CASCADE`, `related_name="recycle_record"` | 关联出库记录 |
| `recycle_asset_code` | **ForeignKey** | → Asset, `to_field="recordcode"`, `related_name="recycle_assets"`, `on_delete=PROTECT` | 回收的资产 |
| `recycle_asset_number` | IntegerField | `default=1` | 回收数量 |
| `operator_employee` | **ForeignKey** | → Employee, `to_field="recordcode"`, `related_name="recycle_assets_operator"`, `on_delete=SET_NULL`, `null=True, blank=True` | 操作人 |
| `recycle_type` | CharField | `max_length=50, blank=True, null=True` | 回收类型/原因 |
| `recycle_asset_date` | DateField | | 回收日期 |
| `recycle_asset_description` | TextField | `blank=True, null=True` | 回收说明 |

---

### 7. DamagedAsset（待报废资产管理）

**db_table**: `am_damaged_asset` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `damaged_asset` | **OneToOneField** | → Asset, `to_field="recordcode"`, `related_name="damaged_asset"`, `on_delete=SET_NULL`, `null=True, blank=True` | 待报废的资产 |
| `damaged_asset_number` | IntegerField | `default=1` | 待报废数量 |
| `damaged_date` | DateField | `default=timezone.now, blank=True, null=True` | 申请日期 |
| `approval_status` | CharField | `max_length=20, default="pending", choices=[("pending","待审批"),("approved","已批准"),("rejected","已拒绝")]` | 审批状态 |
| `approver` | **ForeignKey** | → Employee, `to_field="recordcode"`, `related_name="damaged_assets_approver"`, `on_delete=SET_NULL`, `null=True, blank=True` | 审批人 |
| `damaged_asset_description` | TextField | `blank=True, null=True` | 报废原因 |

---

### 8. WasteAsset（已报废资产管理）

**db_table**: `am_waste_asset` | **继承**: `BaseModel`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `waste_asset` | **OneToOneField** | → Asset, `to_field="recordcode"`, `related_name="waste_asset"`, `on_delete=PROTECT` | 已报废的资产 |
| `waste_damaged_asset` | **OneToOneField** | → DamagedAsset, `to_field="recordcode"`, `related_name="waste_asset_record"`, `on_delete=PROTECT`, `null=True, blank=True` | 关联的待报废记录 |
| `waste_asset_number` | IntegerField | `default=1` | 报废数量 |
| `waste_asset_date` | DateField | | 报废日期 |
| `waste_asset_description` | TextField | `blank=True, null=True` | 报废说明 |

---

### 9. HardDiskSN（硬盘序列号管理）

**db_table**: `am_hard_disk_sn` | **继承**: `BaseModel` | **RECORDCODE_PREFIX**: `HDSN`

| 字段名 | 字段类型 | 参数 | 说明 |
|:---|:---|:---|:---|
| `recordcode` | CharField | `max_length=64, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `asset_recordcode` | **ForeignKey** | → Asset, `to_field="recordcode"`, `related_name="harddisk_sns"`, `on_delete=PROTECT` | 关联资产 |
| `harddisk_sn_code` | CharField | `max_length=100` | 硬盘序列号 |
| `harddisk_type` | CharField | `max_length=20, choices=HARDDISK_TYPE_CHOICES, default="HDD", blank=True` | 硬盘类型 |
| `harddisk_capacity` | CharField | `max_length=20, default="", blank=True` | 硬盘容量 |
| `harddisk_status` | CharField | `max_length=20, choices=HARDDISK_STATUS_CHOICES, default="active"` | 硬盘状态 |
| `harddisk_description` | TextField | `blank=True, default=""` | 补充说明 |
| `version` | IntegerField | `default=1` | 乐观锁版本号 |

**Choices**:
- `HARDDISK_TYPE_CHOICES = [("HDD", "HDD"), ("SSD", "SSD"), ("NVMe", "NVMe"), ("Other", "其他")]`
- `HARDDISK_STATUS_CHOICES = [("active", "正常"), ("repair", "维修"), ("scrap", "报废"), ("lost", "丢失"), ("damaged", "损坏")]`

**约束**: `UNIQUE(harddisk_sn_code)` where `is_deleted=False`

---

### 10. AssetOperationLog（资产操作记录 — 只读表）

**db_table**: `am_asset_operation_log` | **继承**: `models.Model`（不继承BaseModel） | **ordering**: `["-operation_time"]`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `asset_code` | CharField | `max_length=64, db_index=True` | 资产编码（冗余存储，用于查询性能优化） |
| `operation_type` | CharField | `max_length=20, choices=OPERATION_TYPE_CHOICES, db_index=True` | 操作类型 |
| `logging_id` | CharField | `max_length=50, unique=True, db_index=True, blank=True` | 日志唯一标识 |
| `operation_time` | DateTimeField | `auto_now_add=True, db_index=True` | 操作时间 |
| `operator_jobcode` | CharField | `max_length=20, blank=True, null=True` | 操作人工号 |
| `operator_name` | CharField | `max_length=100, blank=True, null=True` | 操作人姓名 |
| `before_data` | JSONField | `blank=True, null=True` | 操作前数据 |
| `after_data` | JSONField | `blank=True, null=True` | 操作后数据 |
| `description` | TextField | | 操作描述 |
| `related_record_code` | CharField | `max_length=50, blank=True, null=True` | 关联记录编码 |
| `related_record_type` | CharField | `max_length=20, blank=True, null=True` | 关联记录类型 |
| `ip_address` | GenericIPAddressField | `blank=True, null=True` | 操作IP |

**Choices**: `OPERATION_TYPE_CHOICES = [("create","创建"),("update","更新"),("delete","删除"),("out","出库"),("recycle","回收"),("damaged","待报废"),("waste","已报废"),("approve","审批"),("transfer","转移"),("state_change","状态变更")]`

**特殊约束**: `save()` 中若已存在记录则抛 `PermissionError` 阻止更新；`delete()` 直接抛 `PermissionError` 阻止删除。

---

### 11. AuditLog（通用审计日志 — 只读表）

**db_table**: `core_audit_log` | **继承**: `models.Model` | **ordering**: `["-operation_time"]`

用于记录非资产操作的审计日志（部门、员工、用户、未登记资产等）。

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `record_code` | CharField | `max_length=64, db_index=True` | 被操作记录的唯一编码 |
| `app_label` | CharField | `max_length=50, db_index=True` | 操作所属应用 |
| `operation_type` | CharField | `max_length=20, choices=OPERATION_TYPE_CHOICES, db_index=True` | 操作类型 |
| `logging_id` | CharField | `max_length=50, unique=True, db_index=True, blank=True` | 日志唯一标识 |
| `operation_time` | DateTimeField | `auto_now_add=True, db_index=True` | 操作时间 |
| `operator_jobcode` | CharField | `max_length=20, blank=True, null=True` | 操作人工号 |
| `operator_name` | CharField | `max_length=100, blank=True, null=True` | 操作人姓名 |
| `before_data` | JSONField | `blank=True, null=True` | 变更前数据 |
| `after_data` | JSONField | `blank=True, null=True` | 变更后数据 |
| `description` | TextField | | 操作描述 |
| `ip_address` | GenericIPAddressField | `blank=True, null=True` | 操作IP |

**Choices**: `OPERATION_TYPE_CHOICES = [("create","创建"),("update","更新"),("delete","删除"),("approve","审批"),("login","登录"),("logout","登出"),("permission_change","权限变更"),("state_change","状态变更")]`

---

### 11. Department（部门管理）

**db_table**: `department_database_table` | **继承**: `BaseModel` | **ordering**: `['sort_order', 'department_code']`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `department_code` | CharField | `max_length=20` | 部门唯一编码 |
| `department_name` | CharField | `max_length=100` | 部门名称 |
| `department_information` | CharField | `max_length=20` | 部门信息负责人 |
| `parent_code` | CharField | `max_length=20, null=True, blank=True` | 上级部门编码 |
| `level` | IntegerField | `default=0` | 部门层级 |
| `sort_order` | IntegerField | `default=0` | 排序顺序 |
| `is_active` | BooleanField | `default=True` | 是否启用 |
| `is_deleted` | BooleanField | `default=False` | 软删除标记 |
| `created_at` | DateTimeField | `auto_now_add=True` | 创建时间 |
| `updated_at` | DateTimeField | `auto_now=True` | 更新时间 |

---

### 12. Employee（员工管理）

**db_table**: `user_database_table` | **继承**: `BaseModel` | **ordering**: `['sort_order', 'employee_jobcode']`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `employee_jobcode` | CharField | `max_length=20` | 员工工号 |
| `employee_name` | CharField | `max_length=100` | 员工名称 |
| `employee_status` | CharField | `max_length=10, choices=EMPLOYEE_STATUS_CHOICES, default='active'` | 员工状态 |
| `employee_department` | **ForeignKey** | → Department, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True` | 所属部门 |
| `employee_phone` | CharField | `max_length=15` | 员工电话 |
| `employee_location` | CharField | `max_length=100` | 员工位置 |
| `employee_description` | TextField | `blank=True, null=True` | 员工描述 |
| `sort_order` | IntegerField | `default=0` | 排序顺序 |
| `is_active` | BooleanField | `default=True` | 是否启用 |
| `is_deleted` | BooleanField | `default=False` | 软删除标记 |
| `created_at` | DateTimeField | `auto_now_add=True` | 创建时间 |
| `updated_at` | DateTimeField | `auto_now=True` | 更新时间 |

**Choices**: `EMPLOYEE_STATUS_CHOICES = [('active', '在职员工'), ('left', '离职员工'), ('retirement', '退休员工')]`

---

### 13. UnregisteredAsset（未登记资产管理）

**db_table**: `am_unregistered_asset` | **继承**: `BaseModel` | **ordering**: `['-created_at']`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `unregistered_code` | CharField | `max_length=32, unique=True` | 未登记资产编码 |
| `scenario_type` | CharField | `max_length=20, choices=ScenarioType.choices` | 场景类型 |
| `discovery_date` | DateField | | 发现日期 |
| `discovery_location` | CharField | `max_length=200` | 发现地点 |
| `discovery_person` | **ForeignKey** | → Employee, `to_field='recordcode'`, `on_delete=DO_NOTHING`, `related_name='unregistered_discovered'` | 发现人 |
| `asset_name` | CharField | `max_length=100` | 资产名称 |
| `asset_brand` | CharField | `max_length=100, blank=True, null=True` | 资产品牌 |
| `asset_specification` | CharField | `max_length=100, blank=True, null=True` | 资产规格 |
| `unregistered_asset_type` | **ForeignKey** | → AssetType, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_assets'` | 资产类型 |
| `estimated_value` | DecimalField | `max_digits=10, decimal_places=2, blank=True, null=True` | 预估价值 |
| `related_asset` | **ForeignKey** | → Asset, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_records'` | 关联资产 |
| `handle_type` | CharField | `max_length=30, choices=HandleType.choices, null=True, blank=True` | 处理方式 |
| `unregistered_asset_storage` | **ForeignKey** | → Storage, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_targets'` | 目标仓库 |
| `handle_description` | TextField | `blank=True, null=True` | 处理说明 |
| `approval_status` | CharField | `max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING` | 审批状态 |
| `approver` | **ForeignKey** | → Employee, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_approved'` | 审批人 |
| `approval_date` | DateField | `blank=True, null=True` | 审批日期 |
| `approval_remark` | TextField | `blank=True, null=True` | 审批备注 |
| `result_asset` | **ForeignKey** | → Asset, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_result_assets'` | 结果资产 |
| `result_recycle_asset` | **ForeignKey** | → RecycleAsset, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_recycles'` | 结果回收记录 |
| `result_damaged_asset` | **ForeignKey** | → DamagedAsset, `to_field='recordcode'`, `on_delete=SET_NULL`, `null=True, blank=True`, `related_name='unregistered_damages'` | 结果待报废记录 |
| `attachments` | JSONField | `default=list, blank=True` | 附件列表 |

---

### 14. AuthUser（认证与用户管理）

**db_table**: `auth_user_management_table` | **继承**: `AbstractBaseUser, PermissionsMixin`（不继承BaseModel） | **USERNAME_FIELD**: `auth_username`

| 字段名 | 字段类型 | 参数 | 说明 |
|--------|---------|------|------|
| `auth_id` | AutoField | `primary_key=True` | 用户唯一标识 |
| `recordcode` | CharField | `max_length=32, unique=True, blank=True, null=True` | 后端生成的全局唯一编码 |
| `auth_username` | CharField | `max_length=150` | 用户登录名 |
| `email` | EmailField | `max_length=254, blank=True, null=True` | 邮箱 |
| `auth_is_active` | BooleanField | `default=True` | 账户是否激活 |
| `auth_is_staff` | BooleanField | `default=False` | 是否后台管理员 |
| `auth_date_create` | DateTimeField | `auto_now_add=True` | 创建时间 |
| `auth_date_update` | DateTimeField | `auto_now=True` | 更新时间 |
| `auth_phone` | CharField | `max_length=15` | 联系电话 |
| `last_login` | DateTimeField | `blank=True, null=True` | 最后登录时间 |

---

### 外键关系汇总

| 来源模型 | 外键字段 | 目标模型 | to_field | on_delete |
|----------|---------|---------|----------|-----------|
| Asset | asset_type | AssetType | recordcode | DO_NOTHING |
| Asset | asset_contract | Contract | recordcode | SET_NULL |
| Asset | asset_storage | Storage | recordcode | DO_NOTHING |
| Asset | asset_entry_person | Employee | recordcode | SET_NULL |
| Asset | asset_applicant | Employee | recordcode | DO_NOTHING |
| Asset | asset_manager | Employee | recordcode | DO_NOTHING |
| OutAsset | outasset_asset | Asset | recordcode | SET_NULL |
| RecycleAsset | recycle_outasset | OutAsset | recordcode | CASCADE (OneToOne) |
| RecycleAsset | recycle_asset_code | Asset | recordcode | PROTECT |
| RecycleAsset | operator_employee | Employee | recordcode | SET_NULL |
| DamagedAsset | damaged_asset | Asset | recordcode | SET_NULL (OneToOne) |
| DamagedAsset | approver | Employee | recordcode | SET_NULL |
| WasteAsset | waste_asset | Asset | recordcode | DO_NOTHING (OneToOne) |
| WasteAsset | waste_damaged_asset | DamagedAsset | id | DO_NOTHING (OneToOne) |
| HardDiskSN | asset_recordcode | Asset | recordcode | PROTECT |
| Employee | employee_department | Department | recordcode | SET_NULL |
| UnregisteredAsset | discovery_person | Employee | recordcode | DO_NOTHING |
| UnregisteredAsset | unregistered_asset_type | AssetType | recordcode | SET_NULL |
| UnregisteredAsset | related_asset | Asset | recordcode | SET_NULL |
| UnregisteredAsset | unregistered_asset_storage | Storage | recordcode | SET_NULL |
| UnregisteredAsset | approver | Employee | recordcode | SET_NULL |
| UnregisteredAsset | result_asset | Asset | recordcode | SET_NULL |
| UnregisteredAsset | result_recycle_asset | RecycleAsset | pk | SET_NULL |
| UnregisteredAsset | result_damaged_asset | DamagedAsset | pk | SET_NULL |

---

## 二、Serializers 字段详情

### assetmanagement 模块序列化器

---

#### StorageSerializer
- **模型**: Storage | **继承**: ModelSerializer
- **字段**: storage_code, storage_name, storage_address, storage_type, storage_description, is_active

#### AssetTypeSerializer
- **模型**: AssetType | **继承**: ModelSerializer
- **字段**: asset_type_code, asset_type_secondary, asset_type_primary, asset_type_category, asset_type_description, is_active

#### ContractSerializer
- **模型**: Contract | **继承**: ModelSerializer
- **字段**: contract_code, contract_name, contract_type, contract_price, contract_supplier, contract_signing_date, contract_warranty_period, contract_settledment_status, contract_settledment_price, contract_paid_count_number, contract_paid_price, contract_paid_record, is_active

#### ContractDetailSerializer
- **模型**: Contract | **继承**: ModelSerializer
- **字段**: 与 ContractSerializer 完全相同

#### AssetSerializer
- **模型**: Asset | **继承**: ModelSerializer
- **字段**: asset_code, asset_name, asset_brand, asset_unit, asset_specification, asset_purchase_price, asset_purchase_date, asset_warranty_period, asset_current_status, asset_description, asset_using_location, asset_entry_date, asset_type(FK), asset_contract(FK), asset_storage(FK), asset_entry_person(FK), asset_applicant(FK), asset_manager(FK), is_active
- **额外只读字段**: return_asset_type_code, return_asset_type_name, return_asset_category, return_contract_code, return_contract_name, return_storage_code, return_storage_name, entry_person_name, applicant_name, manager_name

#### AssetDetailSerializer
- **模型**: Asset | **继承**: ModelSerializer
- **字段**: 同 AssetSerializer，但关联字段使用嵌套序列化器
- **嵌套序列化器**: asset_type→AssetTypeSerializer, asset_contract→ContractSerializer, asset_storage→StorageSerializer, asset_entry_person→EmployeeSerializer, asset_applicant→EmployeeSerializer, asset_manager→EmployeeSerializer, harddisk_sns→HardDiskSNSimpleSerializer(many)

#### AssetCreateSerializer
- **模型**: Asset | **继承**: ModelSerializer
- **排除字段**: ["recordcode"]
- **SlugRelatedField**: asset_type(slug_field="asset_type_code"), asset_contract(slug_field="contract_code"), asset_storage(slug_field="storage_code"), asset_entry_person(slug_field="employee_jobcode"), asset_applicant(slug_field="employee_jobcode"), asset_manager(slug_field="employee_jobcode")

#### AssetBatchItemSerializer
- **继承**: Serializer
- **字段**: row_number, asset_name, asset_type(SlugRelated), asset_purchase_price, asset_purchase_date, asset_entry_date, asset_storage(SlugRelated), asset_contract(SlugRelated), asset_purchase_number, asset_department_code(SlugRelated), asset_employee_jobcode(SlugRelated), asset_specification, asset_brand, asset_unit, asset_remark

#### AssetBatchCreateSerializer
- **继承**: Serializer
- **字段**: items = AssetBatchItemSerializer(many=True)
- **验证**: 最大100条，资产名称不重复

#### AssetBatchDeleteSerializer
- **继承**: Serializer
- **字段**: ids = ListField(child=CharField())
- **验证**: 最大100条，无重复

#### CombineSearchSerializer
- **继承**: Serializer
- **字段**: asset_name(模糊), asset_specification(模糊), asset_brand(模糊), asset_current_status(精确), asset_type(精确), asset_type_category(精确), asset_storage(精确), asset_contract(精确)

#### OutAssetSerializer
- **模型**: OutAsset | **继承**: ModelSerializer
- **字段**: id(read_only), recordcode(read_only), outasset_asset(SlugRelated, slug_field="asset_code"), outasset_number, outasset_date, outasset_type, outasset_description
- **额外只读字段**: outasset_current_status, applicant_jobcode, manager_jobcode, outasset_contract_code, outasset_name, outasset_specification, using_location, outasset_applicant_name, outasset_manager_name

#### OutAssetDetailSerializer
- **模型**: OutAsset | **继承**: ModelSerializer
- **所有字段**: read_only
- **嵌套序列化器**: outasset_applicant→EmployeeSerializer, outasset_manager→EmployeeSerializer, outasset_contract→ContractSerializer

#### RecycleAssetSerializer
- **模型**: RecycleAsset | **继承**: ModelSerializer
- **字段**: id, recordcode, recycle_asset_date, recycle_asset_code(FK), recycle_outasset(SlugRelated, slug_field="recordcode"), recycle_asset_number, recycle_type, is_active
- **额外只读字段**: recycle_asset_name, storage_name, storage_code, using_person_name, recycle_person_name, using_person_jobcode, recycle_person_jobcode
- **write_only字段**: recycle_asset_recycle_person_jobcode(SlugRelated), recycle_asset_storage(SlugRelated)

#### DamagedAssetSerializer
- **模型**: DamagedAsset | **继承**: ModelSerializer
- **字段**: id, recordcode, damaged_asset(OneToOne), approval_status, approver(FK), damaged_date, damaged_asset_number, damaged_asset_description, is_active
- **额外只读字段**: damaged_asset_name, damaged_asset_contract_code, damaged_asset_contract_name, damaged_asset_storage_code, damaged_asset_storage_name, damaged_asset_specification

#### WasteAssetSerializer
- **模型**: WasteAsset | **继承**: ModelSerializer
- **字段**: id, recordcode, waste_asset(OneToOne), waste_asset_date, waste_asset_description, is_active
- **额外只读字段**: asset_code, asset_name, contract_name, waste_asset_contract_code, waste_asset_specification

#### HardDiskSNSimpleSerializer
- **模型**: HardDiskSN | **继承**: ModelSerializer
- **字段**: id, harddisk_sn_code, harddisk_no, harddisk_type, harddisk_status, harddisk_sn_description

#### HardDiskSNSerializer
- **模型**: HardDiskSN | **继承**: ModelSerializer
- **字段**: fields = '__all__'
- **额外声明字段**: asset_name(source='harddisksn_asset.asset_name', read_only)

#### HardDiskSNBatchSerializer
- **继承**: Serializer
- **字段**: asset_code(CharField), disks = DiskItemSerializer(many=True)
- **验证**: 资产编码存在性，硬盘列表非空，序列号不重复

#### DiskItemSerializer
- **继承**: Serializer
- **字段**: id, harddisk_no, harddisk_sn_code, harddisk_type, harddisk_status, harddisk_sn_description

#### AssetOperationLogSerializer
- **模型**: AssetOperationLog | **继承**: ModelSerializer
- **所有字段**: read_only
- **额外声明字段**: operation_type_display

#### ContractBatchDeleteSerializer / ContractBatchCreateSerializer
- **继承**: Serializer
- **字段**: ids / items = ContractBatchCreateItemSerializer(many=True)

#### StorageBatchDeleteSerializer / StorageBatchCreateSerializer
- **继承**: Serializer
- **字段**: ids / items = StorageBatchCreateItemSerializer(many=True)

#### AssetTypeBatchDeleteSerializer / AssetTypeBatchCreateSerializer
- **继承**: Serializer
- **字段**: ids / items = AssetTypeBatchCreateItemSerializer(many=True)

#### RecycleAssetBatchCreateSerializer / RecycleAssetBatchDeleteSerializer
- **继承**: Serializer
- **字段**: items(RecycleAssetBatchItemSerializer), recycle_asset_storage(SlugRelated, optional), recycle_asset_recycle_person_jobcode(SlugRelated, optional) / ids

#### OutAssetBatchCreateSerializer / OutAssetBatchDeleteSerializer
- **继承**: Serializer
- **字段**: items(OutAssetBatchItemSerializer) / ids

#### DashboardStatSerializer
- **继承**: Serializer
- **字段**: total_assets, total_contracts, active_assets

---

### usermanagement 模块序列化器

---

#### DepartmentSerializer
- **模型**: Department | **继承**: ModelSerializer
- **字段**: fields = '__all__'

#### DepartmentTreeSerializer
- **模型**: Department | **继承**: ModelSerializer
- **字段**: department_code, department_name, department_information, parent_code, level, sort_order, children(SerializerMethodField), employee_count(SerializerMethodField)

#### DepartmentMoveSerializer
- **继承**: Serializer
- **字段**: target_parent_code(CharField, allow_null=True)

#### DepartmentBatchSortSerializer
- **继承**: Serializer
- **字段**: items = DepartmentSortSerializer(many=True)

#### EmployeeSerializer
- **模型**: Employee | **继承**: ModelSerializer
- **字段**: id, recordcode, employee_jobcode, employee_name, employee_status, employee_department_code(SlugRelated), employee_department_name(SlugRelated), employee_department_level(IntegerField, source='employee_department.level'), employee_phone, employee_location, employee_description, sort_order, is_deleted
- **注意**: Employee 不继承 BaseModel，没有 is_active/created_at/updated_at 字段

#### EmployeeDetailSerializer
- **模型**: Employee | **继承**: ModelSerializer
- **字段**: fields = '__all__'
- **额外声明字段**: 同 EmployeeSerializer

#### EmployeeCreateSerializer
- **模型**: Employee | **继承**: ModelSerializer
- **字段**: employee_jobcode, employee_name, employee_status, employee_department_code(SlugRelated), employee_phone, employee_location, employee_description, sort_order

#### EmployeeUpdateSerializer
- **模型**: Employee | **继承**: ModelSerializer
- **字段**: employee_name, employee_status, employee_department_code(SlugRelated), employee_phone, employee_location, employee_description, sort_order

#### EmployeeBatchSortSerializer
- **继承**: Serializer
- **字段**: items = EmployeeSortSerializer(many=True)

#### EmployeeBatchCreateSerializer / EmployeeBatchDeleteSerializer
- **继承**: Serializer
- **字段**: items(EmployeeBatchItemSerializer) / ids

#### DepartmentBatchCreateSerializer / DepartmentBatchDeleteSerializer
- **继承**: Serializer
- **字段**: items(DepartmentBatchItemSerializer) / ids

---

### unregisteredasset 模块序列化器

---

#### UnregisteredAssetCreateSerializer
- **模型**: UnregisteredAsset | **继承**: ModelSerializer
- **字段**: scenario_type, discovery_date, discovery_location, asset_name, asset_brand, asset_specification, unregistered_asset_type(FK), estimated_value, related_asset(FK), unregistered_asset_storage(FK), handle_description, attachments

#### UnregisteredAssetUpdateSerializer
- **模型**: UnregisteredAsset | **继承**: ModelSerializer
- **字段**: asset_name, asset_brand, asset_specification, unregistered_asset_type, estimated_value, discovery_location, unregistered_asset_storage, handle_description, attachments（全部 required=False）

#### UnregisteredAssetApproveSerializer
- **继承**: Serializer
- **字段**: handle_type(ChoiceField), approval_remark(CharField)

#### UnregisteredAssetListSerializer
- **模型**: UnregisteredAsset | **继承**: ModelSerializer
- **字段**: id, unregistered_code, scenario_type, scenario_type_display, asset_name, discovery_date, discovery_location, approval_status, approval_status_display, discovery_person_name, created_at

#### UnregisteredAssetDetailSerializer
- **模型**: UnregisteredAsset | **继承**: ModelSerializer
- **字段**: 所有字段 + SerializerMethodField: discovery_person, related_asset, approver, result_asset

---

### authusermanagement 模块序列化器

---

#### AuthUserSerializer
- **模型**: AuthUser | **继承**: ModelSerializer
- **字段**: auth_id, recordcode, auth_username, email, auth_is_active, auth_is_staff, auth_phone, last_login

#### RegisterSerializer
- **继承**: Serializer
- **字段**: auth_username, password, email, auth_phone

#### LoginSerializer
- **继承**: Serializer
- **字段**: auth_username, password

#### UserProfileUpdateSerializer
- **继承**: Serializer
- **字段**: email, auth_phone, password

#### LogoutSerializer
- **继承**: Serializer
- **字段**: refresh

---

## 三、ViewSets API 端点详情

### 1. StorageViewSet（仓库管理）

**路由**: `/api/assets/storages/` | **lookup_field**: `storage_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/storages/` | 列表 | query: keyword, page, page_size, storage_type, ordering | StorageSerializer | IsAuthenticated |
| POST | `/api/assets/storages/` | 创建 | body: StorageSerializer 字段 | StorageSerializer | IsAdminUser |
| GET | `/api/assets/storages/{storage_code}/` | 详情 | path: storage_code | StorageSerializer | IsAuthenticated |
| PUT | `/api/assets/storages/{storage_code}/` | 更新 | body: StorageSerializer 字段 | StorageSerializer | IsAdminUser |
| PATCH | `/api/assets/storages/{storage_code}/` | 部分更新 | body: 部分字段 | StorageSerializer | IsAdminUser |
| DELETE | `/api/assets/storages/{storage_code}/` | 删除 | path: storage_code | message | IsAdminUser |
| GET | `/api/assets/storages/statistics/` | 统计 | 无 | {total_storages, by_type} | IsAuthenticated |
| POST | `/api/assets/storages/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |
| POST | `/api/assets/storages/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 2. AssetTypeViewSet（资产类型管理）

**路由**: `/api/assets/asset-types/` | **lookup_field**: `asset_type_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/asset-types/` | 列表 | query: page, page_size, asset_type_category, search, ordering | AssetTypeSerializer | IsAuthenticated |
| POST | `/api/assets/asset-types/` | 创建 | body: AssetTypeSerializer 字段 | AssetTypeSerializer | IsAdminUser |
| GET | `/api/assets/asset-types/{asset_type_code}/` | 详情 | path: asset_type_code | AssetTypeSerializer | IsAuthenticated |
| PUT | `/api/assets/asset-types/{asset_type_code}/` | 更新 | body: 完整字段 | AssetTypeSerializer | IsAdminUser |
| PATCH | `/api/assets/asset-types/{asset_type_code}/` | 部分更新 | body: 部分字段 | AssetTypeSerializer | IsAdminUser |
| DELETE | `/api/assets/asset-types/{asset_type_code}/` | 删除 | path: asset_type_code | message | IsAdminUser |
| POST | `/api/assets/asset-types/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 3. ContractViewSet（合同管理）

**路由**: `/api/assets/contracts/` | **lookup_field**: `contract_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/contracts/` | 列表 | query: page, page_size, contract_type, contract_settledment_status, ordering | ContractDetailSerializer | IsAuthenticated |
| POST | `/api/assets/contracts/` | 创建 | body: ContractSerializer 字段 | ContractSerializer | IsAdminUser |
| GET | `/api/assets/contracts/{contract_code}/` | 详情 | path: contract_code | ContractDetailSerializer | IsAuthenticated |
| PUT | `/api/assets/contracts/{contract_code}/` | 更新 | body: 完整字段 | ContractSerializer | IsAdminUser |
| PATCH | `/api/assets/contracts/{contract_code}/` | 部分更新 | body: 部分字段 | ContractSerializer | IsAdminUser |
| DELETE | `/api/assets/contracts/{contract_code}/` | 删除 | path: contract_code | message | IsAdminUser |
| GET | `/api/assets/contracts/statistics/` | 统计 | 无 | 统计数据 | IsAuthenticated |
| GET | `/api/assets/contracts/search/` | 全局搜索 | query: keyword(必填), page, page_size | ContractDetailSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/contracts/getcontractByname/{name}/` | 按名称查 | path: name | ContractDetailSerializer(列表) | IsAuthenticated |
| POST | `/api/assets/contracts/{contract_code}/update_settlement_status/` | 更新结算状态 | body: {status: "pending/settled"} | {contract: ContractDetailSerializer} | IsAuthenticated |
| POST | `/api/assets/contracts/{contract_code}/payment_record/` | 添加付款记录 | body: {amount, description} | {contract: ContractDetailSerializer} | IsAuthenticated |
| POST | `/api/assets/contracts/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 4. AssetViewSet（资产管理 — 核心）

**路由**: `/api/assets/assets/` | **lookup_field**: `asset_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/assets/` | 列表 | query: keyword, page, page_size, asset_current_status, asset_type, asset_storage, ordering | AssetDetailSerializer | IsAuthenticated |
| POST | `/api/assets/assets/` | 创建 | body: AssetCreateSerializer 字段 | AssetDetailSerializer(列表) | IsAdminUser |
| GET | `/api/assets/assets/{asset_code}/` | 详情 | path: asset_code | AssetDetailSerializer | IsAuthenticated |
| PUT | `/api/assets/assets/{asset_code}/` | 更新 | body: 更新数据 | AssetDetailSerializer | IsAdminUser |
| PATCH | `/api/assets/assets/{asset_code}/` | 部分更新 | body: 部分字段 | AssetDetailSerializer | IsAdminUser |
| DELETE | `/api/assets/assets/{asset_code}/` | 删除 | path: asset_code | message | IsAdminUser |
| GET | `/api/assets/assets/statistics/` | 统计 | 无 | 统计数据 | IsAuthenticated |
| GET | `/api/assets/assets/search/` | 全局搜索 | query: keyword, status, asset_type, storage_code, contract_code | AssetDetailSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/assets/search_available/` | 查可用资产 | 无 | AssetSerializer(列表) | IsAuthenticated |
| GET | `/api/assets/assets/getassetbyname/{name}/` | 按名称查 | path: name | AssetDetailSerializer(列表) | IsAuthenticated |
| GET | `/api/assets/assets/getassetbyrecordcode/{recordcode}/` | 按recordcode查 | query: recordcode | AssetSerializer(列表) | IsAuthenticated |
| GET | `/api/assets/assets/combined_details/` | 综合详情 | query: asset_code(必填) | CombinedAsset数据 | IsAuthenticated |
| GET | `/api/assets/assets/contract_by_asset/{asset_code}/` | 通过资产查合同 | path: asset_code | ContractDetailSerializer | IsAuthenticated |
| POST | `/api/assets/assets/{asset_code}/change_status/` | 变更状态 | body: {status, description} | {asset: AssetDetailSerializer} | IsAuthenticated |
| POST | `/api/assets/assets/{asset_code}/change_outasset_employee/` | 变更申请人/保管人 | body: {applicant_jobcode, manager_jobcode} | {asset: AssetDetailSerializer} | IsAuthenticated |
| POST | `/api/assets/assets/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_items, fail_items} | IsAdminUser |
| POST | `/api/assets/assets/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 5. OutAssetViewSet（出库管理）

**路由**: `/api/assets/out-assets/` | **lookup_field**: `recordcode` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/out-assets/` | 列表 | query: keyword, searchType, asset_current_status, page, page_size, ordering | OutAssetDetailSerializer | IsAuthenticated |
| POST | `/api/assets/out-assets/` | 创建 | body: OutAssetSerializer 字段 | OutAssetSerializer | IsAdminUser |
| GET | `/api/assets/out-assets/{recordcode}/` | 详情 | path: recordcode | OutAssetDetailSerializer | IsAuthenticated |
| PUT | `/api/assets/out-assets/{recordcode}/` | 更新 | body: 更新数据 | OutAssetDetailSerializer | IsAdminUser |
| PATCH | `/api/assets/out-assets/{recordcode}/` | 部分更新 | body: 部分字段 | OutAssetDetailSerializer | IsAdminUser |
| DELETE | `/api/assets/out-assets/{recordcode}/` | 删除 | path: recordcode | message | IsAdminUser |
| GET | `/api/assets/out-assets/statistics/` | 统计 | 无 | 统计数据 | IsAuthenticated |
| GET | `/api/assets/out-assets/recyclable/` | 可回收列表 | query: years, search, searchType, asset_code, employee_jobcode, department_code, ordering | OutAssetDetailSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/out-assets/by-asset/{asset_code}/` | 按资产查 | path: asset_code | OutAssetSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/out-assets/by-applicant/{applicant_jobcode}/` | 按申请人查 | path: applicant_jobcode | OutAssetDetailSerializer(分页) | IsAuthenticated |
| POST | `/api/assets/out-assets/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_items, fail_items} | IsAdminUser |
| POST | `/api/assets/out-assets/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 6. RecycleAssetViewSet（回收管理）

**路由**: `/api/assets/recycle-assets/` | **lookup_field**: `recordcode` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/recycle-assets/` | 列表 | query: page, page_size, recycle_asset_code, operator_employee, recycle_outasset, recycle_date_from, recycle_date_to, ordering | RecycleAssetSerializer | IsAuthenticated |
| POST | `/api/assets/recycle-assets/` | 创建 | body: RecycleAssetSerializer 字段 | RecycleAssetSerializer | IsAdminUser |
| GET | `/api/assets/recycle-assets/{recordcode}/` | 详情 | path: recordcode | RecycleAssetSerializer | IsAuthenticated |
| PUT | `/api/assets/recycle-assets/{recordcode}/` | 更新 | body: 更新数据 | RecycleAssetSerializer | IsAdminUser |
| PATCH | `/api/assets/recycle-assets/{recordcode}/` | 部分更新 | body: 部分字段 | RecycleAssetSerializer | IsAdminUser |
| DELETE | `/api/assets/recycle-assets/{recordcode}/` | 删除 | path: recordcode | message | IsAdminUser |
| GET | `/api/assets/recycle-assets/by-asset/{recycle_asset_code}/` | 按资产查 | path: recycle_asset_code | RecycleAssetSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/recycle-assets/by-outasset/{recordcode}/` | 按出库记录查 | path: recordcode | RecycleAssetSerializer | IsAuthenticated |
| POST | `/api/assets/recycle-assets/batch-create/` | 批量创建 | body: {items: [...], recycle_asset_storage, recycle_asset_recycle_person_jobcode} | {total, success_items, fail_items} | IsAdminUser |
| POST | `/api/assets/recycle-assets/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 7. DamagedAssetViewSet（待报废管理）

**路由**: `/api/assets/damaged-assets/` | **lookup_field**: `damaged_asset` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/damaged-assets/` | 列表 | query: page, page_size, approval_status, search, ordering | DamagedAssetSerializer | IsAuthenticated |
| POST | `/api/assets/damaged-assets/` | 创建 | body: DamagedAssetSerializer 字段 | DamagedAssetSerializer | IsAuthenticated |
| GET | `/api/assets/damaged-assets/{damaged_asset}/` | 详情 | path: damaged_asset | DamagedAssetSerializer | IsAuthenticated |
| PUT | `/api/assets/damaged-assets/{damaged_asset}/` | 更新 | body: 更新数据(仅pending可改) | DamagedAssetSerializer | IsAuthenticated |
| PATCH | `/api/assets/damaged-assets/{damaged_asset}/` | 部分更新 | body: 部分字段(仅pending可改) | DamagedAssetSerializer | IsAuthenticated |
| DELETE | `/api/assets/damaged-assets/{damaged_asset}/` | 取消申请 | path: damaged_asset | message | IsAuthenticated |
| POST | `/api/assets/damaged-assets/{damaged_asset}/approve/` | 审批通过 | body: {approver_jobcode, operator_name} | {damaged_asset, waste_asset} | IsAuthenticated |
| POST | `/api/assets/damaged-assets/{damaged_asset}/reject/` | 审批拒绝 | body: {approver_jobcode, operator_name} | DamagedAssetSerializer | IsAuthenticated |
| GET | `/api/assets/damaged-assets/by-asset/{damaged_asset}/` | 按资产查 | path: damaged_asset | DamagedAssetSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/damaged-assets/statistics/` | 统计 | 无 | {total_damaged, by_status} | IsAuthenticated |
| POST | `/api/assets/damaged-assets/batch-delete/` | 批量取消 | body: {ids: [...]} | {total, success_count, ...} | IsAuthenticated |

---

### 8. WasteAssetViewSet（已报废管理）

**路由**: `/api/assets/waste-assets/` | **lookup_field**: `waste_asset__asset_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/waste-assets/` | 列表 | query: page, page_size, waste_asset_date, search, ordering | WasteAssetSerializer | IsAuthenticated |
| POST | `/api/assets/waste-assets/` | **禁止(405)** | - | - | - |
| GET | `/api/assets/waste-assets/{waste_asset__asset_code}/` | 详情 | path: asset_code | WasteAssetSerializer | IsAuthenticated |
| PUT | `/api/assets/waste-assets/{waste_asset__asset_code}/` | **禁止(405)** | - | - | - |
| PATCH | `/api/assets/waste-assets/{waste_asset__asset_code}/` | **禁止(405)** | - | - | - |
| DELETE | `/api/assets/waste-assets/{waste_asset__asset_code}/` | 删除 | path: asset_code | message | IsAuthenticated |
| GET | `/api/assets/waste-assets/statistics/` | 统计 | 无 | 统计数据 | IsAuthenticated |
| GET | `/api/assets/waste-assets/by-asset/{waste_asset}/` | 按资产查 | path: waste_asset | WasteAssetSerializer(分页) | IsAuthenticated |
| GET | `/api/assets/waste-assets/by-date-range/` | 按日期查 | query: start_date, end_date | WasteAssetSerializer(分页) | IsAuthenticated |
| POST | `/api/assets/waste-assets/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAuthenticated |

---

### 9. HardDiskSNViewSet（硬盘序列号管理）

**路由**: `/api/assets/harddisk-sn/` | **lookup_field**: `harddisksn_asset` | **分页**: 无

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/assets/harddisk-sn/` | 列表 | query: page, page_size, harddisk_status, search, ordering | HardDiskSNSerializer | IsAuthenticated |
| POST | `/api/assets/harddisk-sn/` | 创建 | body: HardDiskSNSerializer 字段 | HardDiskSNSerializer | IsAuthenticated |
| GET | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 详情 | path: harddisksn_asset | HardDiskSNSerializer | IsAuthenticated |
| PUT | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 更新 | body: 更新数据 | HardDiskSNSerializer | IsAuthenticated |
| PATCH | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 部分更新 | body: 部分字段 | HardDiskSNSerializer | IsAuthenticated |
| DELETE | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 删除 | path: harddisksn_asset | message | IsAuthenticated |
| POST | `/api/assets/harddisk-sn/search_by_serial_number/` | 按序列号查 | body: {harddisk_sn_code} | HardDiskSNSerializer | IsAuthenticated |
| GET | `/api/assets/harddisk-sn/by-asset/{asset_code}/` | 按资产查 | path: asset_code | HardDiskSNSerializer(分页) | IsAuthenticated |
| POST | `/api/assets/harddisk-sn/batch/` | 批量保存 | body: {asset_code, disks: [...]} | {created, updated, total, ...} | IsAuthenticated |

---

### 10. DashboardViewSet（仪表盘）

**路由**: `/api/dashboard/` | **分页**: 无

| HTTP方法 | URL | 功能 | 请求参数 | 返回内容 | 权限 |
|----------|-----|------|----------|----------|------|
| GET | `/api/dashboard/overview/` | 概览统计 | 无 | 统计概览数据 | IsAuthenticated |
| GET | `/api/dashboard/recent_out_assets/` | 最近出库 | query: limit(默认10) | 最近出库列表 | IsAuthenticated |
| GET | `/api/dashboard/recent_recycle_assets/` | 最近回收 | query: limit(默认10) | 最近回收列表 | IsAuthenticated |

---

### 11. DepartmentViewSet（部门管理）

**路由**: `/api/users/departments/` | **lookup_field**: `department_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/users/departments/` | 列表 | query: page, page_size, search, ordering | DepartmentSerializer | IsAuthenticated |
| POST | `/api/users/departments/` | 创建 | body: DepartmentSerializer 字段 | DepartmentSerializer | IsAdminUser |
| GET | `/api/users/departments/{department_code}/` | 详情 | path: department_code | DepartmentSerializer | IsAuthenticated |
| PUT | `/api/users/departments/{department_code}/` | 更新 | body: 完整字段 | DepartmentSerializer | IsAdminUser |
| PATCH | `/api/users/departments/{department_code}/` | 部分更新 | body: 部分字段 | DepartmentSerializer | IsAdminUser |
| DELETE | `/api/users/departments/{department_code}/` | 删除 | path: department_code | message | IsAdminUser |
| GET | `/api/users/departments/tree/` | 部门树 | 无 | 树形结构(递归children) | IsAuthenticated |
| GET | `/api/users/departments/{department_code}/employees/` | 部门员工 | query: status(active/left/retirement) | {department, employees_count, employees} | IsAuthenticated |
| GET | `/api/users/departments/{department_code}/children/` | 子部门 | 无 | {parent, children_count, children} | IsAuthenticated |
| GET | `/api/users/departments/{department_code}/path/` | 面包屑 | 无 | {current, path, depth} | IsAuthenticated |
| GET | `/api/users/departments/{department_code}/descendants/` | 后代部门 | 无 | {current, descendants_count, descendants} | IsAuthenticated |
| PUT | `/api/users/departments/{department_code}/move/` | 移动部门 | body: {target_parent_code} | DepartmentSerializer | IsAdminUser |
| PUT | `/api/users/departments/sort/` | 批量排序 | body: {items: [{department_code, sort_order}]} | {updated_count} | IsAdminUser |
| POST | `/api/users/departments/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_count, ...} | IsAdminUser |
| POST | `/api/users/departments/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 12. EmployeeViewSet（员工管理）

**路由**: `/api/users/employees/` | **lookup_field**: `employee_jobcode` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/users/employees/` | 列表 | query: page, page_size, employee_status, employee_department__department_code, search, ordering | EmployeeSerializer | IsAuthenticated |
| POST | `/api/users/employees/` | 创建 | body: EmployeeCreateSerializer 字段 | EmployeeDetailSerializer | IsAdminUser |
| GET | `/api/users/employees/{employee_jobcode}/` | 详情 | path: employee_jobcode | EmployeeDetailSerializer | IsAuthenticated |
| PUT | `/api/users/employees/{employee_jobcode}/` | 更新 | body: EmployeeUpdateSerializer 字段 | EmployeeUpdateSerializer | IsAdminUser |
| PATCH | `/api/users/employees/{employee_jobcode}/` | 部分更新 | body: 部分字段 | EmployeeUpdateSerializer | IsAdminUser |
| DELETE | `/api/users/employees/{employee_jobcode}/` | 删除 | path: employee_jobcode | message | IsAdminUser |
| GET | `/api/users/employees/statistics/` | 统计 | 无 | 统计数据 | IsAuthenticated |
| GET | `/api/users/employees/active_employees/` | 在职员工 | 无(分页) | EmployeeSerializer(分页) | IsAuthenticated |
| GET | `/api/users/employees/search/` | 全局搜索 | query: keyword(必填), page, page_size | EmployeeSerializer(分页) | IsAuthenticated |
| POST | `/api/users/employees/{employee_jobcode}/change_status/` | 变更状态 | body: {status} | {message, employee} | IsAuthenticated |
| GET | `/api/users/employees/employees/{employee_jobcode}/` | 按工号查 | path: employee_jobcode | EmployeeDetailSerializer | IsAuthenticated |
| POST | `/api/users/employees/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_count, ...} | IsAdminUser |
| POST | `/api/users/employees/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |
| PUT | `/api/users/employees/sort/` | 批量排序 | body: {items: [{employee_jobcode, sort_order}]} | EmployeeSerializer(列表) | IsAdminUser |

---

### 13. UnregisteredAssetViewSet（未登记资产管理）

**路由**: `/api/unregisteredassets/unregistered-assets/` | **lookup_field**: `unregistered_code` | **分页**: CustomPageNumberPagination

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/unregisteredassets/unregistered-assets/` | 列表 | query: page, page_size, scenario_type, approval_status, discovery_person, related_asset, ordering | UnregisteredAssetListSerializer | IsAuthenticated |
| POST | `/api/unregisteredassets/unregistered-assets/` | 创建 | body: UnregisteredAssetCreateSerializer 字段 | UnregisteredAssetDetailSerializer | IsAuthenticated |
| GET | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 详情 | path: unregistered_code | UnregisteredAssetDetailSerializer | IsAuthenticated |
| PUT | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 更新 | body: UnregisteredAssetUpdateSerializer 字段 | UnregisteredAssetDetailSerializer | IsAuthenticated |
| PATCH | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 部分更新 | body: 部分字段 | UnregisteredAssetDetailSerializer | IsAuthenticated |
| DELETE | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 删除 | path: unregistered_code(仅pending可删) | message | IsAdminUser |
| POST | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/approve/` | 审批 | body: {handle_type, approval_remark} | 审批结果 | IsAuthenticated |
| POST | `/api/unregisteredassets/unregistered-assets/batch-create/` | 批量创建 | body: {items: [...]} | {total, success_count, ...} | IsAuthenticated |
| POST | `/api/unregisteredassets/unregistered-assets/batch-delete/` | 批量删除 | body: {ids: [...]} | {total, success_count, ...} | IsAdminUser |

---

### 14. AuthUserViewSet（用户管理）

**路由**: `/api/auth/users/` | **lookup_field**: `auth_id` | **分页**: 无

| HTTP方法 | URL | 功能 | 请求参数 | 返回序列化器 | 权限 |
|----------|-----|------|----------|------------|------|
| GET | `/api/auth/users/` | 列表 | 无 | AuthUserSerializer | IsAdminUser |
| POST | `/api/auth/users/` | 创建 | body: RegisterSerializer 字段 | {user, refresh, access} | AllowAny |
| GET | `/api/auth/users/{auth_id}/` | 详情 | path: auth_id | AuthUserSerializer | IsAdminUser |
| PUT | `/api/auth/users/{auth_id}/` | 更新 | body: AuthUserSerializer 字段 | AuthUserSerializer | IsAuthenticated(本人/管理员) |
| PATCH | `/api/auth/users/{auth_id}/` | 部分更新 | body: 部分字段 | AuthUserSerializer | IsAuthenticated(本人/管理员) |
| DELETE | `/api/auth/users/{auth_id}/` | 删除 | path: auth_id | message | IsAuthenticated(本人/管理员) |
| GET | `/api/auth/users/list_active/` | 激活用户 | 无 | AuthUserSerializer | IsAdminUser |

---

### 自定义 APIView（认证模块）

| HTTP方法 | URL | 功能 | 请求参数 | 返回内容 | 权限 |
|----------|-----|------|----------|----------|------|
| POST | `/api/auth/register/` | 注册 | body: RegisterSerializer 字段 | {user, refresh, access} | AllowAny |
| POST | `/api/auth/login/` | 登录 | body: {auth_username, password} | {user, refresh, access} | AllowAny |
| GET | `/api/auth/profile/` | 个人信息 | 无 | AuthUserSerializer | IsAuthenticated |
| PUT | `/api/auth/profile/` | 更新个人信息 | body: {email, auth_phone, password} | AuthUserSerializer | IsAuthenticated |
| POST | `/api/auth/logout/` | 退出登录 | body: {refresh} | message | IsAuthenticated |
| POST | `/api/auth/token/refresh/` | 刷新Token | body: {refresh} | {access} | AllowAny |
| POST | `/api/auth/token/verify/` | 验证Token | body: {token} | {} | AllowAny |

---

## 全局分页配置

**类名**: `CustomPageNumberPagination` (`core/pagination.py`)

| 配置项 | 值 |
|--------|-----|
| 默认每页数量 | 20 |
| page 参数名 | `page` |
| page_size 参数名 | `page_size` |
| 最大每页数量 | 100 |

**响应格式**:
```json
{
  "code": 200,
  "msg": "查询成功",
  "data": {
    "count": 100,
    "total_pages": 5,
    "page": 1,
    "page_size": 20,
    "next": "http://...",
    "previous": null,
    "results": [...]
  }
}
```

---

## 全局权限体系

| 权限类 | 来源 | 说明 |
|--------|------|------|
| `IsAdminUser` | `core.permissions` | `is_authenticated` + `is_staff=True` |
| `IsAdminUser` | `rest_framework.permissions` | 仅 `is_staff=True` |
| `IsAuthenticated` | `rest_framework.permissions` | 已认证用户 |
| `AllowAny` | `rest_framework.permissions` | 无需认证 |

---

## API 路由总览

| URL前缀 | 模块 | ViewSet |
|---------|------|---------|
| `/api/auth/` | authusermanagement | AuthUserViewSet + 4个APIView |
| `/api/users/` | usermanagement | DepartmentViewSet, EmployeeViewSet |
| `/api/assets/` | assetmanagement | StorageViewSet, AssetTypeViewSet, ContractViewSet, AssetViewSet, OutAssetViewSet, RecycleAssetViewSet, DamagedAssetViewSet, WasteAssetViewSet, HardDiskSNViewSet |
| `/api/unregisteredassets/` | unregisteredasset | UnregisteredAssetViewSet |
| `/api/dashboard/` | assetmanagement | DashboardViewSet |

**统计**: 14个ViewSet + 4个APIView + 约158个API端点
