# 资产管理系统 - 项目文档

## 概述

本文档是资产管理系统的完整技术文档，包含数据模型、API接口、配置文件、基础设施等方面的详细说明。

### 项目架构

```
├── config/                    # 配置模块
│   ├── settings/              # Django设置（base/development/production/test）
│   ├── urls.py                # 主URL配置
│   ├── asgi.py                # ASGI入口
│   └── wsgi.py                # WSGI入口
├── apps/                      # 应用模块
│   ├── assetmanagement/       # 资产管理（核心模块）
│   ├── usermanagement/        # 用户管理
│   ├── authusermanagement/    # 认证管理
│   └── unregisteredasset/     # 未登记资产管理
├── core/                      # 核心模块（权限、异常、分页、常量）
├── utils/                     # 工具模块（响应工具、字符串工具）
├── .env                       # 环境变量配置
├── docker-compose.yml         # Docker Compose配置
└── Dockerfile                 # Docker镜像配置
```

---

## 一、数据模式与类型定义

### 1.1 数据库表结构

#### 1.1.1 资产管理模块

##### Asset（资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| asset_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 资产编码 |
| asset_name | VARCHAR(100) | NOT NULL | 资产名称 |
| asset_purchase_price | DECIMAL(10,2) | NOT NULL | 采购价格 |
| asset_purchase_date | DATE | NOT NULL | 购买日期 |
| asset_entry_date | DATE | NOT NULL | 入库日期 |
| asset_current_status | VARCHAR(20) | NOT NULL, INDEX | 资产状态 |
| asset_type_code | VARCHAR(20) | FOREIGN KEY | 资产类型编码 |
| asset_contract_code | VARCHAR(20) | FOREIGN KEY, NULL | 合同编码 |
| asset_storage_code | VARCHAR(20) | FOREIGN KEY, NULL | 仓库编码 |
| asset_brand | VARCHAR(100) | NULL | 品牌 |
| asset_specification | VARCHAR(100) | NULL | 规格型号 |

**资产状态枚举：**
| 状态码 | 显示名 | 说明 |
|--------|--------|------|
| `in_store` | 在库 | 新增加、已拒绝报废 |
| `recycled_pending` | 已回收待发放 | 已回收，等待重新发放 |
| `in_use` | 在用 | 已出库/已发放 |
| `damaged` | 待报废 | 待报废审批中 |
| `scrapped` | 已报废 | 已报废 |

##### Storage（仓库表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| storage_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 仓库编码 |
| storage_name | VARCHAR(100) | UNIQUE | 仓库名称 |
| storage_address | VARCHAR(200) | | 仓库地址 |
| storage_type | VARCHAR(50) | | 仓库类型 |

**仓库类型枚举：** `newasset`(新货仓库), `recycle`(回收仓库), `damaged`(待报废仓库)

##### AssetType（资产类型表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| asset_type_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 资产类型编码 |
| asset_type_secondary | VARCHAR(100) | | 二级分类名称 |
| asset_type_primary | VARCHAR(100) | | 一级分类名称 |
| asset_type_category | VARCHAR(50) | | 分类类型 |

**分类类型枚举：** `hardware`(硬件), `software`(软件), `lowvalue`(低值易耗), `other`(其他)

##### Contract（合同表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| contract_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 合同编码 |
| contract_name | VARCHAR(100) | UNIQUE | 合同名称 |
| contract_type | VARCHAR(50) | | 合同类型 |
| contract_price | DECIMAL(10,2) | NOT NULL | 合同金额 |
| contract_supplier | VARCHAR(100) | | 供应商 |
| contract_signing_date | DATE | | 签订日期 |
| contract_settlment_status | VARCHAR(20) | | 结算状态 |

