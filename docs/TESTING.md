# 资产管理系统后端测试规范

> 适用：Python 3.12+ / Django 6.0 / DRF 3.15+ / MySQL 8.0  
> 遵循：`AGENTS.md` 最高准则，`API_STANDARDS.md`、`SECURITY.md` 强制门禁  
> 核心目标：强制覆盖核心业务、API、权限与数据一致性，所有提交必须通过测试门禁。

---

## 1. 测试框架与工具

| 工具                                        | 用途        | 强制要求                                                     |
| ----------------------------------------- | --------- | -------------------------------------------------------- |
| `pytest` + `pytest-django` + `pytest-cov` | 测试运行器与覆盖率 | 🔴 必须使用，禁止原生 `unittest`                                  |
| DRF `APIClient`                           | API 集成测试  | 🟡 API 接口测试必须使用                                          |
| `unittest.mock` / `pytest-mock`           | 模拟外部依赖    | 🟡 仅允许 Mock 第三方 API/文件/时间/网络，**绝对禁止 Mock 核心业务逻辑、ORM、事务** |
| `factory_boy` + `Faker`                   | 测试数据生成    | 🟡 推荐，避免硬编码测试数据                                          |

---

## 2. 目录结构与命名规范

### 2.1 标准目录结构（每个 App 内）

apps/assetmanagement/  
└── tests/  
├── factories/ # 数据工厂（factory_boy）  
│ ├── asset_factory.py  
│ └── user_factory.py  
├── unit/ # 单元测试：工具函数、模型、Service/Selector  
│ ├── test_utils.py  
│ ├── test_models.py  
│ └── test_services.py  
├── integration/ # 集成测试：API、数据库多表、权限  
│ ├── test_api.py  
│ └── test_permissions.py  
└── e2e/ # 端到端（可选）  
└── test_asset_lifecycle.py

### 2.2 命名强制规则

- 测试文件：`test_<被测对象>.py`
- 测试函数：`test_should_预期行为_when_触发场景`  
  示例：`test_should_return_201_when_admin_creates_valid_asset`  
  原项目风格 `test_<场景>_<预期结果>` 依然可用，但 AI 新生成必须使用 `test_should_..._when_...`。

---

## 3. 测试环境配置

### 3.1 MySQL 临时测试库

在 `config/settings.py` 或独立 `settings_test.py` 中：

```
python

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'asset_db'),
        'USER': os.getenv('DB_USER', 'asset_user'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        'TEST': {
            'NAME': 'test_asset_db',     # 临时库名
            'CHARSET': 'utf8mb4',
            'COLLATION': 'utf8mb4_unicode_ci',
            'MIGRATE': True,            # 自动运行迁移
            'SERIALIZE': False,         # 关闭序列化加速
        },
    }
}
```

### 3.2 pytest 配置（`pyproject.toml` 或 `pytest.ini`）

```
toml

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
pythonpath = ["."]
addopts = """
    --reuse-db
    --cov=apps/
    --cov-report=term-missing
    --cov-report=html
    -v
"""
filterwarnings = [
    "ignore::DeprecationWarning",
]
```

> 🟡 `--reuse-db` 加速日常开发；数据库结构变更时使用 `--create-db`。

## 4. 测试数据准备（factory_boy）

```
python

# 用户工厂
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    username = factory.Sequence(lambda n: f"test_user_{n:04d}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall('set_password', 'Test@123456')
    is_active = True

# 资产工厂
class AssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Asset
    asset_name = factory.Sequence(lambda n: f"测试资产_{n:04d}")
    asset_code = factory.Sequence(lambda n: f"AST{n:06d}")
    asset_current_status = Asset.Status.IN_STORE
    # 外键关联用 SubFactory
    asset_type_code = factory.SubFactory(AssetTypeFactory)
```

## 5. 编写测试（强制层级）

### 5.1 单元测试

**🔴 必须覆盖**：`utils.py` 工具函数、模型自定义方法/属性、Service/Selector 函数、Serializer 校验逻辑。

