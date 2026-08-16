# 资产管理系统后端 - 项目审查报告

> 生成时间: 2026-06-12
> 审查范围: 全项目架构、业务逻辑、接口设计

---

## 一、项目现状

### 1.1 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.12+ |
| Web框架 | Django | 6.0.5 |
| REST框架 | Django REST Framework | 3.16.0 |
| 数据库 | PostgreSQL | 16 |
| 认证 | JWT (SimpleJWT) | 5.5.1 |
| API文档 | drf-spectacular | 0.28.0 |
| 过滤器 | django-filter | 25.1 |
| 跨域 | django-cors-headers | 4.7.0 |

### 1.2 项目结构

```
asset_management_backend/
├── config/                     # 项目配置
│   ├── settings/               # 多环境配置
│   │   ├── base.py             # 基础配置
│   │   ├── development.py      # 开发环境
│   │   ├── production.py       # 生产环境
│   │   └── test.py             # 测试环境
│   ├── urls.py                 # 根路由
│   ├── wsgi.py / asgi.py       # WSGI/ASGI入口
├── core/                       # 核心公共模块
│   ├── models.py               # BaseModel, SoftDeleteManager
│   ├── exceptions.py           # 自定义异常
│   ├── permissions.py          # 权限类
│   ├── mixins.py               # ResponseWrapperMixin等
│   ├── pagination.py           # 自定义分页
│   ├── batch_mixins.py         # 批量操作Mixin
│   ├── constants.py            # 常量定义
│   ├── validators.py           # 校验器
├── apps/                       # 业务应用
│   ├── assetmanagement/        # 资产管理(核心)
│   ├── authusermanagement/     # 认证与用户管理
│   ├── usermanagement/         # 部门与员工管理
│   └── unregisteredasset/      # 未登记资产管理
├── utils/                      # 工具模块
│   ├── response_utils.py       # 统一响应格式
│   ├── date_utils.py           # 日期工具
│   └── string_utils.py         # 字符串工具
├── manage.py                   # Django管理入口
├── pyproject.toml              # 项目配置
├── Dockerfile / docker-compose.yml  # Docker配置
├── AGENTS.md                   # AI开发规范
```

### 1.3 应用模块概览

| 应用 | 职责 | 核心模型 |
|------|------|----------|
| `assetmanagement` | 资产生命周期管理 | Asset, Storage, AssetType, Contract, OutAsset, RecycleAsset, DamagedAsset, WasteAsset, HardDiskSN, AssetOperationLog |
| `authusermanagement` | 用户认证与权限 | AuthUser (自定义用户模型) |
| `usermanagement` | 组织架构管理 | Department, Employee |
| `unregisteredasset` | 不在账资产处理 | UnregisteredAsset |

---

## 二、架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────┐
│                   View 层                        │
│  ModelViewSet + ResponseWrapperMixin             │
│  职责: HTTP请求处理、权限校验、响应封装              │
├─────────────────────────────────────────────────┤
│                 Serializer 层                     │
│  ModelSerializer + 自定义校验                      │
│  职责: 数据校验、序列化/反序列化、字段白名单           │
├─────────────────────────────────────────────────┤
│                  Service 层                       │
│  业务逻辑 + @transaction.atomic                   │
│  职责: 业务规则、事务控制、状态变更、审计日志          │
├─────────────────────────────────────────────────┤
│                 Selector 层                       │
│  静态方法封装复杂查询                               │
│  职责: 数据查询、N+1优化、软删除过滤                  │
├─────────────────────────────────────────────────┤
│                  Model 层                         │
│  BaseModel + SoftDeleteManager                   │
│  职责: 数据结构定义、字段约束、索引                   │
└─────────────────────────────────────────────────┘
```

**依赖方向**: View → Serializer → Service → Selector → Model (单向依赖)

### 2.2 关键设计模式

#### 2.2.1 软删除 + recordcode 模式

```
BaseModel 提供:
  - is_deleted: 软删除标记
  - created_at: 创建时间
  - updated_at: 更新时间
  - is_active: 激活状态
  - SoftDeleteManager: 自动过滤 is_deleted=False

