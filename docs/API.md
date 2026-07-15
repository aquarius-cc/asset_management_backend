# 资产管理系统 API 接口文档

> 共 **164 个接口** | 统一响应格式：`{code, msg, data}` | 权限：读操作 `IsAuthenticated`，写操作 `IsAdminUser`

---

## 系统基础模块

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/` | API 根路径信息 | 无 | {message, version, docs, admin} | 无 |
| GET | `/health/` | 健康检查 | 无 | {status, database, version} | 无 |
| GET | `/admin/` | Django Admin 后台 | 无 | Admin 页面 | Staff |

---

## 文档模块（drf-spectacular）

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/schema/` | OpenAPI Schema 数据 | ?format (json/yaml) | OpenAPI JSON/YAML | 无 |
| GET | `/api/swagger/` | Swagger UI 文档页 | 无 | HTML 页面 | 无 |
| GET | `/api/redoc/` | ReDoc 文档页 | 无 | HTML 页面 | 无 |

---

## 认证模块 (`apps/authusermanagement`) — 前缀 `/api/auth/`

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| POST | `/api/auth/register/` | 用户注册 | Body: {auth_username, password, email, auth_phone} | {user, refresh, access} | AllowAny |
| POST | `/api/auth/login/` | 用户登录 | Body: {auth_username, password} | {user, refresh, access} | AllowAny |
| POST | `/api/auth/logout/` | 退出登录（Token 黑名单） | Body: {refresh} | {} | 认证 |
| GET | `/api/auth/profile/` | 获取当前用户信息 | 无 | AuthUser 字段 | 认证 |
| PUT | `/api/auth/profile/` | 更新当前用户信息 | Body: {email, auth_phone} | AuthUser 字段 | 认证 |
| POST | `/api/auth/token/refresh/` | 刷新 JWT Token | Body: {refresh} | {access} | AllowAny |
| POST | `/api/auth/token/verify/` | 验证 JWT Token | Body: {token} | {} | AllowAny |
| GET | `/api/auth/users/` | 用户列表 | ?page, ?page_size | {count, results} | 管理员 |
| POST | `/api/auth/users/` | 创建用户 | Body: RegisterSerializer 字段 | {user, refresh, access} | AllowAny |
| GET | `/api/auth/users/{auth_id}/` | 用户详情 | 路径: auth_id | AuthUser 字段 | 管理员 |
| PUT | `/api/auth/users/{auth_id}/` | 更新用户 | Body: AuthUser 字段 | AuthUser 字段 | 认证（本人或管理员） |
| PATCH | `/api/auth/users/{auth_id}/` | 部分更新用户 | Body: 部分字段 | AuthUser 字段 | 认证（本人或管理员） |
| DELETE | `/api/auth/users/{auth_id}/` | 删除用户 | 路径: auth_id | - | 认证（本人或管理员） |
| GET | `/api/auth/users/list_active/` | 获取所有激活用户 | ?page, ?page_size | {count, results} | 管理员 |

---

## 用户管理模块 (`apps/usermanagement`) — 前缀 `/api/users/`