##### OutAsset（出库资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| outasset_recordcode | VARCHAR(36) | PRIMARY KEY, UNIQUE | 出库记录编码 |
| outasset_code | VARCHAR(20) | FOREIGN KEY | 资产编码 |
| outasset_applicant_jobcode | VARCHAR(20) | FOREIGN KEY | 申请人工号 |
| outasset_manager_jobcode | VARCHAR(20) | FOREIGN KEY | 管理人工号 |
| outasset_current_status | VARCHAR(20) | | 当前状态 |
| outasset_date | DATE | | 出库日期 |
| outasset_type | VARCHAR(50) | | 出库类型 |

**出库类型枚举：** `receive`(领用), `borrow`(借用)

##### RecycleAsset（回收资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| outasset_recordcode | VARCHAR(36) | PRIMARY KEY | 出库记录编码 |
| recycle_asset_code | VARCHAR(20) | FOREIGN KEY | 回收资产编码 |
| recycle_asset_storage_code | VARCHAR(20) | FOREIGN KEY | 回收仓库编码 |
| recycle_asset_date | DATE | | 回收日期 |

##### DamagedAsset（待报废资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| damaged_asset_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 资产编码 |
| damaged_asset_storage_code | VARCHAR(20) | FOREIGN KEY | 仓库编码 |
| approval_status | VARCHAR(20) | | 审批状态 |
| approver | VARCHAR(20) | FOREIGN KEY | 审批人工号 |
| damaged_date | DATE | | 报废申请日期 |

**审批状态枚举：** `pending`(待审批), `approved`(已批准), `rejected`(已拒绝)

##### WasteAsset（已报废资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| waste_asset_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 资产编码 |
| waste_asset_contract_code | VARCHAR(20) | FOREIGN KEY | 合同编码 |
| waste_asset_date | DATE | | 报废日期 |
| source_damaged_asset | INT | FOREIGN KEY | 来源待报废记录 |

##### AssetOperationLog（操作记录表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | INT | PRIMARY KEY | 主键 |
| asset_code | VARCHAR(20) | INDEX | 资产编码 |
| operation_type | VARCHAR(20) | INDEX | 操作类型 |
| logging_id | VARCHAR(50) | UNIQUE, INDEX | 日志记录ID |
| operation_time | DATETIME | INDEX | 操作时间 |
| operator_jobcode | VARCHAR(20) | | 操作人工号 |
| operator_name | VARCHAR(100) | | 操作人姓名 |
| before_data | JSON | | 变更前数据 |
| after_data | JSON | | 变更后数据 |
| description | TEXT | | 操作描述 |
| related_record_code | VARCHAR(50) | | 关联记录编码 |

**操作类型枚举：** `create`, `update`, `delete`, `out`, `recycle`, `damaged`, `waste`, `approve`, `transfer`

#### 1.1.2 用户管理模块

##### Department（部门表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| department_code | VARCHAR(20) | PRIMARY KEY, UNIQUE | 部门编码 |
| department_name | VARCHAR(100) | UNIQUE | 部门名称 |
| parent_code | VARCHAR(20) | NULL | 上级部门编码 |
| level | INT | DEFAULT 0 | 部门层级 |
| sort_order | INT | DEFAULT 0 | 排序顺序 |

##### Employee（员工表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| employee_jobcode | VARCHAR(20) | PRIMARY KEY, UNIQUE | 员工工号 |
| employee_name | VARCHAR(100) | | 员工名称 |
| employee_status | VARCHAR(10) | | 员工状态 |
| employee_department | VARCHAR(20) | FOREIGN KEY | 所属部门 |
| employee_phone | VARCHAR(15) | UNIQUE | 员工电话 |
| sort_order | INT | DEFAULT 0 | 排序顺序 |

**员工状态枚举：** `active`(在职), `left`(离职), `retirement`(退休)

#### 1.1.3 认证管理模块

