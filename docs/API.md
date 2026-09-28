# 资产管理系统 API 接口文档

> **本文件不再维护端点清单。** 手写的「方法 / URL / 请求参数 / 返回字段」表格已于
> 2026-09-27 全部退役（见下方[为什么退役](#为什么退役手写端点表)）。
> 端点契约请以下方**权威来源**为准。

## 权威接口文档

| 用途 | 地址 | 说明 |
|------|------|------|
| 交互式浏览 | `/api/v1/swagger/` | Swagger UI，可直接发请求 |
| 交互式阅读 | `/api/v1/redoc/` | ReDoc，按响应模型分组 |
| 机器可读契约 | `/api/v1/schema/` | OpenAPI 3 JSON，由 drf-spectacular 从代码生成 |
| 版本化基线 | [`api-schema-baseline.json`](../api-schema-baseline.json) | CI 比对漂移用快照，改端点须同 PR 重导出 |

生成基线的命令（**改动任何端点后必须执行并提交**）：

```bash
python manage.py spectacular --format openapi-json --file api-schema-baseline.json --validate
```

CI 侧由 `api-schema-check` job 自动比对：破坏性变更直接失败，非破坏性漂移告警。

## 统一响应格式

所有业务接口返回同一包裹结构（权威实现 `utils/response_utils.py`）：

```json
{ "code": 0, "message": "操作成功", "data": {} }
```

| 键 | 类型 | 含义 |
|----|------|------|
| `code` | integer | 成功恒为 `0`；失败为对应 HTTP 状态码（如 400 / 403 / 404） |
| `message` | string | 提示文案。**键名是 `message`，不是 `msg`** |
| `data` | object \| null | 业务数据；无数据时为 `{}` |

> 旧版本文档写作 `{code, msg, data}`，键名有误，已更正。

分页接口的 `data` 内含 `{count, next, previous, results}`。
分页请求参数名为 `page`（页码，从 1 开始）与 `page_size`（每页条数）。

## 鉴权

- 认证方式：JWT。同时支持 `Authorization: Bearer <access>` 与 HttpOnly Cookie
  （Cookie 名见 `settings.JWT_AUTH_COOKIE_ACCESS`）。
- 写操作不使用 `IsAdminUser`。系统配置类（类型 / 仓库 / 合同 / 员工 / 部门 / 用户）
  仅 `system_admin` 角色可写；普通角色按部门数据范围收窄可见性。
- 逐端点的权限要求以 OpenAPI 的 `security` 与接口描述为准，不再在本文件重复。

## 运维端点（不在 OpenAPI schema 内）

以下端点由 `config/urls.py` 直接以 Django 视图挂载，**不出现在 OpenAPI schema 中**，
故需在此单独记录：

| 方法 | URL | 用途 | 返回 | 状态码 |
|------|-----|------|------|--------|
| GET | `/` | API 根信息，列出文档入口 | `{message, version, docs:{swagger,redoc,schema}, admin}` | 200 |
| GET | `/health/` | 健康检查（OC-6） | `{status, checks:{database,redis}, version}` | 200 / 503 |
| GET | `/ready/` | 就绪检查（OC-6） | `{status, service, checks:{database,redis}}` | 200 / 503 |
| GET | `/metrics/` | Prometheus 指标（OC-4） | Prometheus 文本格式 | 200 |
| GET | `/admin/` | Django Admin 后台 | HTML | 200 |

`/health/` 与 `/ready/` 会在任一依赖不健康时返回 **503**，供负载均衡与探针判定。
`/metrics/` 无认证，仅供 Prometheus 内网抓取，**不得**直接暴露到公网。

## 字段参考

以下为**跨端点复用的数据模型字段表**，与端点清单不同——它们不随路由变动而失效，
故保留。已逐项对照 `api-schema-baseline.json` / 模型 / 序列化器核实。

### RecycleAssetCreate 请求体字段

对应 OpenAPI 组件 `RecycleAssetCreateRequest`。

| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `outasset_recordcode` | string | ✅ | 出库记录编码（SlugRelatedField） |
| `storage_code` | string | ✅ | 仓库编码（SlugRelatedField） |
| `recycle_asset_date` | date | ✅ | 回收日期 |
| `recycle_type` | string | ✅ | 回收原因 |
| `recycle_asset_number` | integer | ❌ | 回收数量，默认 1 |
| `recycle_asset_description` | string | ❌ | 回收描述 |

### AuditLog 返回字段

对应 `core/audit_log_views.py::AuditLogSerializer`（只读）。

| 字段名 | 来源 | 说明 |
|--------|------|------|
| `pk` | 模型主键 | 主键 ID |
| `record_code` | CharField | 被操作记录编码 |
| `app_label` | CharField | 应用标识（department / employee / authuser） |
| `operation_type` | CharField | 操作类型（create/update/delete/approve/login/logout/permission_change/state_change） |
| `operation_type_display` | `get_operation_type_display()` | 操作类型中文显示（由 choices 派生，非模型字段） |
| `logging_id` | CharField | 日志记录唯一标识 |
| `operation_time` | DateTimeField | 操作时间，ISO 8601 带时区偏移 |
| `operator_jobcode` | CharField | 操作人工号 |
| `operator_name` | CharField | 操作人姓名 |
| `before_data` | JSONField | 变更前数据 |
| `after_data` | JSONField | 变更后数据 |
| `description` | TextField | 操作描述 |
| `ip_address` | GenericIPAddressField | 操作 IP |

## 为什么退役手写端点表

退役的**理由是维护成本，不是内容失真**。这一点必须写准，否则后来者会误以为
「文档全错、只是懒得改」，而真实情况相反——端点绝大部分都还在，只是路径写法过时。

退役前对本文件做过全量核对（`scripts/check_api_doc_consistency.py` 对
`api-schema-baseline.json` 逐条比对）。**核对结论：表内路径串无一「端点不存在」**，
差异全部集中在三类可机械修正的写法——缺 `/v1` 前缀、路径参数名过时、action 名过时；
另有一小部分是模块挂载前缀与 schema 出口（说明路由结构用，非可调用端点），
以及一个已在实现中退役的端点。

退役理由因此只有一条：手写端点表是 `api-schema-baseline.json` 的人工副本，而人工副本
必然随实现改动而分叉——本次需要改写的行数就是证据；下一次路由迁移会让整表再次失效，
而 `/api/v1/schema/` 始终自动正确。字段表、响应格式、鉴权说明等**不依赖路由**的内容
已保留在本文上部。

> 本文刻意不记录上述核对的具体数字。端点表删除后，那些数字已无法由护栏复现
> （护栏扫描的是当前文档），写死在正文里只会变成无法核对的魔法数字。
> 需要数字时运行 `python scripts/check_api_doc_consistency.py`，其输出由提取器实时枚举。

`docs/API详细文档0608.md` 的「资源端点列表」章节同批删除（与该章节内的小节标题
路径完全重合，零信息损失），其余章节保留并按同一基线修正。

## 相关规范

- 业务规则：`Rules_Fiels/backend-business-rules.md`（B1–B10、状态机、BR-1~BR-7）
- 测试规范：`Rules_Fiels/backend-testing-rules.md`（T1–T8）
- 跨端契约（响应结构、状态枚举、分页参数名、日期格式）：根级 `AGENTS.md` §3