### 部门管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/users/departments/` | 部门列表 | ?page, ?page_size, ?search, ?ordering | {count, results} | 认证 |
| POST | `/api/users/departments/` | 创建部门 | Body: DepartmentSerializer 字段 | Department 字段 | 管理员 |
| GET | `/api/users/departments/{department_code}/` | 部门详情 | 路径: department_code | Department 字段 | 认证 |
| PUT | `/api/users/departments/{department_code}/` | 更新部门 | Body: DepartmentSerializer 字段 | Department 字段 | 管理员 |
| PATCH | `/api/users/departments/{department_code}/` | 部分更新部门 | Body: 部分字段 | Department 字段 | 管理员 |
| DELETE | `/api/users/departments/{department_code}/` | 删除部门 | 路径: department_code | - | 管理员 |
| GET | `/api/users/departments/tree/` | 获取部门树 | 无 | [{department_code, children, employee_count}] | 认证 |
| GET | `/api/users/departments/{department_code}/employees/` | 获取部门员工 | 路径: department_code; ?status (active/left/retirement) | {department, employees_count, employees} | 认证 |
| GET | `/api/users/departments/{department_code}/children/` | 获取子部门 | 路径: department_code | {parent, children_count, children} | 认证 |
| GET | `/api/users/departments/{department_code}/path/` | 获取部门路径（面包屑） | 路径: department_code | {current, path, depth} | 认证 |
| GET | `/api/users/departments/{department_code}/descendants/` | 获取所有后代部门 | 路径: department_code | {current, descendants_count, descendants} | 认证 |
| PUT | `/api/users/departments/{department_code}/move/` | 移动部门 | Body: {target_parent_department_code} | Department 字段 | 管理员 |
| GET | `/api/users/departments/{department_code}/parent/` | 获取父部门 | 路径: department_code | {recordcode, department_code, department_name, level, parent_department_code, path} | 认证 |
| PUT | `/api/users/departments/sort/` | 批量排序 | Body: {items: [{department_code, sort_order}]} | {updated_count} | 管理员 |
| POST | `/api/users/departments/batch-create/` | 批量创建部门 | Body: {items: [...]} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/users/departments/batch-delete/` | 批量删除部门 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

### 员工管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/users/employees/` | 员工列表 | ?page, ?page_size, ?search, ?employee_status, ?employee_department__department_code | {count, results} | 认证 |
| POST | `/api/users/employees/` | 创建员工 | Body: EmployeeCreateSerializer 字段 | Employee 字段 | 管理员 |
| GET | `/api/users/employees/{employee_jobcode}/` | 员工详情 | 路径: employee_jobcode | EmployeeDetail 字段 | 认证 |
| PUT | `/api/users/employees/{employee_jobcode}/` | 更新员工 | Body: EmployeeUpdateSerializer 字段 | Employee 字段 | 管理员 |
| PATCH | `/api/users/employees/{employee_jobcode}/` | 部分更新员工 | Body: 部分字段 | Employee 字段 | 管理员 |
| DELETE | `/api/users/employees/{employee_jobcode}/` | 删除员工 | 路径: employee_jobcode | - | 管理员 |
| GET | `/api/users/employees/statistics/` | 员工统计 | 无 | {total, by_status, by_department} | 认证 |
| GET | `/api/users/employees/active_employees/` | 在职员工列表 | ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/users/employees/search/` | 全局模糊搜索员工 | ?keyword, ?page, ?page_size | {count, results} | 认证 |
| POST | `/api/users/employees/{employee_jobcode}/change_status/` | 更改员工状态 | Body: {status} | {message, employee} | 管理员 |
| GET | `/api/users/employees/employees/{employee_jobcode}/` | 根据工号查询员工 | 路径: employee_jobcode | EmployeeDetail 字段 | 认证 |
| POST | `/api/users/employees/batch-create/` | 批量创建员工 | Body: {items: [...]} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/users/employees/batch-delete/` | 批量删除员工 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |
| GET | `/api/users/employees/{employee_jobcode}/department/` | 根据工号查询所在部门 | 路径: employee_jobcode | {department_code, department_name, level, parent_code} | 认证 |
| PUT | `/api/users/employees/sort/` | 批量更新员工排序 | Body: {items: [{employee_jobcode, sort_order}]} | [Employee 字段] | 管理员 |

---

## 资产管理模块 (`apps/assetmanagement`) — 前缀 `/api/assets/`

### 仓库管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/storages/` | 仓库列表 | ?page, ?page_size, ?keyword, ?storage_type, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/storages/` | 创建仓库 | Body: StorageSerializer 字段 | Storage 字段 | 管理员 |
| GET | `/api/assets/storages/{storage_code}/` | 仓库详情 | 路径: storage_code 或 id | Storage 字段 | 认证 |
| PUT | `/api/assets/storages/{storage_code}/` | 更新仓库 | Body: StorageSerializer 字段 | Storage 字段 | 管理员 |
| PATCH | `/api/assets/storages/{storage_code}/` | 部分更新仓库 | Body: 部分字段 | Storage 字段 | 管理员 |
| DELETE | `/api/assets/storages/{storage_code}/` | 删除仓库（软删除） | 路径: storage_code | - | 管理员 |
| GET | `/api/assets/storages/statistics/` | 仓库统计 | 无 | {total_storages, by_type} | 认证 |
| POST | `/api/assets/storages/batch-delete/` | 批量删除仓库 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |
| POST | `/api/assets/storages/batch-create/` | 批量创建仓库 | Body: {items: [...]} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |

### 资产类型管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/asset-types/` | 资产类型列表 | ?page, ?page_size, ?search, ?asset_type_category, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/asset-types/` | 创建资产类型 | Body: AssetTypeSerializer 字段 | AssetType 字段 | 管理员 |
| GET | `/api/assets/asset-types/{asset_type_code}/` | 资产类型详情 | 路径: asset_type_code 或 id | AssetType 字段 | 认证 |
| PUT | `/api/assets/asset-types/{asset_type_code}/` | 更新资产类型 | Body: AssetTypeSerializer 字段 | AssetType 字段 | 管理员 |
| PATCH | `/api/assets/asset-types/{asset_type_code}/` | 部分更新资产类型 | Body: 部分字段 | AssetType 字段 | 管理员 |
| DELETE | `/api/assets/asset-types/{asset_type_code}/` | 删除资产类型（软删除） | 路径: asset_type_code | - | 管理员 |
| POST | `/api/assets/asset-types/batch-delete/` | 批量删除资产类型 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