recordcode 设计:
  - 格式: REC-YYYYMMDD-XXXXXXXX (UUID随机8位)
  - 用途: 外键关联的唯一标识(数据库级无条件唯一)
  - 业务编码: 条件唯一(仅 is_deleted=False 时唯一)
```

#### 2.2.2 状态机 (AssetFSM)

```
状态流转图:
  in_store ──outasset──→ in_use ──recycle──→ recycled_pending ──damaged──→ damaged ──approve──→ scrapped(终态)
                            ↑                      │                      │
                            └──────outasset────────┘                      │
                                                   └──── reject/cancel────┘

设计原则:
  - 只修改 asset.asset_current_status 字段
  - 由 Service 层控制事务和并发锁(select_for_update)
  - InvalidTransitionError 表示非法转换
```

#### 2.2.3 审计日志 (AuditLogger)

```
显式调用模式(替代 Signal):
  AuditLogger.log_asset_create(asset, operator)
  AuditLogger.log_asset_update(asset, before, after, operator)
  AuditLogger.log_state_change(asset, from, to, trigger)

AssetOperationLog:
  - 只读表, 不允许修改和删除
  - JSONField 存储变更前后数据
  - 自动记录操作人、操作时间、IP地址
```

#### 2.2.4 批量操作 (BatchOperationMixin)

```
batch_execute:
  - MAX_BATCH_SIZE 前置校验(100)
  - 逐条独立执行, 单条失败不影响其他
  - AppValidationError → error_code 映射
  - 统一返回 {total, success_count, fail_count, success_items, fail_items}

batch_delete_execute:
  - 默认启用 transaction.atomic
  - 返回 {total, success_count, fail_count, success_ids, fail_items}
```

### 2.3 应用层架构

#### assetmanagement (核心)

```
assetmanagement/
├── models.py              # 10个数据模型
├── serializers.py         # 序列化器(增/改/查分离)
├── views.py               # ViewSet(仅HTTP, 调用Service)
├── urls.py                # DRF Router路由
├── dashboard_urls.py      # 仪表盘路由
│
├── asset_service.py       # 资产CRUD + 编码生成
├── outasset_service.py    # 出库业务
├── recycle_service.py     # 回收业务
├── damaged_service.py     # 报废申请
├── waste_service.py       # 已报废执行
├── contract_service.py    # 合同管理
├── storage_service.py     # 仓库管理
├── asset_type_service.py  # 资产类型管理
├── harddisk_service.py    # 硬盘SN管理
│
├── selectors.py           # 查询层(所有Selector集中)
├── interfaces.py          # 跨应用接口契约
├── signals.py             # 信号(仅审计)
├── audit.py               # 显式审计模块
├── operation_log_service.py  # 操作日志服务
├── operation_log_views.py    # 操作日志视图
├── state_machine/         # 状态机
│   ├── __init__.py
│   └── core.py            # AssetFSM + AssetState
├── querysets.py           # 自定义QuerySet
├── admin.py               # Django Admin配置
└── tests/                 # 测试用例
```

---

## 三、业务流程

### 3.1 资产生命周期

```
                    ┌──────────────┐
                    │   资产入库     │
                    │  (创建+编码)   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    在库       │ ←── 回收资产 / 审批拒绝
                    │  in_store    │
                    └──────┬───────┘
                           │ 出库
                    ┌──────▼───────┐
                    │    在用       │ ←── 取消出库
                    │   in_use     │
                    └──────┬───────┘
                           │ 回收
                    ┌──────▼───────┐
                    │  已回收待发放   │ ←── 取消回收 / 审批拒绝
                    │recycled_pending│
                    └──────┬───────┘
                           │ 报废申请
                    ┌──────▼───────┐
                    │    待报废      │ ←── 取消申请
                    │   damaged    │
                    └──────┬───────┘
                           │ 审批通过
                    ┌──────▼───────┐
                    │    已报废      │ (终态)
                    │  scrapped    │
                    └──────────────┘