##### AuthUser（认证用户表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| auth_id | INT | PRIMARY KEY | 用户ID |
| auth_username | VARCHAR(150) | UNIQUE | 用户名 |
| email | VARCHAR(254) | UNIQUE, NULL | 邮箱 |
| password | VARCHAR(128) | | 密码(哈希) |
| auth_is_active | BOOLEAN | DEFAULT True | 是否激活 |
| auth_is_staff | BOOLEAN | DEFAULT False | 是否管理员 |
| auth_phone | VARCHAR(15) | UNIQUE | 联系电话 |

#### 1.1.4 未登记资产模块

##### UnregisteredAsset（未登记资产表）

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| unregistered_code | VARCHAR(32) | PRIMARY KEY, UNIQUE | 未登记资产编码 |
| scenario_type | VARCHAR(20) | | 场景类型 |
| discovery_date | DATE | | 发现日期 |
| discovery_location | VARCHAR(200) | | 发现地点 |
| discovery_person_jobcode | VARCHAR(20) | FOREIGN KEY | 发现人工号 |
| asset_name | VARCHAR(100) | | 资产名称 |
| related_asset_code | VARCHAR(20) | FOREIGN KEY, NULL | 关联资产编码 |
| handle_type | VARCHAR(30) | NULL | 处理方式 |
| approval_status | VARCHAR(20) | | 审批状态 |
| approver_jobcode | VARCHAR(20) | FOREIGN KEY, NULL | 审批人工号 |

**场景类型枚举：** `s1_no_record`(实物有系统无), `s2_no_outasset`(系统有无出库), `s3_status_mismatch`(状态异常)

**处理方式枚举：** `create_and_recycle`, `create_and_damaged`, `supplement_and_recycle`, `correct_and_recycle`, `reject`

---

## 二、API端点文档

### 2.1 认证管理 API

#### 2.1.1 用户注册

- **URL**: `POST /api/auth/register/`
- **描述**: 注册新用户账号
- **请求体**:
```json
{
  "auth_username": "string (必填)",
  "password": "string (必填)",
  "password2": "string (必填，确认密码)",
  "email": "string (可选)",
  "auth_phone": "string (可选)"
}
```
- **成功响应** (201):
```json
{
  "code": 201,
  "msg": "注册成功",
  "data": {
    "user": {
      "auth_id": 1,
      "auth_username": "testuser",
      "email": "test@example.com",
      "auth_is_active": true,
      "auth_is_staff": false
    },
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
  }
}
```

#### 2.1.2 用户登录

- **URL**: `POST /api/auth/login/`
- **描述**: 用户登录获取Token
- **请求体**:
```json
{
  "auth_username": "string (必填)",
  "password": "string (必填)"
}
```
- **成功响应** (200):
```json
{
  "code": 200,
  "msg": "登录成功",
  "data": {
    "user": { ... },
    "refresh": "string",
    "access": "string"
  }
}
```

#### 2.1.3 用户退出

- **URL**: `POST /api/auth/logout/`
- **描述**: 将refresh_token加入黑名单
- **请求体**:
```json
{
  "refresh": "string (必填)"
}
```

#### 2.1.4 获取用户信息

- **URL**: `GET /api/auth/profile/`
- **描述**: 获取当前登录用户信息
- **认证**: Bearer Token

#### 2.1.5 更新用户信息

- **URL**: `PUT /api/auth/profile/`
- **描述**: 更新当前用户信息
- **请求体**:
```json
{
  "email": "string (可选)",
  "auth_phone": "string (可选)",
  "password": "string (可选)"
}
```

#### 2.1.6 Token刷新

- **URL**: `POST /api/auth/token/refresh/`
- **描述**: 使用refresh_token获取新的access_token

#### 2.1.7 Token验证

- **URL**: `POST /api/auth/token/verify/`
- **描述**: 验证Token有效性

### 2.2 用户管理 API

#### 2.2.1 部门管理