### 合同管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/contracts/` | 合同列表 | ?page, ?page_size, ?contract_type, ?contract_settledment_status, ?ordering | ContractListSerializer | 认证 |
| POST | `/api/assets/contracts/` | 创建合同 | Body: ContractCreateSerializer 字段 | ContractDetailSerializer | 管理员 |
| GET | `/api/assets/contracts/{contract_code}/` | 合同详情 | 路径: contract_code 或 id | ContractDetailSerializer | 认证 |
| PUT | `/api/assets/contracts/{contract_code}/` | 更新合同 | Body: ContractUpdateSerializer 字段 | ContractDetailSerializer | 管理员 |
| PATCH | `/api/assets/contracts/{contract_code}/` | 部分更新合同 | Body: 部分字段 | ContractDetailSerializer | 管理员 |
| DELETE | `/api/assets/contracts/{contract_code}/` | 删除合同（软删除） | 路径: contract_code | - | 管理员 |
| GET | `/api/assets/contracts/statistics/` | 合同统计 | 无 | 合同统计数据 | 认证 |
| GET | `/api/assets/contracts/search/` | 全局模糊搜索合同 | ?keyword, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/contracts/getcontractByname/{name}/` | 按名称模糊查询合同 | 路径: name | {count, results} | 认证 |
| POST | `/api/assets/contracts/{contract_code}/update_settlement_status/` | 更新合同结算状态 | Body: {status} | {contract} | 管理员 |
| POST | `/api/assets/contracts/{contract_code}/payment_record/` | 添加付款记录 | Body: {amount, description} | {contract} | 管理员 |
| POST | `/api/assets/contracts/batch-delete/` | 批量删除合同 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

### 资产管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/assets/` | 资产列表 | ?page, ?page_size, ?search, ?asset_current_status, ?asset_type, ?asset_storage, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/assets/` | 创建资产 | Body: AssetCreateSerializer 字段 | AssetDetail 字段 | 管理员 |
| GET | `/api/assets/assets/{asset_code}/` | 资产详情 | 路径: asset_code 或 id | AssetDetail 字段 | 认证 |
| PUT | `/api/assets/assets/{asset_code}/` | 更新资产 | Body: AssetUpdateSerializer 字段 | AssetDetail 字段 | 管理员 |
| PATCH | `/api/assets/assets/{asset_code}/` | 部分更新资产 | Body: 部分字段 | AssetDetail 字段 | 管理员 |
| DELETE | `/api/assets/assets/{asset_code}/` | 删除资产（软删除） | 路径: asset_code | - | 管理员 |
| GET | `/api/assets/assets/statistics/` | 资产统计 | 无 | 资产统计数据 | 认证 |
| GET | `/api/assets/assets/search/` | 全局搜索资产 | ?keyword, ?status, ?asset_type, ?storage_code, ?contract_code, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/assets/search_available/` | 查询可用资产 | ?asset_code, ?asset_name, ?asset_specification, ?asset_brand, ?asset_contract_code, ?asset_contract_name, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/assets/getassetbyname/{name}/` | 按名称模糊查询资产 | 路径: name | {count, results} | 认证 |
| GET | `/api/assets/assets/getassetbyrecordcode/{recordcode}/` | 按记录编码查询资产 | 路径: recordcode | [Asset 字段] | 认证 |
| GET | `/api/assets/assets/combined_details/` | 资产综合详情 | ?asset_code | 综合资产数据 | 认证 |
| GET | `/api/assets/assets/contract_by_asset/{asset_code}/` | 通过资产编码查询关联合同 | 路径: asset_code | ContractDetail 字段 | 认证 |
| POST | `/api/assets/assets/{asset_code}/change_status/` | 变更资产状态 | Body: {status, description} | {asset} | 认证 |
| POST | `/api/assets/assets/{asset_code}/change_outasset_employee/` | 更新资产申请人和保管人 | Body: {applicant_jobcode, manager_jobcode} | {asset} | 认证 |
| POST | `/api/assets/assets/batch-create/` | 批量创建资产 | Body: {items: [AssetBatchItemSerializer]} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/assets/assets/batch-delete/` | 批量删除资产 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

#### 查询可用资产搜索参数说明（search_available）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `asset_code` | String | 否 | 资产编码（模糊匹配） |
| `asset_name` | String | 否 | 资产名称（模糊匹配） |
| `asset_specification` | String | 否 | 资产规格（模糊匹配） |
| `asset_brand` | String | 否 | 资产品牌（模糊匹配） |
| `asset_contract_code` | String | 否 | 合同编码（精确匹配） |
| `asset_contract_name` | String | 否 | 合同名称（模糊匹配） |
| `page` | Integer | 否 | 页码（默认1） |
| `page_size` | Integer | 否 | 每页数量（默认20） |

**说明**：
- 默认返回 `asset_current_status='in_store'` 或 `'recycled_pending'` 的资产
- 所有搜索参数均为可选，支持组合查询
- 无搜索参数时返回所有可用资产

