# =============================================================================
# Makefile - 资产管理系统常用命令
# =============================================================================
# 使用方法：
#   make help                    # 显示帮助信息
#   make install                # 安装依赖
#   make run                    # 启动开发服务器
#   make test                   # 运行测试
#   make lint                   # 代码检查
#   make docker-build           # 构建 Docker 镜像
#   make docker-up               # 启动 Docker 服务

# =============================================================================
# 变量定义
# =============================================================================
PYTHON := python
PIP := pip
VENV := .venv
PYTHONPATH := $(shell pwd)/apps

# Docker 配置
DOCKER_IMAGE := asset-management-backend
DOCKER_TAG := latest
DOCKER_CONTAINER := asset-management-web

# =============================================================================
# 颜色定义
# =============================================================================
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
NC     := \033[0m # No Color

# =============================================================================
# 帮助信息
# =============================================================================
.PHONY: help
help: ## 显示帮助信息
	@echo ""
	@echo "$(BLUE)资产管理系统 - 常用命令$(NC)"
	@echo ""
	@echo "$(GREEN)环境设置：$(NC)"
	@echo "  make install          # 安装项目依赖"
	@echo "  make venv            # 创建虚拟环境"
	@echo "  make clean            # 清理缓存文件"
	@echo ""
	@echo "$(GREEN)开发运行：$(NC)"
	@echo "  make run             # 启动开发服务器"
	@echo "  make shell           # 进入 Django Shell"
	@echo "  make superuser       # 创建超级管理员"
	@echo ""
	@echo "$(GREEN)数据库：$(NC)"
	@echo "  make migrate         # 执行数据库迁移"
	@echo "  make makemigrations  # 创建数据库迁移"
	@echo "  make db-reset        # 重置数据库（危险！）"
	@echo ""
	@echo "$(GREEN)代码质量：$(NC)"
	@echo "  make lint            # 运行代码检查 (ruff/mypy)"
	@echo "  make type-check      # 运行类型检查 (mypy)"
	@echo "  make format          # 代码格式化 (ruff)"
	@echo ""
	@echo "$(GREEN)测试：$(NC)"
	@echo "  make test            # 运行测试"
	@echo "  make coverage        # 生成覆盖率报告"
	@echo ""
	@echo "$(GREEN)Docker：$(NC)"
	@echo "  make docker-build    # 构建 Docker 镜像"
	@echo "  make docker-up       # 启动 Docker 服务"
	@echo "  make docker-down     # 停止 Docker 服务"
	@echo "  make docker-logs     # 查看 Docker 日志"
	@echo ""
	@echo "$(GREEN)文档：$(NC)"
	@echo "  make api-docs        # 生成 API 文档"
	@echo ""

# =============================================================================
# 环境设置
# =============================================================================
.PHONY: install
install: ## 安装项目依赖
	@echo "$(YELLOW)安装项目依赖...$(NC)"
	pip install -r requirements/dev.txt

.PHONY: venv
venv: ## 创建虚拟环境
	@echo "$(YELLOW)创建虚拟环境...$(NC)"
	python -m venv $(VENV)
	@echo "$(GREEN)虚拟环境已创建，激活命令：$(NC)"
	@echo "  source $(VENV)/bin/activate  # Linux/macOS"
	@echo "  $(VENV)\\Scripts\\activate     # Windows"

.PHONY: clean
clean: ## 清理缓存文件
	@echo "$(YELLOW)清理缓存文件...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)清理完成$(NC)"

# =============================================================================
# 开发运行
# =============================================================================
.PHONY: run
run: ## 启动开发服务器
	@echo "$(YELLOW)启动开发服务器...$(NC)"
	$(PYTHON) manage.py runserver

.PHONY: shell
shell: ## 进入 Django Shell
	@echo "$(YELLOW)进入 Django Shell...$(NC)"
	$(PYTHON) manage.py shell

.PHONY: superuser
superuser: ## 创建超级管理员
	@echo "$(YELLOW)创建超级管理员...$(NC)"
	$(PYTHON) manage.py createsuperuser

# =============================================================================
# 数据库
# =============================================================================
.PHONY: migrate
migrate: ## 执行数据库迁移
	@echo "$(YELLOW)执行数据库迁移...$(NC)"
	$(PYTHON) manage.py migrate

.PHONY: makemigrations
makemigrations: ## 创建数据库迁移
	@echo "$(YELLOW)创建数据库迁移...$(NC)"
	$(PYTHON) manage.py makemigrations

.PHONY: db-reset
db-reset: ## 重置数据库（危险！）
	@echo "$(RED)警告：即将重置数据库，所有数据将丢失！$(NC)"
	@read -p "确认重置？(y/n) " -n 1 -r; \
	echo; \
	if [[ ! $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "取消操作"; \
		exit 1; \
	fi
	$(PYTHON) manage.py flush --noinput
	$(PYTHON) manage.py migrate

# =============================================================================
# 代码质量
# =============================================================================
.PHONY: lint
lint: type-check format ## 运行所有代码检查

.PHONY: type-check
type-check: ## 运行类型检查 (mypy)
	@echo "$(YELLOW)运行 mypy 类型检查...$(NC)"
	mypy apps core config utils

.PHONY: format
format: ## 代码格式化 (ruff)
	@echo "$(YELLOW)运行 ruff 代码格式化...$(NC)"
	ruff check . --fix
	ruff format .

# =============================================================================
# 测试
# =============================================================================
.PHONY: test
test: ## 运行测试
	@echo "$(YELLOW)运行测试...$(NC)"
	$(PYTHON) manage.py test

.PHONY: coverage
coverage: ## 生成覆盖率报告
	@echo "$(YELLOW)生成覆盖率报告...$(NC)"
	coverage run --source='.' manage.py test
	coverage report
	coverage html

# =============================================================================
# Docker
# =============================================================================
.PHONY: docker-build
docker-build: ## 构建 Docker 镜像
	@echo "$(YELLOW)构建 Docker 镜像...$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

.PHONY: docker-up
docker-up: ## 启动 Docker 服务
	@echo "$(YELLOW)启动 Docker 服务...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)服务已启动，访问 http://localhost:8000$(NC)"

.PHONY: docker-down
docker-down: ## 停止 Docker 服务
	@echo "$(YELLOW)停止 Docker 服务...$(NC)"
	docker-compose down

.PHONY: docker-logs
docker-logs: ## 查看 Docker 日志
	docker-compose logs -f $(DOCKER_CONTAINER)

# =============================================================================
# 文档
# =============================================================================
.PHONY: api-docs
api-docs: ## 生成 API 文档
	@echo "$(YELLOW)生成 API 文档...$(NC)"
	$(PYTHON) manage.py spectacular --file schema.yml
	@echo "$(GREEN)API 文档已生成至 schema.yml$(NC)"
