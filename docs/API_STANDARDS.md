# API 开发规范 (API_STANDARDS.md)

> **适用**：资产管理系统后端（Python 3.12+ / Django 6.0 / DRF 3.15+）  
> **遵循**：`AGENTS.md` 为最高准则，所有 API 实现必须通过自检清单  
> **版本**：v1.1 | **更新**：2026-05-07

---

## 1. 设计原则

1. **资源导向**：路径段用**名词复数**  
   ✅ `/api/v1/assets/`  
   ❌ `/api/v1/getAssets`

2. **HTTP 方法语义**严格遵循：

| 方法       | 场景        | 幂等  |
| -------- | --------- | --- |
| `GET`    | 获取列表 / 详情 | 是   |
| `POST`   | 创建新资源     | 否   |
| `PUT`    | 全量替换更新    | 是   |
| `PATCH`  | 部分字段更新    | 否   |
| `DELETE` | 软删除（状态变更） | 是   |

3. **版本控制**：URL 路径前缀 `/api/v1/`，后续大版本 `/api/v2/` 平滑升级。

4. **统一响应格式**：所有接口返回固定 JSON 结构（详见第 2 节）。

---

## 2. 统一响应格式

### 2.1 成功响应

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": { }
}
```

- `data` 可为对象、数组或 `null`（删除操作）。

- 分页列表的 `data` 见第 4 节。

### 2.2 错误响应

```json
{
  "code": 40010,
  "msg": "资产状态不允许此操作",
  "data": null
}
```

- `code`：业务错误码，由 `core/exceptions.py` 自定义异常类统一管理。

- `msg`：**用户可读提示**，禁止暴露堆栈、SQL 错误等技术细节。

- 全局 DRF 异常处理器负责转换所有异常为此格式。

---

## 3. Serializer 强制约束

### 3.1 场景分离（必须）

每个模型严格区分 4 种序列化器：

| 类型                 | 用途             | 示例                      |
| ------------------ | -------------- | ----------------------- |
| `CreateSerializer` | `POST` 创建      | `AssetCreateSerializer` |
| `UpdateSerializer` | `PUT/PATCH` 更新 | `AssetUpdateSerializer` |
| `ListSerializer`   | `GET` 列表（字段精简） | `AssetListSerializer`   |
| `DetailSerializer` | `GET` 详情（可含嵌套） | `AssetDetailSerializer` |

```python
# 示例：ListSerializer 字段精简

class AssetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'asset_code', 'asset_name', 'asset_current_status']
```

### 3.2 前置校验（必须）

- 所有业务流程校验（如状态流转前置条件）必须在 `validate()` 或 `validate_<field>()` 中完成。

- **禁止**未校验数据流入 Service 层。

### 3.3 敏感字段保护

- 采购价、鉴权信息等 → 依权限返回时脱敏，否则设置 `write_only=True`。

- 密码字段 → **必须** `write_only=True`。

### 3.4 嵌套序列化

- 仅在 `DetailSerializer` 中展开外键，且必须显式 `read_only=True`。

- `ListSerializer` 避免深度嵌套，避免 N+1 性能问题。

---

## 4. 分页、筛选与排序

### 4.1 分页（默认强制）

请求参数：

| 参数          | 类型  | 必填  | 说明                |
| ----------- | --- | --- | ----------------- |
| `page`      | int | 否   | 页码，默认 1           |
| `page_size` | int | 否   | 每页条数，默认 20，最大 100 |

响应格式：

```json
{
  "code": 200,
  "msg": "",
  "data": {
    "total": 150,
    "page": 1,
    "page_size": 20,
    "items": []
  }
}
```

### 4.2 筛选

- QueryParams 传递，命名遵循 `字段名__查询方式`（如 `status=active`、`price__lte=1000`）。

- **必须**使用 `django-filter` 或自定义 `filter_class`，禁止手动拼接 raw SQL。

### 4.3 排序

- 统一参数 `ordering`，如 `?ordering=-created_at`（负号倒序）。

- 可排序字段必须在视图 `ordering_fields` 中白名单声明，防止内部列泄露。

---

## 5. 认证与权限

### 5.1 JWT 认证（默认全局）

- Access Token 过期 ≤ 2 小时，支持 Refresh Token。

- 视图显式配置：

```python
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
class AssetViewSet(ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
```

### 5.2 权限分层控制（必须）

```text
请求 → 全局 JWT 认证
     → 全局权限(IsAuthenticated)
     → View.get_queryset() 行级数据隔离
     → View.check_object_permissions() 对象级权限
     → Service 层业务权限（审批 / 状态前置）
```

- **行级隔离**：重写 `get_queryset` 按 `request.user` 过滤组织/部门，禁止返回全量。

```python
def get_queryset(self):
    return Asset.objects.filter(department=self.request.user.department)
```

- **对象权限**：`retrieve/update/destroy` 等单个资源操作必须调用 `check_object_permissions`。

- **敏感操作**（导出、批量删除）增加二次业务校验。

---

## 6. 异常处理

- 使用 DRF `EXCEPTION_HANDLER` 全局统一转换，**禁止视图中 try-except 返回自定义结构**。

- 自定义业务异常继承 `rest_framework.exceptions.APIException`：

```python
# core/exceptions.py

class AssetStatusError(APIException):
    status_code = 400
    default_code = 40010
    default_detail = "资产状态不允许此操作"
```

---

## 7. 接口文档（drf-spectacular）

- 每个 ViewSet/APIView 必须添加 `@extend_schema(tags=["模块名称"])`。

- 关键接口需 `summary` 和 `description`。

- Serializer 字段必须有 `help_text`：

```python
asset_name = serializers.CharField(help_text="资产名称")
```

- **文档与代码同步**，PR 中标注 API 变更影响。

---

## 8. 安全约束

| 要求       | 详细                                           |
| -------- | -------------------------------------------- |
| **防注入**  | 必须使用 ORM 查询，禁止拼接用户输入 raw SQL                 |
| **CORS** | 生产环境显式配置前端域名，**禁止通配符 `*`**                   |
| **敏感数据** | 日志中遮蔽采购价/维保信息，可用 `sensitive_variables`       |
| **幂等性**  | 创建类接口支持 Idempotency-Key（推荐 Redis 存储，设合理 TTL） |

---

## 9. 代码组织与导入

### 目录结构

```text
apps/
└── assetmanagement/
    ├── serializers.py
    ├── views.py
    ├── permissions.py
    ├── filters.py
    └── urls.py
```

### 导入规则

- 使用绝对导入：`from apps.assetmanagement.serializers import AssetCreateSerializer`

- 路由统一挂载：`path('api/v1/asset/', include('apps.assetmanagement.urls'))`

---

## 10. 提交前自检清单

### 设计

- URL 使用名词复数，版本前缀正确

- HTTP 方法语义正确

- 响应格式统一，异常由全局处理器转换

### 实现

- Serializer 按场景分离，敏感字段已处理

- 列表接口默认分页，筛选使用 `django-filter`，排序字段已白名单

- 权限配置显式完整，对象操作执行 `check_object_permissions`

### 安全

- 无 raw SQL 拼接，CORS 已限制

- 敏感信息在日志中已遮蔽

- 创建类接口已添加幂等键支持

### 文档

- drf-spectacular 注解齐全（tags、summary）

- 文档与代码同步，PR 描述标注 API 变更影响

> ⚠️ 任何违反本规范的 API 代码将被要求修改，直至完全通过清单检查。

---

### 优化说明

1. **结构精简**：将重复表述合并，子章节标题更凝练，增强 AI 检索和匹配效率。
2. **指令式语气**：所有约束以“必须/禁止”表达，消除建议性模糊空间。
3. **示例统一性**：代码示例专注资产场景，直接可复用。
4. **清单可执行化**：自检清单表格化，兼顾人工和 AI 逐项验证。
5. **补全关键安全细节**：新增日志敏感数据遮蔽、CORS 显式约束、幂等键实现建议，与原 AGENTS.md 红线对齐。