#### 创建资产请求体字段说明（AssetCreateSerializer）

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `asset_name` | String | **是** | 资产名称 |
| `asset_type` | String | **是** | 资产类型编码（AssetType.asset_type_code） |
| `asset_purchase_price` | Decimal | **是** | 购买价格 |
| `asset_purchase_date` | Date | **是** | 购买日期（YYYY-MM-DD） |
| `asset_entry_date` | Date | **是** | 入库日期（YYYY-MM-DD） |
| `asset_contract` | String | 否 | 合同编码（Contract.contract_code） |
| `asset_storage` | String | 否 | 仓库编码（Storage.storage_code） |
| `asset_entry_person` | String | 否 | 入库人工号（Employee.employee_jobcode） |
| `asset_applicant` | String | 否 | 申请人工号（Employee.employee_jobcode） |
| `asset_manager` | String | 否 | 保管人工号（Employee.employee_jobcode） |
| `asset_purchase_number` | Integer | 否 | 购买数量（默认1）。**注意：会根据此数量创建多条资产记录，每条记录生成唯一 asset_code** |
| `asset_warranty_period` | Integer | 否 | 保修期（年，默认0） |
| `asset_current_status` | String | 否 | 资产状态（默认 "in_store"） |
| `asset_unit` | String | 否 | 资产单位 |
| `asset_brand` | String | 否 | 资产品牌 |
| `asset_specification` | String | 否 | 资产规格 |
| `asset_using_location` | String | 否 | 资产使用地点 |
| `asset_description` | String | 否 | 资产描述 |

#### 创建资产请求示例

```json
{
  "asset_name": "台式机-001",
  "asset_type": "AT001",
  "asset_purchase_price": 5000.00,
  "asset_purchase_date": "2026-06-27",
  "asset_entry_date": "2026-06-27",
  "asset_storage": "ST001",
  "asset_contract": "CT001",
  "asset_entry_person": "E001",
  "asset_brand": "联想",
  "asset_specification": "i7/16GB/512GB",
  "asset_unit": "台"
}
```

#### 批量创建资产请求体字段说明（AssetBatchItemSerializer）

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `row_number` | Integer | 否 | 行号，用于错误定位 |
| `asset_name` | String | **是** | 资产名称 |
| `asset_type` | String | **是** | 资产类型编码（AssetType.asset_type_code） |
| `asset_purchase_price` | Decimal | 否 | 购买价格 |
| `asset_purchase_date` | Date | 否 | 购买日期（YYYY-MM-DD） |
| `asset_entry_date` | Date | 否 | 入库日期（YYYY-MM-DD） |
| `asset_storage` | String | 否 | 仓库编码（Storage.storage_code） |
| `asset_contract` | String | 否 | 合同编码（Contract.contract_code） |
| `asset_purchase_number` | Integer | 否 | 购买数量（默认1，最小1）。**注意：会根据此数量为该 item 创建多条资产记录** |
| `asset_entry_person` | String | 否 | 入库人工号（Employee.employee_jobcode） |
| `asset_applicant` | String | 否 | 申请人工号（Employee.employee_jobcode） |
| `asset_manager` | String | 否 | 保管人工号（Employee.employee_jobcode） |
| `asset_specification` | String | 否 | 资产规格 |
| `asset_brand` | String | 否 | 资产品牌 |
| `asset_unit` | String | 否 | 资产单位 |
| `asset_warranty_period` | Integer | 否 | 保修期（年，默认0） |
| `asset_description` | String | 否 | 资产描述 |
| `asset_using_location` | String | 否 | 资产使用地点 |

#### 批量创建资产请求示例

```json
{
  "items": [
    {
      "asset_name": "台式机-001",
      "asset_type": "AT001",
      "asset_storage": "ST001",
      "asset_contract": "CT001",
      "asset_entry_person": "E001",
      "asset_applicant": "E002",
      "asset_manager": "E003",
      "asset_purchase_price": 5000.00,
      "asset_purchase_date": "2026-06-27",
      "asset_entry_date": "2026-06-27",
      "asset_brand": "联想",
      "asset_specification": "i7/16GB/512GB",
      "asset_unit": "台",
      "asset_warranty_period": 3,
      "asset_description": "办公用台式机",
      "asset_using_location": "北京办公室"
    }
  ]
}
```