```

### 3.2 资产出库流程

```
1. 前端提交出库申请 (outasset_code, outasset_type, outasset_date)
2. Service 层校验:
   a. 资产状态必须为 in_store 或 recycled_pending
   b. 记录出库前状态(outasset_previous_status)
3. 创建 OutAsset 记录
4. 状态机变更: AssetFSM.outasset(asset)
5. 更新 Asset 字段:
   - asset_current_status → in_use
   - asset_storage_code → None
   - asset_applicant_jobcode → 申请人
   - asset_manager_jobcode → 保管人
   - asset_using_location → 使用地点
6. 审计日志: AuditLogger.log_asset_out()
```

### 3.3 资产回收流程

```
1. 前端提交回收申请 (outasset_recordcode, recycle_asset_date)
2. Service 层校验:
   a. 关联资产状态必须为 in_use
   b. 出库记录必须存在且有效
3. 创建 RecycleAsset 记录
4. 状态机变更: AssetFSM.recycle(asset)
5. 更新 Asset 字段:
   - asset_current_status → recycled_pending
   - asset_storage_code → 回收仓库
   - asset_entry_person_jobcode → 回收操作人
6. 审计日志: AuditLogger.log_asset_recycle()
```

### 3.4 报废审批流程

```
1. 提交报废申请 (创建 DamagedAsset)
   - 状态机: AssetFSM.damaged(asset)
   - 资产状态 → damaged

2. 审批通过 (approve_damaged_asset):
   a. 更新 DamagedAsset.approval_status → approved
   b. 状态机: AssetFSM.approve(asset) → scrapped
   c. 自动创建 WasteAsset 记录
   d. 审计日志

3. 审批拒绝 (reject_damaged_asset):
   a. 更新 DamagedAsset.approval_status → rejected
   b. 状态机: AssetFSM.reject(asset) → recycled_pending
   c. 审计日志
```

### 3.5 未登记资产处理

```
三种场景:
  S1 (实物有系统无): 发现未登记资产 → 创建新Asset → 回收/报废
  S2 (系统有无出库): 系统有记录但无出库 → 补建出库记录 → 回收
  S3 (状态异常): 资产状态与实际不符 → 修正状态 → 回收

流程:
  1. 发现人提交未登记资产(UnregisteredAsset)
  2. 管理员审批 → 选择处理方式(handle_type)
  3. 审批通过后自动执行:
     - S1: 创建Asset + AssetFSM.unregistered_create_and_recycle()
     - S2: 补建OutAsset + AssetFSM.force_recycle_from_any()
     - S3: AssetFSM.force_recycle_from_any()
  4. 结果追踪(result_asset_code, result_recycle_code)
```

---

## 四、接口设计

### 4.1 统一响应格式

#### 成功响应
```json
{
    "code": 200,
    "msg": "操作成功",
    "data": { ... }
}
```

#### 错误响应
```json
{
    "code": 400,
    "msg": "资产编码已存在",
    "data": {}
}
```

#### 分页响应
```json
{
    "code": 200,
    "msg": "查询成功",
    "data": {
        "count": 100,
        "total_pages": 5,
        "page": 1,
        "page_size": 20,
        "next": "http://api.example.com/assets/?page=2&page_size=20",
        "previous": null,
        "results": [ ... ]
    }
}
```

### 4.2 认证接口 (authusermanagement)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/auth/register/` | 用户注册 | 无 |
| POST | `/api/auth/login/` | 用户登录 | 无 |
| POST | `/api/auth/logout/` | 退出登录 | Bearer |
| GET | `/api/auth/profile/` | 获取个人信息 | Bearer |
| PUT | `/api/auth/profile/` | 更新个人信息 | Bearer |
| POST | `/api/auth/token/` | 获取JWT令牌 | 无 |
| POST | `/api/auth/token/refresh/` | 刷新JWT令牌 | 无 |
| POST | `/api/auth/token/verify/` | 验证JWT令牌 | 无 |
| GET | `/api/auth/users/` | 用户列表(管理员) | Bearer+Admin |
| POST | `/api/auth/users/` | 创建用户 | 无 |
| GET | `/api/auth/users/{id}/` | 用户详情 | Bearer+Admin |
| PUT | `/api/auth/users/{id}/` | 更新用户 | Bearer |
| DELETE | `/api/auth/users/{id}/` | 删除用户 | Bearer |