```
python

import pytest
from apps.assetmanagement.services import AssetCheckOutService
from apps.assetmanagement.tests.factories import AssetFactory, UserFactory
from core.exceptions import AssetStatusError

@pytest.mark.django_db
def test_should_update_status_to_in_use_when_check_out_success():
    """正常出库 → 状态变更为在用"""
    asset = AssetFactory(asset_current_status='in_store')
    user = UserFactory()
    service = AssetCheckOutService(asset=asset, user=user)
    service.execute()
    asset.refresh_from_db()
    assert asset.asset_current_status == 'in_use'

@pytest.mark.django_db
def test_should_raise_AssetStatusError_when_asset_not_in_store():
    """非在库资产出库 → 抛出业务异常"""
    asset = AssetFactory(asset_current_status='in_use')
    user = UserFactory()
    service = AssetCheckOutService(asset=asset, user=user)
    with pytest.raises(AssetStatusError):
        service.execute()
```

### 5.2 集成测试

**🔴 必须覆盖**：API 端点正确性、权限控制（行级隔离 + 对象级）、数据一致性、事务回滚。

```
python

from django.urls import reverse
from rest_framework import status
import pytest

@pytest.mark.django_db
def test_should_return_201_and_create_asset_when_admin_posts_valid_data(
    authenticated_admin_client
):
    client, user = authenticated_admin_client
    url = reverse('asset-list')
    data = {"asset_name": "新资产", "asset_code": "AST-000001", ...}
    response = client.post(url, data, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert Asset.objects.filter(asset_code="AST-000001").exists()

@pytest.mark.django_db
def test_should_return_403_when_regular_user_tries_to_create_asset(
    authenticated_regular_client
):
    client, user = authenticated_regular_client
    url = reverse('asset-list')
    data = {"asset_name": "越权资产", "asset_code": "AST-000002", ...}
    response = client.post(url, data, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN
```

### 5.3 安全与并发测试

- **权限**：覆盖无认证401、无权限403、行级隔离只能查看本部门数据。

- **并发**：模拟库存扣减时的并发请求，验证事务隔离与数据一致性（可使用 `TransactionTestCase` 或多线程）。

---

## 6. 运行与覆盖率

```
bash

# 全量测试（复用数据库）
pytest

# 重建测试库后运行
pytest --create-db

# 指定模块或函数
pytest apps/assetmanagement/tests/integration/test_api.py::test_should_xxx

# 生成覆盖率 HTML 报告（htmlcov/index.html）
pytest --cov-report=html
```

### 覆盖率红线（🔴 合并门禁）

| 模块                   | 最低覆盖率    |
| -------------------- | -------- |
| 工具函数                 | ≥ 90%    |
| 模型/Service/Selector  | ≥ 85%    |
| API 集成测试（核心流程）       | ≥ 70%    |
| **资产核心业务**（状态机、库存变更） | **100%** |

---

## 7. 强制编写规范

- **Mock 限制**：仅 Mock 外部依赖（文件系统、第三方API、时间），**严禁 Mock ORM/Model/事务/核心业务**。

- **Bug 修复**：必须补充对应回归测试。

- **AI 代码**：新增功能必须包含测试，否则视为不合格。

- **命名**：新测试统一使用 `test_should_..._when_...`。

- **数据独立**：每个测试用例独立生成数据，pytest-django 自动事务回滚。

---

## 8. 提交流程与门禁

| 阶段  | 操作                                         | 失败阻止          |
| --- | ------------------------------------------ | ------------- |
| 本地  | `pre-commit` + `pytest apps/<changed_app>` | 必须通过          |
| 提交前 | `pytest` 全量运行（至少核心模块）                      | 不通过则禁止提交      |
| CI  | 自动运行 `pytest --cov` + 覆盖率报告                | 覆盖率不达标 → 禁止合并 |
| 上线前 | 核心场景回归测试 + 并发测试                            | 全部通过          |

> ⚠️ 任何未通过覆盖率门禁或测试失败的 PR 将被拒绝合并。