### 出库管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/out-assets/` | 出库列表 | ?page, ?page_size, ?keyword, ?searchType, ?asset_current_status, ?outasset_type, ?ordering | OutAssetListSerializer | 认证 |
| POST | `/api/assets/out-assets/` | 创建出库记录 | Body: OutAssetCreateSerializer 字段 | OutAssetDetailSerializer | 管理员 |
| GET | `/api/assets/out-assets/{recordcode}/` | 出库详情 | 路径: recordcode | OutAssetDetailSerializer | 认证 |
| PUT | `/api/assets/out-assets/{recordcode}/` | 更新出库记录 | Body: OutAssetUpdateSerializer 字段 | OutAssetDetailSerializer | 管理员 |
| PATCH | `/api/assets/out-assets/{recordcode}/` | 部分更新出库记录 | Body: 部分字段 | OutAssetDetailSerializer | 管理员 |
| DELETE | `/api/assets/out-assets/{recordcode}/` | 删除出库记录（软删除） | 路径: recordcode | - | 管理员 |
| GET | `/api/assets/out-assets/statistics/` | 出库统计 | 无 | 出库统计数据 | 认证 |
| GET | `/api/assets/out-assets/recyclable/` | 可回收资产列表 | ?asset_code, ?asset_name, ?asset_specification, ?asset_brand, ?outasset_applicant_name, ?outasset_manager_name, ?department, ?department_code, ?employee_jobcode, ?search, ?searchType, ?years, ?ordering, ?page, ?page_size | OutAssetListSerializer | 认证 |
| GET | `/api/assets/out-assets/by-asset/{asset_code}/` | 按资产编码查询出库记录 | 路径: asset_code | OutAssetListSerializer | 认证 |
| GET | `/api/assets/out-assets/by-applicant/{applicant_jobcode}/` | 按申请人工号查询出库记录 | 路径: applicant_jobcode | OutAssetListSerializer | 认证 |
| POST | `/api/assets/out-assets/batch-create/` | 批量创建出库记录 | Body: {items: [...]} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/assets/out-assets/batch-delete/` | 批量删除出库记录 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

#### 可回收资产搜索参数说明（recyclable）

| 参数 | 类型 | 匹配方式 | 说明 |
|------|------|----------|------|
| `asset_code` | String | 模糊匹配 | 资产编码 |
| `asset_name` | String | 模糊匹配 | 资产名称 |
| `asset_specification` | String | 模糊匹配 | 资产规格 |
| `asset_brand` | String | 模糊匹配 | 资产品牌 |
| `outasset_applicant_name` | String | 模糊匹配 | 申请人姓名 |
| `outasset_manager_name` | String | 模糊匹配 | 保管人姓名 |
| `department` | String | 模糊匹配 | 部门名称 |
| `department_code` | String | 精确匹配 | 部门编码 |
| `employee_jobcode` | String | 精确匹配 | 员工工号 |
| `search` | String | 模糊搜索 | 关键词搜索（资产+用户） |
| `searchType` | String | - | 搜索类型：asset/user/all |
| `years` | Integer | - | 出库时长（年数） |
| `ordering` | String | - | 排序字段 |
| `page` | Integer | - | 页码（默认1） |
| `page_size` | Integer | - | 每页数量（默认20） |

**说明**：
- 默认返回 `asset_current_status='in_use'` 且未回收的资产
- 所有搜索参数均为可选，支持组合查询
- 前端可灵活调整搜索参数，后端通过 `RECYCLABLE_FILTER_CONFIG` 配置自动支持

### 回收资产管理

> 【AGENTS 规范 - 序列化器分层】每个 Action 使用专用序列化器：
> - **ListSerializer**: 列表查询（扁平字段，只读）
> - **CreateSerializer**: 创建/更新（写入字段）
> - **DetailSerializer**: 详情查询（嵌套对象，只读）

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/recycle-assets/` | 回收列表 | ?page, ?page_size, ?search, ?recycle_date_from, ?recycle_date_to, ?ordering | RecycleAssetListSerializer | 认证 |
| POST | `/api/assets/recycle-assets/` | 创建回收记录 | Body: RecycleAssetCreateSerializer 字段 | RecycleAssetDetailSerializer | 管理员 |
| GET | `/api/assets/recycle-assets/{recordcode}/` | 回收详情 | 路径: recordcode 或 id | RecycleAssetDetailSerializer | 认证 |
| PUT | `/api/assets/recycle-assets/{recordcode}/` | 更新回收记录 | Body: RecycleAssetUpdateSerializer 字段 | RecycleAssetDetailSerializer | 管理员 |
| DELETE | `/api/assets/recycle-assets/{recordcode}/` | 删除回收记录（软删除） | 路径: recordcode | - | 管理员 |
| GET | `/api/assets/recycle-assets/by-asset/{recycle_asset_code}/` | 按资产编码查询回收记录 | 路径: recycle_asset_code | RecycleAssetListSerializer | 认证 |
| GET | `/api/assets/recycle-assets/by-outasset/{recordcode}/` | 按出库编码查询回收记录 | 路径: recordcode | RecycleAssetDetailSerializer | 认证 |
| POST | `/api/assets/recycle-assets/batch-create/` | 批量创建回收记录 | Body: {items: [{recycle_outasset_code, recycle_type, recycle_date(可选), recycle_description(可选)}], recycle_asset_storage(可选), recycle_asset_recycle_person_jobcode(可选)} | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/assets/recycle-assets/batch-delete/` | 批量删除回收记录 | Body: {ids: [...]} | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |

### RecycleAssetCreateSerializer 字段说明

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| outasset_recordcode | string | ✅ | 出库记录编码（SlugRelatedField） |
| storage_code | string | ✅ | 仓库编码（SlugRelatedField） |
| recycle_asset_date | date | ✅ | 回收日期 |
| recycle_type | string | ✅ | 回收原因 |
| recycle_asset_number | integer | ❌ | 回收数量，默认 1 |
| recycle_asset_description | string | ❌ | 回收描述 |

### 待报废资产管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/damaged-assets/` | 待报废列表 | ?page, ?page_size, ?search, ?approval_status, ?ordering | DamagedAssetListSerializer | 认证 |
| POST | `/api/assets/damaged-assets/` | 创建待报废记录 | Body: DamagedAssetCreateSerializer 字段 | DamagedAssetDetailSerializer | 管理员 |
| GET | `/api/assets/damaged-assets/{damaged_asset}/` | 待报废详情 | 路径: damaged_asset 或 id | DamagedAssetDetailSerializer | 认证 |
| PUT | `/api/assets/damaged-assets/{damaged_asset}/` | 更新待报废记录 | Body: DamagedAssetUpdateSerializer 字段 | DamagedAssetDetailSerializer | 管理员 |
| DELETE | `/api/assets/damaged-assets/{damaged_asset}/` | 取消待报废申请（软删除） | 路径: damaged_asset | - | 管理员 |
| POST | `/api/assets/damaged-assets/{damaged_asset}/approve/` | 审批通过 | Body: DamagedAssetAproveSerializer 字段 | {damaged_asset, waste_asset} | 管理员 |
| POST | `/api/assets/damaged-assets/{damaged_asset}/reject/` | 审批拒绝 | Body: DamagedAssetAproveSerializer 字段 | DamagedAssetDetailSerializer | 管理员 |
| GET | `/api/assets/damaged-assets/by-asset/{damaged_asset}/` | 按资产编码查询待报废记录 | 路径: damaged_asset | DamagedAssetListSerializer | 认证 |