#### 登录请求示例
**POST** `/api/auth/login/`
```json
// Request Body
{
    "username": "admin",
    "password": "123456"
}

// Response 200
{
    "code": 200,
    "msg": "登录成功",
    "data": {
        "user": {
            "auth_id": 1,
            "auth_username": "admin",
            "email": "admin@example.com",
            "auth_is_staff": true,
            "auth_is_active": true
        },
        "refresh": "eyJhbGciOiJIUzI1NiIs...",
        "access": "eyJhbGciOiJIUzI1NiIs..."
    }
}
```

### 4.3 部门管理接口 (usermanagement/departments)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/users/departments/` | 部门列表 | Bearer |
| POST | `/api/users/departments/` | 创建部门 | Bearer+Admin |
| GET | `/api/users/departments/{code}/` | 部门详情 | Bearer |
| PUT | `/api/users/departments/{code}/` | 更新部门 | Bearer+Admin |
| DELETE | `/api/users/departments/{code}/` | 删除部门 | Bearer+Admin |
| POST | `/api/users/departments/batch-create/` | 批量创建 | Bearer+Admin |
| POST | `/api/users/departments/batch-delete/` | 批量删除 | Bearer+Admin |
| GET | `/api/users/departments/{code}/employees/` | 部门员工列表 | Bearer |
| POST | `/api/users/departments/{code}/sort/` | 排序 | Bearer+Admin |
| POST | `/api/users/departments/{code}/move/` | 移动部门 | Bearer+Admin |
| GET | `/api/users/departments/tree/` | 部门树结构 | Bearer |

#### 创建部门请求示例
**POST** `/api/users/departments/`
```json
// Request Body
{
    "department_code": "D001",
    "department_name": "技术部",
    "department_information": "张三",
    "parent_code": null,
    "level": 0,
    "sort_order": 0
}

// Response 201
{
    "code": 200,
    "msg": "创建成功",
    "data": {
        "recordcode": "REC-20260612-A1B2C3D4",
        "department_code": "D001",
        "department_name": "技术部",
        "department_information": "张三",
        "parent_code": null,
        "level": 0,
        "sort_order": 0
    }
}
```

### 4.4 员工管理接口 (usermanagement/employees)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/users/employees/` | 员工列表 | Bearer |
| POST | `/api/users/employees/` | 创建员工 | Bearer+Admin |
| GET | `/api/users/employees/{id}/` | 员工详情 | Bearer |
| PUT | `/api/users/employees/{id}/` | 更新员工 | Bearer+Admin |
| DELETE | `/api/users/employees/{id}/` | 删除员工 | Bearer+Admin |
| POST | `/api/users/employees/batch-create/` | 批量创建 | Bearer+Admin |
| POST | `/api/users/employees/batch-delete/` | 批量删除 | Bearer+Admin |
| GET | `/api/users/employees/search/` | 搜索员工 | Bearer |

### 4.5 仓库管理接口 (assetmanagement/storages)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/storages/` | 仓库列表 | Bearer |
| POST | `/api/assets/storages/` | 创建仓库 | Bearer+Admin |
| GET | `/api/assets/storages/{code}/` | 仓库详情 | Bearer |
| PUT | `/api/assets/storages/{code}/` | 更新仓库 | Bearer+Admin |
| DELETE | `/api/assets/storages/{code}/` | 删除仓库 | Bearer+Admin |
| POST | `/api/assets/storages/batch-delete/` | 批量删除 | Bearer+Admin |
| GET | `/api/assets/storages/statistics/` | 仓库统计 | Bearer |

#### 查询参数
- `keyword`: 模糊搜索(编码/名称/地址)
- `storage_type`: 仓库类型筛选(newasset/recycle/damaged)
- `page`: 页码
- `page_size`: 每页数量(最大100)