| 方法 | URL | 描述 | 权限 |
|------|-----|------|------|
| GET | `/api/users/departments/` | 获取部门列表 | 认证用户 |
| POST | `/api/users/departments/` | 创建部门 | 管理员 |
| GET | `/api/users/departments/{code}/` | 获取部门详情 | 认证用户 |
| PUT | `/api/users/departments/{code}/` | 更新部门 | 管理员 |
| DELETE | `/api/users/departments/{code}/` | 删除部门 | 管理员 |
| GET | `/api/users/departments/tree/` | 获取部门树结构 | 认证用户 |
| GET | `/api/users/departments/{code}/path/` | 获取部门路径(面包屑) | 认证用户 |
| PUT | `/api/users/departments/{code}/move/` | 移动部门 | 管理员 |
| PUT | `/api/users/departments/sort/` | 批量排序部门 | 管理员 |

**部门列表响应**:
```json
{
  "code": 200,
  "msg": "success",
  "data": [
    {
      "department_code": "D001",
      "department_name": "总公司",
      "parent_code": null,
      "level": 0,
      "sort_order": 0
    }
  ]
}
```

#### 2.2.2 员工管理

| 方法 | URL | 描述 | 权限 |
|------|-----|------|------|
| GET | `/api/users/employees/` | 获取员工列表 | 认证用户 |
| POST | `/api/users/employees/` | 创建员工 | 管理员 |
| GET | `/api/users/employees/{jobcode}/` | 获取员工详情 | 认证用户 |
| PUT | `/api/users/employees/{jobcode}/` | 更新员工 | 管理员 |
| DELETE | `/api/users/employees/{jobcode}/` | 删除员工 | 管理员 |
| GET | `/api/users/employees/search?keyword=xxx` | 全局搜索员工 | 认证用户 |
| GET | `/api/users/employees/statistics/` | 获取员工统计 | 认证用户 |
| POST | `/api/users/employees/{jobcode}/change_status/` | 更改员工状态 | 管理员 |

**员工创建请求体**:
```json
{
  "employee_jobcode": "string (必填, 唯一)",
  "employee_name": "string (必填)",
  "employee_status": "string (active/left/retirement)",
  "employee_department": "string (部门编码)",
  "employee_phone": "string (必填, 唯一)",
  "employee_location": "string",
  "employee_description": "string",
  "sort_order": "integer"
}
```

### 2.3 资产管理 API

#### 2.3.1 仓库管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/storages/` | 获取仓库列表 |
| POST | `/api/assets/storages/` | 创建仓库 |
| GET | `/api/assets/storages/{code}/` | 获取仓库详情 |
| PUT | `/api/assets/storages/{code}/` | 更新仓库 |
| DELETE | `/api/assets/storages/{code}/` | 删除仓库 |

#### 2.3.2 资产类型管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/asset-types/` | 获取资产类型列表 |
| POST | `/api/assets/asset-types/` | 创建资产类型 |
| GET | `/api/assets/asset-types/{code}/` | 获取资产类型详情 |
| PUT | `/api/assets/asset-types/{code}/` | 更新资产类型 |
| DELETE | `/api/assets/asset-types/{code}/` | 删除资产类型 |

#### 2.3.3 合同管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/contracts/` | 获取合同列表 |
| POST | `/api/assets/contracts/` | 创建合同 |
| GET | `/api/assets/contracts/{code}/` | 获取合同详情 |
| PUT | `/api/assets/contracts/{code}/` | 更新合同 |
| DELETE | `/api/assets/contracts/{code}/` | 删除合同 |
| GET | `/api/assets/contracts/search?keyword=xxx` | 搜索合同 |
| POST | `/api/assets/contracts/{code}/update_settlement_status/` | 更新结算状态 |
| POST | `/api/assets/contracts/{code}/payment_record/` | 添加付款记录 |