### 已报废资产管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/waste-assets/` | 已报废列表 | ?page, ?page_size, ?search, ?waste_asset_date, ?ordering | WasteAssetListSerializer | 认证 |
| POST | `/api/assets/waste-assets/` | 创建已报废记录 | Body: WasteAssetCreateSerializer 字段 | WasteAssetDetailSerializer | 管理员 |
| GET | `/api/assets/waste-assets/{waste_asset__asset_code}/` | 已报废详情 | 路径: waste_asset__asset_code 或 id | WasteAssetDetailSerializer | 认证 |
| DELETE | `/api/assets/waste-assets/{waste_asset__asset_code}/` | 删除已报废记录 | 路径: waste_asset__asset_code | - | 管理员 |
| GET | `/api/assets/waste-assets/statistics/` | 报废统计 | 无 | 报废统计数据 | 认证 |
| GET | `/api/assets/waste-assets/by-asset/{waste_asset}/` | 按资产编码查询已报废记录 | 路径: waste_asset | {count, results} | 认证 |
| GET | `/api/assets/waste-assets/by-date-range/` | 按日期范围查询报废记录 | ?start_date, ?end_date | {count, results} | 认证 |

### 硬盘序列号管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/harddisk-sn/` | 硬盘序列号列表 | ?page, ?page_size, ?search, ?harddisk_status, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/harddisk-sn/` | 创建硬盘序列号 | Body: HardDiskSNSerializer 字段 | HardDiskSN 字段 | 管理员 |
| GET | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 硬盘序列号详情 | 路径: harddisksn_asset 或 id | HardDiskSN 字段 | 认证 |
| PUT | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 更新硬盘序列号 | Body: HardDiskSNSerializer 字段 | HardDiskSN 字段 | 管理员 |
| DELETE | `/api/assets/harddisk-sn/{harddisksn_asset}/` | 删除硬盘序列号 | 路径: harddisksn_asset | - | 管理员 |
| POST | `/api/assets/harddisk-sn/search_by_serial_number/` | 通过序列号查询 | Body: {harddisk_sn_code} | HardDiskSN 字段 | 认证 |
| GET | `/api/assets/harddisk-sn/by-asset/{asset_code}/` | 按资产编码查询硬盘记录 | 路径: asset_code | {count, results} | 认证 |
| POST | `/api/assets/harddisk-sn/batch/` | 批量保存硬盘序列号 | Body: {asset_code, disks: [{harddisk_no, harddisk_sn_code, ...}]} | {created, updated, total, asset_code, harddisk_number} | 管理员 |

---