### 4.6 资产类型接口 (assetmanagement/asset-types)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/asset-types/` | 类型列表 | Bearer |
| POST | `/api/assets/asset-types/` | 创建类型 | Bearer+Admin |
| GET | `/api/assets/asset-types/{code}/` | 类型详情 | Bearer |
| PUT | `/api/assets/asset-types/{code}/` | 更新类型 | Bearer+Admin |
| DELETE | `/api/assets/asset-types/{code}/` | 删除类型 | Bearer+Admin |
| POST | `/api/assets/asset-types/batch-delete/` | 批量删除 | Bearer+Admin |

### 4.7 合同管理接口 (assetmanagement/contracts)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/contracts/` | 合同列表 | Bearer |
| POST | `/api/assets/contracts/` | 创建合同 | Bearer+Admin |
| GET | `/api/assets/contracts/{code}/` | 合同详情 | Bearer |
| PUT | `/api/assets/contracts/{code}/` | 更新合同 | Bearer+Admin |
| DELETE | `/api/assets/contracts/{code}/` | 删除合同 | Bearer+Admin |
| POST | `/api/assets/contracts/batch-delete/` | 批量删除 | Bearer+Admin |
| GET | `/api/assets/contracts/statistics/` | 合同统计 | Bearer |
| POST | `/api/assets/contracts/{code}/update_settlement_status/` | 更新结算状态 | Bearer+Admin |
| POST | `/api/assets/contracts/{code}/payment_record/` | 添加付款记录 | Bearer+Admin |
| GET | `/api/assets/contracts/getcontractByname/{name}/` | 按名称搜索 | Bearer |
| GET | `/api/assets/contracts/search/` | 全局搜索 | Bearer |

#### 添加付款记录示例
**POST** `/api/assets/contracts/{code}/payment_record/`
```json
// Request Body
{
    "amount": 50000.00,
    "description": "首期付款"
}

// Response 200
{
    "code": 200,
    "msg": "付款记录添加成功",
    "data": {
        "contract": {
            "contract_code": "HT-2026-001",
            "contract_name": "服务器采购合同",
            "contract_paid_price": 50000.00,
            "contract_paid_count_number": 1,
            "contract_paid_record": "2026-06-12 10:30:00: 付款 50000.00 元 - 首期付款\n"
        }
    }
}
```

### 4.8 资产管理接口 (assetmanagement/assets)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/assets/` | 资产列表 | Bearer |
| POST | `/api/assets/assets/` | 创建资产 | Bearer |
| GET | `/api/assets/assets/{code}/` | 资产详情 | Bearer |
| PUT | `/api/assets/assets/{code}/` | 更新资产 | Bearer |
| DELETE | `/api/assets/assets/{code}/` | 删除资产(软删除) | Bearer |
| POST | `/api/assets/assets/batch-create/` | 批量创建 | Bearer+Admin |
| POST | `/api/assets/assets/batch-delete/` | 批量删除 | Bearer+Admin |
| GET | `/api/assets/assets/statistics/` | 资产统计 | Bearer |
| GET | `/api/assets/assets/search/` | 全局搜索 | Bearer |
| GET | `/api/assets/assets/search_available/` | 可用资产列表 | Bearer |
| GET | `/api/assets/assets/getassetbyname/{name}/` | 按名称搜索 | Bearer |
| GET | `/api/assets/assets/getassetbyrecordcode/{code}/` | 按记录编码查询 | Bearer |
| POST | `/api/assets/assets/{code}/change_status/` | 变更状态 | Bearer |
| POST | `/api/assets/assets/{code}/change_outasset_employee/` | 变更申请人/保管人 | Bearer |
| GET | `/api/assets/assets/combined_details/{code}/` | 综合详情 | Bearer |
| GET | `/api/assets/assets/contract_by_asset/{code}/` | 查询关联合同 | Bearer |