#### 2.3.4 资产管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/assets/` | 获取资产列表 |
| POST | `/api/assets/assets/` | 创建资产 |
| GET | `/api/assets/assets/{code}/` | 获取资产详情 |
| PUT | `/api/assets/assets/{code}/` | 更新资产 |
| DELETE | `/api/assets/assets/{code}/` | 删除资产 |
| GET | `/api/assets/assets/search?keyword=xxx` | 搜索资产 |
| GET | `/api/assets/assets/statistics/` | 获取资产统计 |
| POST | `/api/assets/assets/{code}/change_status/` | 变更资产状态 |
| GET | `/api/assets/assets/{code}/history/` | 获取资产操作历史 |
| GET | `/api/assets/assets/{code}/timeline/` | 获取资产状态时间线 |

**资产创建请求体**:
```json
{
  "asset_code": "string (必填, 唯一)",
  "asset_name": "string (必填)",
  "asset_purchase_price": "decimal (必填)",
  "asset_purchase_date": "date (必填, YYYY-MM-DD)",
  "asset_entry_date": "date (必填, YYYY-MM-DD)",
  "asset_type_code": "string (必填)",
  "asset_contract_code": "string (可选)",
  "asset_storage_code": "string (可选)",
  "asset_brand": "string (可选)",
  "asset_specification": "string (可选)",
  "asset_warranty_period": "integer (可选)",
  "asset_entry_person_jobcode": "string (可选)",
  "asset_applicant_jobcode": "string (可选)",
  "asset_manager_jobcode": "string (可选)",
  "asset_description": "string (可选)",
  "asset_using_location": "string (可选)"
}
```

#### 2.3.5 出库管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/out-assets/` | 获取出库记录列表 |
| POST | `/api/assets/out-assets/` | 创建出库记录 |
| GET | `/api/assets/out-assets/{recordcode}/` | 获取出库记录详情 |
| PUT | `/api/assets/out-assets/{recordcode}/` | 更新出库记录 |
| DELETE | `/api/assets/out-assets/{recordcode}/` | 删除出库记录 |
| GET | `/api/assets/out-assets/recyclable/` | 获取可回收资产 |
| GET | `/api/assets/out-assets/by-asset/{code}/` | 按资产查出库记录 |
| GET | `/api/assets/out-assets/by-applicant/{jobcode}/` | 按申请人查出库记录 |

**出库创建请求体**:
```json
{
  "outasset_code": "string (资产编码，必填)",
  "outasset_number": "integer (数量，默认1)",
  "outasset_applicant_jobcode": "string (申请人工号)",
  "outasset_manager_jobcode": "string (管理人工号，必填)",
  "outasset_using_location": "string (使用地点，必填)",
  "outasset_type": "string (receive/borrow)",
  "return_date": "date (归还日期，可选)",
  "outasset_description": "string (说明，可选)"
}
```

#### 2.3.6 回收管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/recycle-assets/` | 获取回收记录列表 |
| POST | `/api/assets/recycle-assets/` | 创建回收记录 |
| GET | `/api/assets/recycle-assets/{recordcode}/` | 获取回收记录详情 |

**回收创建请求体**:
```json
{
  "outasset_recordcode": "string (出库记录编码，必填)",
  "recycle_asset_code": "string (资产编码)",
  "recycle_asset_storage_code": "string (仓库编码，必填)",
  "recycle_asset_recycle_person_jobcode": "string (回收人工号，必填)",
  "recycle_asset_date": "date (回收日期，必填)",
  "recycle_asset_description": "string (说明，可选)"
}
```

#### 2.3.7 报废管理

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/damaged-assets/` | 获取待报废列表 |
| POST | `/api/assets/damaged-assets/` | 创建待报废申请 |
| GET | `/api/assets/damaged-assets/{code}/` | 获取待报废详情 |
| DELETE | `/api/assets/damaged-assets/{code}/` | 取消待报废申请 |
| POST | `/api/assets/damaged-assets/{code}/approve/` | 审批通过 |
| POST | `/api/assets/damaged-assets/{code}/reject/` | 拒绝审批 |

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/waste-assets/` | 获取已报废列表 |
| GET | `/api/assets/waste-assets/{code}/` | 获取已报废详情 |