### 已损坏资产管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/broken-assets/` | 损坏记录列表 | ?page, ?page_size, ?search, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/broken-assets/` | 创建损坏记录 | Body: BrokenAssetCreateSerializer 字段 | BrokenAsset 字段 | 管理员 |
| GET | `/api/assets/broken-assets/{recordcode}/` | 损坏记录详情 | 路径: recordcode | BrokenAsset 字段 | 认证 |
| PUT | `/api/assets/broken-assets/{recordcode}/` | 更新损坏记录 | Body: BrokenAssetUpdateSerializer 字段 | BrokenAsset 字段 | 管理员 |
| PATCH | `/api/assets/broken-assets/{recordcode}/` | 部分更新损坏记录 | Body: 部分字段 | BrokenAsset 字段 | 管理员 |
| DELETE | `/api/assets/broken-assets/{recordcode}/` | 删除损坏记录 | 路径: recordcode | - | 管理员 |

---

### 已遗失资产管理

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/lost-assets/` | 遗失记录列表 | ?page, ?page_size, ?search, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/lost-assets/` | 创建遗失记录 | Body: LostAssetCreateSerializer 字段 | LostAsset 字段 | 管理员 |
| GET | `/api/assets/lost-assets/{recordcode}/` | 遗失记录详情 | 路径: recordcode | LostAsset 字段 | 认证 |
| PUT | `/api/assets/lost-assets/{recordcode}/` | 更新遗失记录 | Body: LostAssetUpdateSerializer 字段 | LostAsset 字段 | 管理员 |
| PATCH | `/api/assets/lost-assets/{recordcode}/` | 部分更新遗失记录 | Body: 部分字段 | LostAsset 字段 | 管理员 |
| DELETE | `/api/assets/lost-assets/{recordcode}/` | 删除遗失记录 | 路径: recordcode | - | 管理员 |

---

### 资产找回记录

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/found-assets/` | 找回记录列表 | ?page, ?page_size, ?search, ?ordering | {count, results} | 认证 |
| POST | `/api/assets/found-assets/` | 创建找回记录 | Body: FoundAssetCreateSerializer 字段 | FoundAsset 字段 | 管理员 |
| GET | `/api/assets/found-assets/{recordcode}/` | 找回记录详情 | 路径: recordcode | FoundAsset 字段 | 认证 |
| PUT | `/api/assets/found-assets/{recordcode}/` | 更新找回记录 | Body: FoundAssetUpdateSerializer 字段 | FoundAsset 字段 | 管理员 |
| PATCH | `/api/assets/found-assets/{recordcode}/` | 部分更新找回记录 | Body: 部分字段 | FoundAsset 字段 | 管理员 |
| DELETE | `/api/assets/found-assets/{recordcode}/` | 删除找回记录 | 路径: recordcode | - | 管理员 |

---

### 资产状态操作

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| POST | `/api/assets/assets/{asset_code}/mark_broken/` | 标记资产损坏 | Body: {broken_reason, broken_description} | Asset 字段 | 认证 |
| POST | `/api/assets/assets/{asset_code}/mark_lost/` | 标记资产遗失 | Body: {lost_reason, last_known_location, lost_description} | Asset 字段 | 认证 |
| POST | `/api/assets/assets/{asset_code}/found_and_return/` | 找回遗失资产 | Body: {found_location, found_description} | Asset 字段 | 认证 |

---

## 资产操作日志模块 (`apps/assetmanagement`) — 前缀 `/api/assets/`

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/assets/operation-logs/` | 操作记录列表 | ?asset_code, ?operation_type, ?operator_jobcode, ?start_date, ?end_date, ?days, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/operation-logs/{pk}/` | 操作记录详情 | 路径: pk | AssetOperationLog 字段 | 认证 |
| GET | `/api/assets/operation-logs/by-logging-id/{logging_id}/` | 按 LoggingId 查询记录 | 路径: logging_id | AssetOperationLog 字段 | 认证 |
| GET | `/api/assets/operation-logs/recent/` | 最近操作记录 | ?days (默认7, 范围1-365), ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/operation-logs/user/{operator_jobcode}/` | 用户操作记录 | 路径: operator_jobcode, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/assets/{asset_code}/history/` | 资产操作历史 | 路径: asset_code, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/assets/assets/{asset_code}/timeline/` | 资产状态变更时间线 | 路径: asset_code | 状态时间线数据 | 认证 |

**AssetOperationLog 字段说明**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | IntegerField | 主键 |
| `logging_id` | CharField | 日志唯一标识 |
| `asset_code` | CharField | 资产编码（冗余存储） |
| `asset_name` | CharField | 资产名称（冗余存储，删除 Asset 不影响记录） |
| `asset_specification` | CharField | 资产规格（冗余存储，删除 Asset 不影响记录） |
| `operation_type` | CharField | 操作类型 |
| `operation_time` | DateTimeField | 操作时间 |
| `operator_jobcode` | CharField | 操作人工号 |
| `operator_name` | CharField | 操作人姓名 |
| `before_data` | JSONField | 操作前数据 |
| `after_data` | JSONField | 操作后数据 |
| `description` | TextField | 操作描述 |
| `related_record_code` | CharField | 关联记录编码 |
| `related_record_type` | CharField | 关联记录类型 |
| `ip_address` | GenericIPAddressField | 操作IP |