#### 创建资产请求示例
**POST** `/api/assets/assets/`
```json
// Request Body
{
    "asset_name": "ThinkPad X1 Carbon",
    "asset_purchase_price": 12999.00,
    "asset_purchase_number": 5,
    "asset_unit": "台",
    "asset_brand": "Lenovo",
    "asset_specification": "i7/16GB/512GB",
    "asset_type_code": "REC-20260101-XXXXXXXX",
    "asset_contract_code": "REC-20260201-XXXXXXXX",
    "asset_purchase_date": "2026-06-01",
    "asset_warranty_period": 3,
    "asset_entry_date": "2026-06-12",
    "asset_storage_code": "REC-20260301-XXXXXXXX"
}

// Response 201
{
    "code": 200,
    "msg": "创建成功，共创建 5 条资产记录",
    "data": [
        {
            "asset_recordcode": "Entry20260612103045A1B2C3D4",
            "asset_code": "ASSET-hardware-ZDDN-20260612-A3B7C2-0001",
            "asset_name": "ThinkPad X1 Carbon",
            "asset_purchase_price": "12999.00",
            "asset_current_status": "in_store",
            "asset_brand": "Lenovo"
        },
        // ... 其他4条记录
    ]
}
```

#### 资产编码格式
```
ASSET-{分类类型}-{类型编码}-{日期}-{随机6位}-{序号4位}

示例: ASSET-hardware-ZDDN-20260612-A3B7C2-0001
      ↑         ↑        ↑       ↑        ↑     ↑
    前缀    硬件分类   类型编码  日期    随机字符  序号
```

### 4.9 出库管理接口 (assetmanagement/out-assets)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/out-assets/` | 出库列表 | Bearer |
| POST | `/api/assets/out-assets/` | 创建出库 | Bearer |
| GET | `/api/assets/out-assets/{code}/` | 出库详情 | Bearer |
| PUT | `/api/assets/out-assets/{code}/` | 更新出库 | Bearer |
| DELETE | `/api/assets/out-assets/{code}/` | 删除出库(回滚) | Bearer |
| POST | `/api/assets/out-assets/batch-create/` | 批量出库 | Bearer+Admin |
| POST | `/api/assets/out-assets/batch-delete/` | 批量删除(回滚) | Bearer+Admin |
| GET | `/api/assets/out-assets/statistics/` | 出库统计 | Bearer |
| GET | `/api/assets/out-assets/recyclable/` | 可回收资产列表 | Bearer |
| GET | `/api/assets/out-assets/by-asset/{code}/` | 按资产查出库记录 | Bearer |
| GET | `/api/assets/out-assets/by-applicant/{code}/` | 按申请人查出库记录 | Bearer |

#### 创建出库请求示例
**POST** `/api/assets/out-assets/`
```json
// Request Body
{
    "outasset_code": "Entry20260612103045A1B2C3D4",
    "outasset_number": 1,
    "outasset_date": "2026-06-12",
    "outasset_type": "receive",
    "outasset_applicant_jobcode": "REC-20260101-YYYYYYYY",
    "outasset_manager_jobcode": "REC-20260101-ZZZZZZZZ",
    "outasset_using_location": "技术部办公室"
}

// Response 201
{
    "code": 200,
    "msg": "出库成功",
    "data": {
        "outasset_recordcode": "OUT-20260612-A3B7C2D4",
        "outasset_code": "ASSET-hardware-ZDDN-20260612-A3B7C2-0001",
        "outasset_number": 1,
        "outasset_date": "2026-06-12",
        "outasset_type": "receive",
        "outasset_previous_status": "in_store"
    }
}
```

### 4.10 回收管理接口 (assetmanagement/recycle-assets)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/recycle-assets/` | 回收列表 | Bearer |
| POST | `/api/assets/recycle-assets/` | 创建回收 | Bearer |
| GET | `/api/assets/recycle-assets/{code}/` | 回收详情 | Bearer |
| DELETE | `/api/assets/recycle-assets/{code}/` | 删除回收(回滚) | Bearer |
| POST | `/api/assets/recycle-assets/batch-create/` | 批量回收 | Bearer+Admin |
| POST | `/api/assets/recycle-assets/batch-delete/` | 批量删除(回滚) | Bearer+Admin |