#### 2.3.8 操作日志 API

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/assets/operation-logs/` | 查询操作记录列表 |
| GET | `/api/assets/operation-logs/{pk}/` | 获取操作记录详情 |
| GET | `/api/assets/operation-logs/by-logging-id/{id}/` | 通过LoggingId查询 |
| GET | `/api/assets/operation-logs/recent/?days=7` | 获取最近操作记录 |
| GET | `/api/assets/operation-logs/user/{jobcode}/` | 获取用户操作记录 |

**操作日志查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| asset_code | string | 资产编码（精确匹配） |
| operation_type | string | 操作类型 |
| operator_jobcode | string | 操作人工号 |
| start_date | date | 开始日期 |
| end_date | date | 结束日期 |
| days | integer | 最近N天（与日期范围互斥） |

### 2.4 未登记资产管理 API

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/unregisteredassets/unregistered-assets/` | 获取列表 |
| POST | `/api/unregisteredassets/unregistered-assets/` | 创建记录 |
| GET | `/api/unregisteredassets/unregistered-assets/{code}/` | 获取详情 |
| PUT | `/api/unregisteredassets/unregistered-assets/{code}/` | 更新记录 |
| DELETE | `/api/unregisteredassets/unregistered-assets/{code}/` | 删除记录 |
| POST | `/api/unregisteredassets/unregistered-assets/{code}/approve/` | 审批处理 |

**创建请求体**:
```json
{
  "scenario_type": "string (s1_no_record/s2_no_outasset/s3_status_mismatch)",
  "discovery_date": "date (必填)",
  "discovery_location": "string (必填)",
  "asset_name": "string (必填)",
  "asset_brand": "string (可选)",
  "asset_specification": "string (可选)",
  "asset_type_code": "string (可选)",
  "estimated_value": "decimal (可选)",
  "related_asset_code": "string (S2/S3场景必填)",
  "target_storage_code": "string (可选)",
  "handle_description": "string (可选)",
  "attachments": "array (可选)"
}
```

**审批请求体**:
```json
{
  "handle_type": "string (必填)",
  "approval_remark": "string (可选)"
}
```

**处理方式选项**:
- `create_and_recycle`: 新建资产并回收
- `create_and_damaged`: 新建资产并报废
- `supplement_and_recycle`: 补建记录并回收
- `correct_and_recycle`: 修正状态并回收
- `reject`: 拒绝处理

### 2.5 仪表盘 API

| 方法 | URL | 描述 |
|------|-----|------|
| GET | `/api/dashboard/` | 获取仪表盘统计数据 |

---

## 三、配置与环境文件

### 3.1 .env 文件

```ini
# Django 设置
DJANGO_SETTINGS_MODULE=config.settings.development
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# 数据库配置
DB_NAME=asset_management_backend
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=3306

# CORS 配置
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# JWT 配置（可选）
ACCESS_TOKEN_LIFETIME=2
REFRESH_TOKEN_LIFETIME=336
```

### 3.2 Django 设置说明

#### 3.2.1 核心配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `AUTH_USER_MODEL` | 自定义用户模型 | `authusermanagement.AuthUser` |
| `DEFAULT_AUTO_FIELD` | 默认主键类型 | `BigAutoField` |
| `TIME_ZONE` | 时区 | `Asia/Shanghai` |

#### 3.2.2 REST Framework 配置

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication'
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.CustomPageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}
```

#### 3.2.3 JWT 配置

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(hours=12),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

#### 3.2.4 CORS 配置

```python
CORS_ALLOWED_ORIGINS = [...]  # 生产环境应限制为具体域名
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
```

### 3.3 数据库配置

使用 MySQL 数据库：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}
```

---

## 四、基础设施与部署

### 4.1 Docker Compose