---

## 通用审计日志模块 (`core`) — 前缀 `/api/`

> 记录非资产操作的审计日志（部门、员工、用户等），与 AssetOperationLog 结构一致。

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/audit-logs/` | 通用审计日志列表 | ?app_label, ?operation_type, ?operator_jobcode, ?record_code, ?start_date, ?end_date, ?days, ?page, ?page_size | {count, results} | 认证 |
| GET | `/api/audit-logs/{pk}/` | 审计日志详情 | 路径: pk | AuditLog 字段 | 认证 |
| GET | `/api/audit-logs/by-logging-id/{logging_id}/` | 按 logging_id 查询 | 路径: logging_id | AuditLog 字段 | 认证 |
| GET | `/api/audit-logs/recent/` | 最近审计日志 | ?days (默认7, 范围1-365) | {count, results} | 认证 |
| GET | `/api/audit-logs/by-app/{app_label}/` | 按应用标识查询 | 路径: app_label (department/employee/authuser) | {count, results} | 认证 |
| GET | `/api/audit-logs/by-operator/{operator_jobcode}/` | 按操作人查询 | 路径: operator_jobcode | {count, results} | 认证 |

### AuditLog 返回字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `pk` | IntegerField | 主键 ID |
| `record_code` | CharField | 被操作记录编码 |
| `app_label` | CharField | 应用标识（department/employee/authuser） |
| `operation_type` | CharField | 操作类型 |
| `operation_type_display` | CharField | 操作类型中文显示 |
| `logging_id` | CharField | 日志记录唯一标识 |
| `operation_time` | DateTimeField | 操作时间 |
| `operator_jobcode` | CharField | 操作人工号 |
| `operator_name` | CharField | 操作人姓名 |
| `before_data` | JSONField | 变更前数据 |
| `after_data` | JSONField | 变更后数据 |
| `description` | TextField | 操作描述 |
| `ip_address` | GenericIPAddressField | 操作IP |

---

## 仪表盘模块 (`apps/assetmanagement`) — 前缀 `/api/dashboard/`

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/dashboard/overview/` | 仪表盘概览统计 | 无 | 总览统计数据 | 认证 |
| GET | `/api/dashboard/recent_out_assets/` | 最近出库记录 | ?limit (默认10, 最大100) | 最近出库记录列表 | 认证 |
| GET | `/api/dashboard/recent_recycle_assets/` | 最近回收记录 | ?limit (默认10, 最大100) | 最近回收记录列表 | 认证 |

---

## 未登记资产管理模块 (`apps/unregisteredasset`) — 前缀 `/api/unregisteredassets/`

| 方法 | URL | 功能 | 请求参数 | 返回字段 | 权限 |
|------|-----|------|----------|----------|------|
| GET | `/api/unregisteredassets/unregistered-assets/` | 未登记资产列表 | ?page, ?page_size, ?scenario_type, ?approval_status, ?discovery_person_jobcode, ?related_asset_code, ?ordering | {count, results} | 认证 |
| POST | `/api/unregisteredassets/unregistered-assets/` | 创建未登记资产 | Body: UnregisteredAssetCreateSerializer 字段 | UnregisteredAssetDetail 字段 | 认证 |
| GET | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 未登记资产详情 | 路径: unregistered_code | UnregisteredAssetDetail 字段 | 认证 |
| PUT | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 更新未登记资产 | Body: UnregisteredAssetUpdateSerializer 字段 | UnregisteredAssetDetail 字段 | 认证（创建者或管理员） |
| PATCH | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 部分更新未登记资产 | Body: 部分字段 | UnregisteredAssetDetail 字段 | 认证（创建者或管理员） |
| DELETE | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/` | 删除未登记资产（软删除） | 路径: unregistered_code | - | 管理员 |
| POST | `/api/unregisteredassets/unregistered-assets/{unregistered_code}/approve/` | 审批处理 | Body: {handle_type, approval_remark} | 审批结果 | 认证 |
| POST | `/api/unregisteredassets/unregistered-assets/batch-create/` | 批量创建未登记资产 | Body: {items: [...]} (最大100条) | {total, success_count, fail_count, success_items, fail_items} | 管理员 |
| POST | `/api/unregisteredassets/unregistered-assets/batch-delete/` | 批量删除未登记资产 | Body: {ids: [...]} (最大100条) | {total, success_count, fail_count, success_ids, fail_items} | 管理员 |
