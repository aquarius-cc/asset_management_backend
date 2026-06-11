# Changelog

所有重要的项目变更都将记录在此文件中。

项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范。

格式基于 [Conventional Commits](https://www.conventionalcommits.org/zh-cn/v1.0.0/) 规范。

## \[未发布\] - YYYY-MM-DD

### 新增 (Added)
- 新功能

### 更改 (Changed)
- 功能变更

### 弃用 (Deprecated)
- 即将弃用的功能

### 修复 (Fixed)
- Bug 修复

### 移除 (Removed)
- 移除的功能

### 安全 (Security)
- 安全相关变更

---

## \[1.0.0\] - 2025-01-01

### 新增 (Added)
- 资产管理核心模块（资产、入库、出库、回收、报废）
- 认证授权模块（JWT 认证、权限控制）
- 用户管理模块（用户、部门、岗位）
- RESTful API 接口
- OpenAPI 自动文档生成
- 数据库审计日志功能

### 功能 (Features)
- 资产全生命周期管理
- 细粒度 RBAC 权限控制
- 行级数据隔离
- 事务安全保证
- 统一响应格式

### 文档 (Documentation)
- 项目架构文档
- API 设计规范
- 安全规范文档
- 测试规范文档
- Git 工作流规范

---

## 版本说明

版本格式：`MAJOR.MINOR.PATCH`

- **MAJOR**: 破坏性兼容变更
- **MINOR**: 新增功能（向后兼容）
- **PATCH**: Bug 修复（向后兼容）

### 分支策略

- `main`: 生产环境代码
- `develop`: 开发主分支
- `feature/*`: 功能开发分支
- `hotfix/*`: 热修复分支

### 提交规范

请使用 Conventional Commits 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型 (type)：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具变更

---

> 上次更新时间：2025-01-01
