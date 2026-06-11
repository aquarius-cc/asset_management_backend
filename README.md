# 资产管理系统后端 (Asset Management Backend)

> 基于 Django REST Framework 的企业级资产管理后端服务

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.16-red.svg)](https://www.django-rest-framework.org/)

## 项目概述

本项目为企业资产管理系统提供后端 API 支撑，基于**前后端分离架构**，覆盖资产从入库、领用、外借、报废、回收、盘点全生命周期。

### 核心能力

- ✅ **全生命周期管理** - 资产入库、领用、外借、报废、回收、盘点
- ✅ **审计留痕** - 所有操作自动记录，满足合规要求
- ✅ **细粒度权限** - RBAC + 行级数据隔离
- ✅ **事务安全** - 关键操作使用 `@transaction.atomic`
- ✅ **RESTful API** - OpenAPI 自动文档

## 技术栈

| 领域 | 技术选型 |
|------|---------|
| **语言** | Python 3.12+ |
| **框架** | Django 6.0 + DRF 3.16 |
| **数据库** | MySQL 8.0+ |
| **认证** | JWT (SimpleJWT) |
| **文档** | drf-spectacular |

## 快速开始

### 环境要求

- Python 3.12+
- MySQL 8.0+ (或使用 SQLite 进行开发)

### 安装步骤

```bash
# 1. 克隆项目
git clone <repo-url>
cd asset_management_backend

# 2. 创建虚拟环境
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements/dev.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填写数据库配置

# 5. 数据库迁移
python manage.py migrate

# 6. 创建超级管理员（可选）
python manage.py createsuperuser

# 7. 启动开发服务器
python manage.py runserver
```

### 环境变量配置

参考 `.env.example` 文件，配置以下环境变量：

- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` - 数据库配置
- `SECRET_KEY` - Django 密钥（生产环境必须修改）
- `DEBUG` - 调试模式（生产环境设为 `False`）
- `ALLOWED_HOSTS` - 允许的主机域名

## 项目结构

```
asset_management_backend/
├── apps/                      # 业务应用
│   ├── assetmanagement/       # 资产核心模块
│   ├── authusermanagement/    # 认证授权模块
│   └── usermanagement/        # 用户管理模块
├── core/                      # 公共基类和工具
├── utils/                     # 通用工具函数
├── config/                    # Django 配置
├── requirements/              # 分层依赖文件
├── docs/                      # 详细文档
├── manage.py
└── README.md                  # 本文件入口
```

## 文档导航

> 更多详细信息请查阅 `docs/` 目录下的文档

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 项目全景、快速上手、文档导航 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层架构、模块职责 |
| [docs/API_STANDARDS.md](docs/API_STANDARDS.md) | REST API 设计规范 |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全配置、权限矩阵 |
| [docs/TESTING.md](docs/TESTING.md) | 测试规范 |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Git 工作流、CI/CD |

## 代码规范

本项目遵循 `AGENTS.md` 定义的开发规范：

- ✅ 类型标注完整 (mypy 零错误)
- ✅ 分层架构 (Selector/Service/View)
- ✅ 单向依赖
- ✅ 事务安全
- ✅ 统一响应格式

提交前请确保通过：

```bash
mypy .
ruff check .
python manage.py test
```

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源许可证。

## 贡献指南

详见 [CONTRIBUTING.md](CONTRIBUTING.md)

---

> 🔴 **重要**：AI 代理在任务开始前必须阅读 `AGENTS.md`
