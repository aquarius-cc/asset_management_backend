# 资产管理系统后端工程 — README

> **面向 Python 3.12 + Django 6.0 + DRF 3.15 的后端服务**  
> 遵循 `AGENTS.md`（AI 最高开发准则）与 Harness 协作流程  
> 为人工开发者与 AI 代理提供统一的入口、规范与知识上下文

---

## 1. 项目简介

为企业资产管理系统提供后端 API 支撑，基于 **前后端分离架构**，覆盖资产从入库、领用、外借、报废、回收、盘点全生命周期。
系统内置 **审计留痕、行级数据隔离、细粒度权限、事务安全、幂等性** 等企业级能力，保障数据一致性与合规性。

---

## 2. 技术栈总览

| 领域       | 技术选型                                                       |
| -------- | ---------------------------------------------------------- |
| **语言**   | Python 3.12+（强制类型标注，禁止 `Any`）                              |
| **框架**   | Django 6.0.5、Django REST Framework 3.15                    |
| **数据库**  | PostgreSQL 16+（ORM 防注入、软删除基类）                              |
| **认证**   | JWT（Simple JWT / Token 刷新）                                 |
| **权限**   | DRF 全局权限 + 对象级 `check_object_permissions` + 行级数据隔离         |
| **文档**   | drf-spectacular（自动生成 OpenAPI）                              |
| **质量工具** | mypy（静态类型）、ruff（代码规范）、pytest / unittest（测试）                |
| **依赖管理** | pip + venv，分层 `requirements/base.txt` `dev.txt` `test.txt` |
| **工程化**  | Git 版本管理、CI/CD 门禁（mypy → ruff → test → check --deploy）     |

---

## 3. 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url> && cd asset_management_backend

# 2. 创建虚拟环境（Python 3.12+）
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements/dev.txt

# 4. 数据库迁移
python manage.py migrate

# 5. 启动开发服务器
python manage.py runserver
```

> 更多环境配置（数据库、JWT 密钥等）请编辑 `.env` 文件（可参考 `.env.example`）。

## 4. 代码规范（摘要）

**所有详细规则以 `AGENTS.md` 为最高准则，`docs/` 下文档为补充说明。**

| 规则       | 要求                                                                                         |
| -------- | ------------------------------------------------------------------------------------------ |
| **类型标注** | mypy 零错误通过，禁止使用 `Any`、`# type: ignore` 逃避检查                                                |
| **模型层**  | 统一继承 `core.models.BaseModel`（自动包含 `create_time` `update_time` `is_delete`）；表名蛇形小写 `am_` 前缀 |
| **业务分层** | `Selector` 只读、`Service` 只写、`View` 仅处理 HTTP；单向依赖 `Model→Serializer→Service/Selector→View`   |
| **事务安全** | 影响库存/状态的写操作必须包裹 `@transaction.atomic`                                                      |
| **安全输入** | 所有用户输入经 Serializer 全量校验，禁止拼接原生 SQL                                                         |
| **统一响应** | `{"code":200, "msg":"", "data":{}}`                                                        |
| **绝对导入** | `from apps.xxx` / `from core.xxx`，禁止相对导入                                                   |
| **代码风格** | 严格对齐现有项目风格，ruff 零告警                                                                        |

---

## 5. 目录总览

asset_management_backend/
├── apps/                    # 业务应用
│   ├── assetmanagement/     # 资产核心（模型、序列化、服务、视图、信号）
│   ├── authusermanagement/  # 认证与授权
│   └── usermanagement/      # 用户与组织
├── core/                    # 公共基类（BaseModel、异常处理等）
├── utils/                   # 通用工具函数
├── config/                  # Django 配置（settings、urls、wsgi）
├── requirements/            # 分层依赖文件
├── docs/                    # 架构、规范、业务文档（见下方文档清单）
├── migrations/              # 数据库迁移文件
├── manage.py
└── .env                     # 环境变量（禁止入库）

## 6. 📚 文档清单与 AI 协同指引

> **AI 代理任务前必须阅读 `AGENTS.md`（最高优先级）**  
> 再根据任务类型自动加载下表对应的文档，**禁止仅凭记忆或假设编写代码**。

### 6.1 文档加载触发规则