#### 服务定义

```yaml
services:
  # Django 应用服务
  web:
    build: .
    container_name: asset-management-web
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=${DB_NAME:-asset_management_backend}
      - DB_USER=${DB_USER:-root}
      - DB_PASSWORD=${DB_PASSWORD:-}
      - DJANGO_SETTINGS_MODULE=config.settings.production
      - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
      - DEBUG=${DEBUG:-False}
    volumes:
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    depends_on:
      mysql:
        condition: service_healthy
    networks:
      - asset-network

  # MySQL 数据库服务
  mysql:
    image: mysql:8.0
    container_name: asset-management-mysql
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-rootpassword}
      - MYSQL_DATABASE=${DB_NAME:-asset_management_backend}
      - MYSQL_USER=${DB_USER:-asset_user}
      - MYSQL_PASSWORD=${DB_PASSWORD:-assetpassword}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    networks:
      - asset-network

volumes:
  mysql_data:
  static_volume:
  media_volume:

networks:
  asset-network:
    driver: bridge
```

### 4.2 Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/base.txt /app/requirements/base.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements/base.txt

COPY . /app/

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "config.wsgi:application"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1
```

### 4.3 CI/CD 流程

#### GitHub Actions 配置

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    name: Code Linting
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy apps core config utils

  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: lint
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: rootpassword
          MYSQL_DATABASE: asset_management_test
        ports:
          - 3306:3306
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements/dev.txt
      - run: python manage.py migrate --settings=config.settings.test
      - run: python manage.py test --settings=config.settings.test

  docker:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/asset-management-backend:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/asset-management-backend:${{ github.sha }}
```

---

## 五、测试与模拟数据

### 5.1 测试文件结构

```
apps/
├── assetmanagement/tests/
│   ├── conftest.py      # pytest 配置
│   ├── test_models.py   # 模型测试
│   ├── test_selectors.py# 选择器测试
│   ├── test_services.py # 服务层测试
│   └── test_operation_log.py # 操作日志测试
├── usermanagement/tests/
│   ├── conftest.py
│   └── test_services.py
├── authusermanagement/tests/
│   ├── conftest.py
│   └── test_services.py
└── unregisteredasset/tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_selectors.py
    ├── test_services.py
    └── test_api.py
```

### 5.2 测试配置

```python
# config/settings/test.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='asset_management_test'),
        'USER': config('DB_USER', default='root'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='3306'),
    }
}

DEBUG = True
```

### 5.3 运行测试

```bash
# 运行所有测试
python manage.py test --settings=config.settings.test

# 运行特定应用的测试
python manage.py test apps.assetmanagement.tests --settings=config.settings.test

# 使用 pytest（如果配置了）
pytest apps/assetmanagement/tests/
```

---

## 六、项目入口与路由

### 6.1 URL 路由总览

```
/                              → API根路径信息
/admin/                        → Django Admin
/api/auth/                     → 认证管理
/api/users/                    → 用户管理
/api/assets/                   → 资产管理
/api/unregisteredassets/       → 未登记资产管理
/api/dashboard/                → 仪表盘
/api/schema/                   → OpenAPI Schema
/api/swagger/                  → Swagger UI
/api/redoc/                    → ReDoc UI
```

### 6.2 主路由配置

```python
# config/urls.py
urlpatterns = [
    path('', api_root, name='api-root'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authusermanagement.urls')),
    path('api/users/', include('apps.usermanagement.urls')),
    path('api/assets/', include('apps.assetmanagement.urls')),
    path('api/unregisteredassets/', include('apps.unregisteredasset.urls')),
    path('api/dashboard/', include('apps.assetmanagement.dashboard_urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
```

### 6.3 路由模块划分

