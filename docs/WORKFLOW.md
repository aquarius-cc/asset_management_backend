# Git 工作流 & CI/CD 规范（后端 Python + Django + MySQL）

> 适用：资产管理系统后端（Python 3.12+ / Django 6.0 / DRF 3.15+ / MySQL 8.0）  
> 遵循：`API_STANDARDS.md`、`SECURITY.md` 最高准则

---

## 1. 分支策略（GitHub Flow 简化版）

| 分支类型        | 命名示例                         | 说明                  |
| ----------- | ---------------------------- | ------------------- |
| `main`      | —                            | 生产稳定分支，禁止直接提交       |
| `develop`   | —                            | 开发主干，所有变更先合并至此      |
| `feature/*` | `feature/asset-batch-import` | 新功能                 |
| `fix/*`     | `fix/jwt-refresh-error`      | Bug 修复              |
| `hotfix/*`  | `hotfix/critical-login`      | 线上紧急修复（从 `main` 切出） |
| `chore/*`   | `chore/upgrade-django-6.0.2` | 依赖升级、配置调整           |

**核心规则**：

- 禁止直接向 `main` 或 `develop` 推送
- 所有变更必须通过 MR/PR 合并，至少 1 人评审通过

---

## 2. 提交规范（Conventional Commits）

格式：`<type>(<scope>): <subject>`

### 2.1 常用 Type

| type       | 说明          | 示例                                     |
| ---------- | ----------- | -------------------------------------- |
| `feat`     | 新功能         | `feat(asset): 添加资产批量导入 API`            |
| `fix`      | Bug 修复      | `fix(auth): 修复 JWT Refresh Token 过期问题` |
| `docs`     | 文档更新        | `docs: 更新部署文档 MySQL 配置`                |
| `style`    | 代码格式（不影响逻辑） | `style(asset): 用 black 格式化`            |
| `refactor` | 重构（无功能变化）   | `refactor(asset): 重构查询逻辑`              |
| `perf`     | 性能优化        | `perf(asset): 优化列表查询索引`                |
| `test`     | 测试相关        | `test(asset): 新增出库流程测试`                |
| `chore`    | 构建/工具/依赖    | `chore: 升级 djangorestframework`        |

### 2.2 Scope（可选）

建议使用模块名：`asset`, `auth`, `user`, `db`, `api` 等。

---

## 3. 自动化检查（Git Hooks）

使用 `pre-commit` 确保代码质量，配置文件 `.pre-commit-config.yaml`：

```
yaml

repos:

- repo: https://github.com/psf/black
  rev: 24.4.2
  hooks:

  - id: black
    args: ["--line-length=100"]

- repo: https://github.com/PyCQA/isort
  rev: 5.13.2
  hooks:

  - id: isort
    args: ["--profile=black", "--line-length=100"]

- repo: https://github.com/PyCQA/flake8
  rev: 7.0.0
  hooks:

  - id: flake8
    args: ["--max-line-length=100", "--extend-ignore=E203,W503"]

  # 类型检查（可选）

- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.10.0
  hooks:

  - id: mypy
    args: ["--ignore-missing-imports"]
    additional_dependencies: ["django-stubs", "djangorestframework-stubs"]

  # 提交信息校验

- repo: https://github.com/alessandrojcm/commitlint-pre-commit-hook
  rev: v9.16.0
  hooks:

  - id: commitlint
    stages: [commit-msg]
    additional_dependencies: ['@commitlint/config-conventional']
```

### 安装与启用：

```
bash

pip install pre-commit
pre-commit install
```

## 4. 开发流程

1. **获取最新代码**

```
bash

git checkout develop && git pull origin develop
```

2. **创建分支**

```
bash

git checkout -b feature/asset-batch-import
```

3. **开发 + 自测**

```
bash

black isort flake8   # 代码格式化与检查
python manage.py test # 运行测试
```

4. **提交**

```
bash

git add .
git commit -m "feat(asset): 添加资产批量导入 API"
git push origin feature/asset-batch-import
```

## 5. 合并流程

1. 提交 MR/PR 至 `develop`

2. 至少 1 名团队成员评审通过（重点检查 API 设计、权限、测试覆盖）

3. 合并后删除源分支

4. 版本发布时将 `develop` 合并到 `main`，并打 Tag（如 `v1.0.0`）

---

## 6. CI/CD 配置（GitHub Actions + MySQL）

创建 `.github/workflows/ci-cd.yml`：

```
yaml

name: CI/CD Pipeline

on:
  push:
    branches: [ develop, main ]
  pull_request:
    branches: [ develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: asset_db
          MYSQL_USER: asset_user
          MYSQL_PASSWORD: test_password
        ports:
          - 3306:3306
        options: --health-cmd="mysqladmin ping" --health-interval=10s --health-timeout=5s --health-retries=5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/dev.txt
          pip install black isort flake8

      - name: Run code checks
        run: |
          black --check .
          isort --check .
          flake8 .

      - name: Run tests
        env:
          DB_ENGINE: django.db.backends.mysql
          DB_NAME: asset_db
          DB_USER: asset_user
          DB_PASSWORD: test_password
          DB_HOST: 127.0.0.1
          DB_PORT: 3306
          DJANGO_SECRET_KEY: test-secret-key
          DJANGO_DEBUG: "False"
        run: |
          python manage.py migrate
          python manage.py test

  deploy-test:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop'
    steps:
      - name: Deploy to Test Server
        run: echo "Deploying to test environment..."

  deploy-prod:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://your-domain.com
    steps:
      - name: Deploy to Production
        run: echo "Deploying to production (manual approval required)..."
    ```
```

## 7. 流程说明

| 触发场景              | 自动化操作                         |
| ----------------- | ----------------------------- |
| 提交 PR 到 `develop` | 代码格式检查 + 单元测试                 |
| 合并到 `develop`     | 测试通过后自动部署到测试环境                |
| 合并到 `main`        | 测试通过后需人工确认，部署生产环境（含迁移、静态文件收集） |

---

## 8. 提交前自检清单

| 类别     | 检查项                                            |
| ------ | ---------------------------------------------- |
| **分支** | ✅ 从 `develop` 切出，命名符合规范                        |
| **提交** | ✅ 提交信息符合 Conventional Commits                  |
| **代码** | ✅ `black / isort / flake8` 全部通过                |
| **测试** | ✅ 单元测试覆盖核心逻辑，本地全量通过                            |
| **规范** | ✅ API 符合 `API_STANDARDS.md`，权限符合 `SECURITY.md` |
| **文档** | ✅ 如有架构/接口变更，已同步更新对应 docs 文档                    |

> ⚠️ 任何未通过以上检查的 MR/PR 将被拒绝合并。