#### 创建回收请求示例
**POST** `/api/assets/recycle-assets/`
```json
// Request Body
{
    "outasset_recordcode": "OUT-20260612-A3B7C2D4",
    "recycle_asset_number": 1,
    "recycle_asset_date": "2026-06-15",
    "recycle_asset_storage_code": "REC-20260301-XXXXXXXX",
    "recycle_asset_recycle_person_jobcode": "REC-20260101-YYYYYYYY"
}

// Response 201
{
    "code": 200,
    "msg": "回收成功",
    "data": {
        "recycle_record_code": "RECYCLE-20260615-A3B7C2D4",
        "outasset_recordcode": "OUT-20260612-A3B7C2D4",
        "recycle_asset_number": 1,
        "recycle_asset_date": "2026-06-15"
    }
}
```

### 4.11 报废管理接口 (assetmanagement/damaged-assets)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/damaged-assets/` | 待报废列表 | Bearer |
| POST | `/api/assets/damaged-assets/` | 提交报废申请 | Bearer |
| GET | `/api/assets/damaged-assets/{code}/` | 报废详情 | Bearer |
| POST | `/api/assets/damaged-assets/{code}/approve/` | 审批通过 | Bearer+Admin |
| POST | `/api/assets/damaged-assets/{code}/reject/` | 审批拒绝 | Bearer+Admin |
| POST | `/api/assets/damaged-assets/{code}/cancel/` | 取消申请 | Bearer |
| DELETE | `/api/assets/damaged-assets/{code}/` | 删除(回滚) | Bearer |

### 4.12 已报废接口 (assetmanagement/waste-assets)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/waste-assets/` | 已报废列表 | Bearer |
| GET | `/api/assets/waste-assets/{code}/` | 报废详情 | Bearer |

### 4.13 硬盘序列号接口 (assetmanagement/harddisk-sn)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/harddisk-sn/` | 硬盘列表 | Bearer |
| POST | `/api/assets/harddisk-sn/batch-save/` | 批量保存 | Bearer |
| GET | `/api/assets/harddisk-sn/{code}/` | 硬盘详情 | Bearer |

### 4.14 操作日志接口 (assetmanagement/operation-logs)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/assets/operation-logs/` | 操作日志列表 | Bearer |
| GET | `/api/assets/operation-logs/{id}/` | 日志详情 | Bearer |
| GET | `/api/assets/operation-logs/by-logging-id/{id}/` | 按日志ID查询 | Bearer |
| GET | `/api/assets/operation-logs/recent/` | 最近日志 | Bearer |
| GET | `/api/assets/operation-logs/user/{jobcode}/` | 按操作人查询 | Bearer |
| GET | `/api/assets/assets/{code}/history/` | 资产操作历史 | Bearer |
| GET | `/api/assets/assets/{code}/timeline/` | 资产状态时间线 | Bearer |

### 4.15 仪表盘接口 (api/dashboard/)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/dashboard/statistics/` | 仪表盘统计数据 | Bearer |
| GET | `/api/dashboard/summary/` | 概览汇总 | Bearer |

### 4.16 未登记资产接口 (api/unregisteredassets/)

| 方法 | 地址 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/unregisteredassets/unregistered-assets/` | 列表 | Bearer |
| POST | `/api/unregisteredassets/unregistered-assets/` | 创建 | Bearer |
| GET | `/api/unregisteredassets/unregistered-assets/{code}/` | 详情 | Bearer |
| PUT | `/api/unregisteredassets/unregistered-assets/{code}/` | 更新 | Bearer |
| DELETE | `/api/unregisteredassets/unregistered-assets/{code}/` | 删除 | Bearer |
| POST | `/api/unregisteredassets/unregistered-assets/{code}/approve/` | 审批 | Bearer+Admin |

---

## 五、数据模型关系

```
Department ──1:N──→ Employee
    │                    │
    │                    │