| 任务类型          | 必须阅读的文档                                 |
| ------------- | --------------------------------------- |
| **业务功能开发**    | `业务流程说明书.md` + `资产数据字典.md` + `权限矩阵表.md` |
| **API 接口开发**  | `API_STANDARDS.md` + `资产数据字典.md`        |
| **权限 / 认证模块** | `SECURITY.md` + `权限矩阵表.md`              |
| **架构变更 / 重构** | `ARCHITECTURE.md` + `业务流程说明书.md`        |
| **测试编写**      | `TESTING.md` + 相应业务文档                   |
| **审计相关**      | `审计日志规范.md` + `业务流程说明书.md`              |
| **依赖升级 / 部署** | `DEPLOYMENT.md`（如存在）、`WORKFLOW.md`      |

### 6.2 文档索引表

| 文档                    | 用途                                        | AI 触发场景                  |
| --------------------- | ----------------------------------------- | ------------------------ |
| **AGENTS.md**         | **最高开发准则**：红线、流程、代码规范、前后端分离要求             | ⚠️ 任何任务开始前必须通读           |
| **README.md**（本文件）    | 项目全景、快速上手、文档导航                            | 首次接入、环境问题                |
| **ARCHITECTURE.md**   | 分层架构、App 职责、依赖方向、设计决策                     | 方案设计、重构、新增模块             |
| **API_STANDARDS.md**  | REST 设计规范、响应格式、分页/筛选标准、drf-spectacular 注解 | 任何 API 开发                |
| **TESTING.md**        | 测试策略、命名规范、Mock 限制、覆盖率目标                   | 编写测试、修复 Bug              |
| **SECURITY.md**       | 认证授权、敏感数据脱敏、SQL 注入防护、依赖安全                 | 权限开发、安全审计                |
| **业务流程说明书.md**        | 资产全生命周期状态流转、操作规则、前置条件                     | 业务逻辑编写、状态机实现             |
| **资产数据字典.md**         | 模型字段详情、枚举值、索引、约束                          | Model/Serializer 设计、数据查询 |
| **权限矩阵表.md**          | 角色-操作映射、数据范围规则                            | 权限控制、`get_queryset` 数据隔离 |
| **审计日志规范.md**         | 审计事件标准、记录字段、存储查询要求                        | 审计功能开发、合规检查              |
| **WORKFLOW.md**       | Git 分支策略、提交规范、CI/CD 门禁流程                  | 代码提交、解决 CI 失败            |
| **DEPLOYMENT.md**（如有） | 生产部署、迁移策略、回滚方案                            | 上线检查、环境配置                |
| **CHANGELOG.md**（如有）  | 版本变更记录                                    | 升级依赖、排查兼容性               |

### 6.3 AI 协同核心规则

- 🔴 **文档缺失或需求模糊时，必须立即暂停并询问**，严禁猜测、私自扩展需求。

- 🟡 所有代码产出必须通过 `AGENTS.md` 定义的 **mypy / ruff / test / 业务合规** 门禁。

- 🟡 文档必须与代码同步更新；API 变更需同步 drf-spectacular 注解，架构/表结构/权限变更需同步相应的 `docs/` 文档。

- 🔵 本 README 即为 AI 查询的入口文档，遇到未知模块请根据上方表格定位对应文档。

---

## 7. 核心目标

- 提供稳定、可审计、高一致性的资产管理 REST API

- 严格数据隔离与权限防控，杜绝越权与数据泄漏

- 自动化审计留痕，满足合规与排查要求

- 分层架构与强类型保障，降低多人及 AI 协同成本

- 核心业务在并发、异常场景下数据正确性零妥协

---

## 8. 贡献与协作

1. 严格遵循 `AGENTS.md` 与 `docs/WORKFLOW.md` 中的分支策略和提交格式（Conventional Commits）。

2. 提交前本地运行 `mypy .`、`ruff check .`、`python manage.py test` 并确保全量通过。

3. 资产核心数据变更必须附带审计日志逻辑，并提供回滚方案。

4. AI 生成代码需标注关键决策点，供人工审查。

> 更多细节请查阅根目录 `AGENTS.md` 及 `docs/` 下的对应规范文档。