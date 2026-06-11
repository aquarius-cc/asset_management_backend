# 贡献指南

感谢您对资产管理系统项目的关注！我们欢迎所有形式的贡献，包括但不限于：

- 🐛 Bug 报告
- 💡 功能建议
- 📝 文档改进
- 🔧 代码贡献
- ✅ 测试完善

## 📋 目录

- [行为准则](#行为准则)
- [开始之前](#开始之前)
- [开发环境设置](#开发环境设置)
- [工作流程](#工作流程)
- [提交规范](#提交规范)
- [Pull Request 流程](#pull-request-流程)
- [测试要求](#测试要求)

---

## 行为准则

请阅读我们的[行为准则](CODE_OF_CONDUCT.md)（如存在）。参与本项目即表示您同意遵守这些准则。

## 开始之前

在开始贡献之前，请：

1. 查看 [AGENTS.md](../AGENTS.md) - 了解项目开发规范
2. 查看 [CHANGELOG.md](../CHANGELOG.md) - 了解项目变更历史
3. 阅读 [README.md](../README.md) - 了解项目概述
4. 查看 [docs/](./) 目录下的详细文档

## 开发环境设置

```bash
# 1. Fork 仓库到您的账户

# 2. 克隆您 Fork 的仓库
git clone https://github.com/your-username/asset_management_backend.git
cd asset_management_backend

# 3. 创建功能分支
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix

# 4. 安装依赖
pip install -r requirements/dev.txt

# 5. 复制环境变量文件
cp .env.example .env
# 编辑 .env 填写本地配置

# 6. 运行数据库迁移
python manage.py migrate

# 7. 创建测试超级管理员（可选）
python manage.py createsuperuser
```

## 工作流程

我们采用 Git Flow 工作流程：

```
main (生产环境)
    └── develop (开发主分支)
            ├── feature/xxx (功能分支)
            ├── fix/xxx (修复分支)
            └── hotfix/xxx (热修复分支)
```

### 创建功能分支

```bash
# 从 develop 分支创建
git checkout develop
git pull origin develop
git checkout -b feature/add-new-asset-type
```

### 提交代码

```bash
# 暂存文件
git add .

# 提交（使用规范的消息格式）
git commit -m "feat(asset): 添加新资产类型功能"
```

### 推送分支

```bash
# 推送您的分支
git push origin feature/add-new-asset-type
```

## 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

[body]

[footer]
```

### 类型 (Type)

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构 |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建/工具变更 |

### 范围 (Scope)

可选，用于标识影响的模块：

- `asset` - 资产管理模块
- `auth` - 认证模块
- `user` - 用户模块
- `api` - API 相关
- `db` - 数据库相关

### 示例

```bash
# 新功能
git commit -m "feat(asset): 添加资产批量导入功能"

# Bug 修复
git commit -m "fix(asset): 修复出库状态更新异常"

# 文档更新
git commit -m "docs: 更新 API 文档中的分页说明"

# 重构
git commit -m "refactor(auth): 重构权限验证逻辑"
```

## Pull Request 流程

### 1. 创建 Pull Request

1. 前往 GitHub 仓库页面
2. 点击 `New Pull Request`
3. 选择您的分支与 `develop` 分支进行比较
4. 填写 PR 描述模板

### 2. PR 描述模板

```markdown
## 描述
<!-- 请简要描述您的更改 -->

## 更改类型
- [ ] 🐛 Bug 修复
- [ ] 💡 新功能
- [ ] 📝 文档更新
- [ ] 🔧 代码重构
- [ ] ✅ 测试

## 相关 Issue
<!-- 如果有相关的 Issue，请链接 -->

## 检查清单
- [ ] 我的代码遵循项目的代码规范
- [ ] 我已经运行了本地测试
- [ ] 我的更改不会引入新的警告
```

### 3. 代码审查

- 等待维护者审查您的代码
- 根据反馈进行修改
- 保持 PR 简洁和专注

### 4. 合并

- 只有在所有检查通过后才能合并
- 使用 `Squash and merge` 合并到 develop 分支
- 删除已合并的分支

## 测试要求

在提交代码之前，请确保：

### 运行测试

```bash
# 运行所有测试
python manage.py test

# 运行特定应用的测试
python manage.py test apps.assetmanagement

# 生成覆盖率报告
coverage run manage.py test
coverage report
```

### 代码检查

```bash
# 类型检查
mypy apps core config utils

# 代码规范
ruff check .

# 格式化
ruff format .
```

### 检查清单

- [ ] 所有测试通过
- [ ] mypy 类型检查无错误
- [ ] ruff 代码规范检查无警告
- [ ] 新功能包含测试
- [ ] 文档已更新（如适用）

## 开发指南

### 代码规范

- 遵循 [AGENTS.md](../AGENTS.md) 中的规范
- 使用类型注解
- 编写清晰的注释和文档字符串
- 保持函数简短（建议不超过 50 行）

### 提交前自检

```bash
# 一键检查
make lint
make test
```

## 问题反馈

如果您发现任何问题或有疑问：

1. 先搜索 [Issues](https://github.com/your-org/asset_management_backend/issues)
2. 如果没有找到类似问题，创建新的 Issue
3. 详细描述问题和复现步骤

## 许可证

通过贡献代码，您同意将您的作品按照项目的 [Apache License 2.0](../LICENSE) 许可证发布。

---

感谢您的贡献！ 🎉