| 模块 | 路径前缀 | 视图集 |
|------|----------|--------|
| 认证管理 | `/api/auth/` | AuthUserViewSet |
| 部门管理 | `/api/users/departments/` | DepartmentViewSet |
| 员工管理 | `/api/users/employees/` | EmployeeViewSet |
| 仓库管理 | `/api/assets/storages/` | StorageViewSet |
| 资产类型 | `/api/assets/asset-types/` | AssetTypeViewSet |
| 合同管理 | `/api/assets/contracts/` | ContractViewSet |
| 资产管理 | `/api/assets/assets/` | AssetViewSet |
| 出库管理 | `/api/assets/out-assets/` | OutAssetViewSet |
| 回收管理 | `/api/assets/recycle-assets/` | RecycleAssetViewSet |
| 报废管理 | `/api/assets/damaged-assets/` | DamagedAssetViewSet |
| 已报废 | `/api/assets/waste-assets/` | WasteAssetViewSet |
| 仪表盘 | `/api/dashboard/` | DashboardViewSet |

---

## 七、统一响应格式

### 7.1 成功响应

```json
{
  "code": 200,
  "msg": "success",
  "data": { ... }
}
```

### 7.2 分页响应

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "count": 100,
    "results": [...],
    "next": "http://...?page=2",
    "previous": null
  }
}
```

### 7.3 错误响应

```json
{
  "code": 400,
  "msg": "错误描述",
  "errors": {
    "field_name": ["错误信息"]
  }
}
```

### 7.4 HTTP 状态码对照表

| 状态码 | 含义 | 使用场景 |
|--------|------|----------|
| 200 | 成功 | 查询、更新、删除成功 |
| 201 | 创建成功 | 创建资源 |
| 400 | 请求参数错误 | 参数校验失败 |
| 401 | 未认证 | Token无效或未提供 |
| 403 | 无权限 | 权限不足 |
| 404 | 资源不存在 | 查询的资源不存在 |
| 500 | 服务器错误 | 服务端内部错误 |

---

## 八、安全规范

### 8.1 认证机制

- 使用 JWT Token 认证
- Access Token 有效期：2小时
- Refresh Token 有效期：12小时
- 支持 Token 黑名单（退出登录时加入黑名单）

### 8.2 权限控制

| 操作 | 权限要求 |
|------|----------|
| 查看数据 | 认证用户 |
| 创建/更新/删除 | 管理员 |
| 用户管理 | 管理员 |
| 部门管理 | 管理员 |

### 8.3 安全最佳实践

1. **密码安全**：使用 PBKDF2_SHA256 哈希算法存储密码
2. **敏感信息保护**：禁止通过API返回密码等敏感字段
3. **输入验证**：所有用户输入必须经过验证
4. **SQL注入防护**：使用Django ORM，避免原生SQL
5. **CORS配置**：生产环境限制允许的来源
6. **CSRF防护**：使用Django内置CSRF保护
7. **日志审计**：所有操作记录到操作日志表

---

## 九、附录

### 9.1 状态流转图

```
资产状态流转：
[in_store] ──出库──→ [in_use]
     ↑                   │
     │                   │
    拒绝报废            回收/报废申请
     │                   │
     │                   ↓
[recycled_pending] ←─── [damaged]
     │                   │
     │                   ↓
    出库               [scrapped]
```

### 9.2 未登记资产场景说明

| 场景 | 标识 | 说明 | 处理方式 |
|------|------|------|----------|
| S1 | s1_no_record | 实物有系统无 | 创建新资产并回收/报废 |
| S2 | s2_no_outasset | 系统有无出库 | 补建出库记录并回收 |
| S3 | s3_status_mismatch | 状态异常 | 修正状态并回收 |

### 9.3 API 文档访问

- Swagger UI: `http://localhost:8000/api/swagger/`
- ReDoc: `http://localhost:8000/api/redoc/`
- OpenAPI Schema: `http://localhost:8000/api/schema/`

---

**文档版本**: 1.0.0  
**生成日期**: 2026-05-27  
**项目版本**: v1.0.0