Storage ◄──FK──── Asset ────FK──→ AssetType
    │              │    │
    │              │    └──FK──→ Contract
    │              │
    │              ├──FK──→ Employee (entry_person)
    │              ├──FK──→ Employee (applicant)
    │              └──FK──→ Employee (manager)
    │
    ├──1:N──→ OutAsset ────FK──→ Asset
    │              │
    │              └──1:1──→ RecycleAsset
    │
    ├──1:1──→ DamagedAsset ────FK──→ Asset
    │              │
    │              └──1:1──→ WasteAsset
    │
    └──1:N──→ HardDiskSN ────FK──→ Asset

AssetOperationLog (只读审计表)
    └── 通过 asset_code 关联 Asset

UnregisteredAsset
    ├──FK──→ Employee (discovery_person)
    ├──FK──→ AssetType
    ├──FK──→ Asset (related_asset)
    ├──FK──→ Storage (target_storage)
    └──FK──→ Employee (approver)
```

---

## 六、关键技术实现

### 6.1 认证机制

```
JWT Token 配置:
  - Access Token 有效期: 2小时
  - Refresh Token 有效期: 12小时
  - 启用 Token 轮换 (ROTATE_REFRESH_TOKENS)
  - 启用 Token 黑名单 (BLACKLIST_AFTER_ROTATION)
  - Token 黑名单存储: token_blacklist 应用

认证流程:
  1. POST /api/auth/login/ → 获取 access + refresh token
  2. 请求头携带: Authorization: Bearer {access_token}
  3. Token过期: POST /api/auth/token/refresh/ → 获取新 access_token
```

### 6.2 权限控制

```
权限层级:
  1. 全局: DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]
  2. 视图级: get_permissions() 根据 action 动态切换
  3. 对象级: check_object_permissions()

权限策略:
  - 读操作: IsAuthenticated
  - 写操作: IsAdminUser (管理员)
  - 批量操作: IsAdminUser (管理员)
  - 注册: AllowAny
```

### 6.3 性能优化

```
查询优化:
  - select_related: 预加载外键关联 (Asset→Type, Storage, Contract)
  - prefetch_related: 预加载反向关联 (Asset→HardDiskSN)
  - 自定义 QuerySet: for_list() 精简字段, with_all_relations() 完整关联

数据库优化:
  - 复合索引: (asset_type_code, asset_current_status)
  - 条件唯一约束: is_deleted=False 时唯一
  - 连接池: CONN_MAX_AGE=600, CONN_HEALTH_CHECKS=True

分页优化:
  - 自定义 CustomPageNumberPagination
  - 无参数时返回全部数据
  - 有参数时启用分页 (最大100条/页)
```

### 6.4 错误处理

```
异常体系:
  AppValidationError (400) - 数据验证失败
  NotFoundError (404) - 资源不存在
  PermissionDeniedError (403) - 权限不足
  BusinessLogicError (400) - 业务逻辑错误
  ResourceConflictError (409) - 资源冲突

全局异常处理:
  - DRF APIException 正常传播
  - 生产环境不暴露堆栈详情
  - 统一错误响应格式 {code, msg, data: {}}
```

---

## 七、部署配置

### 7.1 Docker 配置

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: asset_management_backend
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"

  web:
    build: .
    command: gunicorn config.wsgi:application
    ports:
      - "8000:8000"
    depends_on:
      - db
```

### 7.2 环境变量

```bash
# .env
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com
DB_NAME=asset_management_backend
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

---

## 八、开发规范 (AGENTS.md)

### 核心红线

1. **单一职责**: Service函数≤30行, View仅HTTP
2. **最小侵入**: 仅改任务范围, 禁止无关重构
3. **类型严格**: 全标注, 禁用Any
4. **可回退**: 一键回滚后mypy/ruff/test全过
5. **安全**: 输入Serializer全校验, ORM防注入
6. **绝对导入**: `from apps.xxx, core.xxx`, 禁相对
7. **统一返回**: `{"code":200,"msg":"","data":{}}`
8. **原子提交**: 每次Git提交只包含一个逻辑变更

### 开发流程

```
需求分析 → 方案设计 → 编码 → 测试 → 自检 → 文档
```

---

*报告结束*
