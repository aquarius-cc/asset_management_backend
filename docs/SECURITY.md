# 项目安全规范 — 资产管理后端（Python/Django）

> 适用：Python 3.12+ | Django 6.0 | DRF 3.15+  
> 遵循最高准则：`AGENTS.md`（红线/必做指令）  
> 面向：人工开发者 + AI 代理

---

## 1. 权限控制（核心防线）

### 1.1 权限分层模型

所有资产相关接口必须经过 **四层校验**：

1. **全局认证**（JWT 有效性）
2. **视图级权限**（`permission_classes`）
3. **行级数据隔离**（重写 `get_queryset` 按用户组织/部门过滤）
4. **对象级权限**（`check_object_permissions`）

> 🔴 **资产模块专属红线**：审批、批量操作等敏感动作需增加 **业务权限** 第五层校验（如 Service 层校验状态流转合法性）。

### 1.2 模型级权限定义

Django 自动为每个模型创建 `add`/`change`/`delete`/`view` 基础权限。可按需扩展自定义权限：

```
python

# apps/assetmanagement/models.py

class Asset(BaseModel):
    # ... 字段

    class Meta:
        permissions = [
            ("export_asset", "Can export asset data"),
            ("batch_delete_asset", "Can batch delete assets"),
        ]
```

**权限分配**：通过 Django Admin 或代码将权限绑定到用户/组（Group）。

### 1.3 视图层权限实现

#### 接口级权限

```
python

# apps/assetmanagement/views.py

from rest_framework.permissions import IsAuthenticated
from .permissions import AssetPermission

class AssetViewSet(ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, AssetPermission]  # 全局 + 自定义
```

#### 行级数据隔离（强制）

```
python

def get_queryset(self):
    user = self.request.user
    # 普通用户仅返回本部门资产；管理员全部
    if user.is_superuser:
        return Asset.objects.all()
    return Asset.objects.filter(department=user.department)
```

#### 对象级权限（强制）

涉及单个资源的操作（`retrieve`/`update`/`partial_update`/`destroy`）必须显式调用 `check_object_permissions`：

```
python

def get_object(self):
    obj = super().get_object()
    self.check_object_permissions(self.request, obj)
    return obj
```

#### 自定义权限类

```
python

# apps/assetmanagement/permissions.py

from rest_framework.permissions import BasePermission
class IsAssetOwnerOrAdmin(BasePermission):
    """仅资产所属部门管理员或超管可操作"""
    def has_object_permission(self, request, view, obj):
        return request.user.is_superuser or obj.manager_department == request.user.department
```

---

## 2. 认证与 Token 管理

### 2.1 JWT 配置（使用 SimpleJWT）

```
python

# config/settings.py

from datetime import timedelta
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),   # ≤ 2 小时
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}
```

### 2.2 认证接口

使用 DRF SimpleJWT 自带视图：

```
python

# config/urls.py

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
urlpatterns = [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
```

### 2.3 401 异常统一处理

全局捕获 `AuthenticationFailed`，返回统一错误格式（不得泄露堆栈）：

```
python

# core/exceptions.py

from rest_framework.views import exception_handler
from rest_framework.exceptions import AuthenticationFailed
def custom_exception_handler(exc, context):
    if isinstance(exc, AuthenticationFailed):
        return Response(
            {"code": 40100, "msg": "认证失败或Token已过期", "data": None},
            status=401
        )
    return exception_handler(exc, context)
```

---

## 3. 敏感信息保护（资产系统重点关注）

### 3.1 环境变量管理

**禁止**在代码中硬编码任何密钥、密码、Token。

- 使用 `.env` 文件（已加入 `.gitignore`）存储敏感配置。

- `config/settings/production.py` 中通过 `os.getenv()` 强制读取，缺失则启动失败。

```python
# config/settings/base.py — 开发环境 fallback（仅限本地开发）
SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-only-key-change-in-production-1234567890")

# config/settings/production.py — 生产环境强制从环境变量读取
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY environment variable is required in production")
```

> **注意：** `base.py` 中的默认值仅供开发环境使用。生产部署必须设置 `DJANGO_SETTINGS_MODULE=config.settings.production` 并通过环境变量注入 `SECRET_KEY`，否则启动时会抛出 `ImproperlyConfigured` 异常。

### 3.2 敏感字段序列化控制

- 采购价、维保费用等字段：**必须**按用户权限动态脱敏或设置 `write_only=True`。

- 密码字段：**必须** `write_only=True`。

```
python

# serializers.py

class AssetDetailSerializer(serializers.ModelSerializer):
    purchase_price = serializers.SerializerMethodField()
    def get_purchase_price(self, obj):
        # 仅拥有 'view_price' 权限的用户可查看
        request = self.context.get('request')
        if request and request.user.has_perm('assetmanagement.view_price'):
            return obj.purchase_price
        return None
```

### 3.3 日志敏感信息遮蔽

日志中 **禁止** 打印完整 Token、密码、身份证号、采购价等敏感数据。

```
python

# core/logging.py

import re
from logging import Filter
class SensitiveDataFilter(Filter):
    def filter(self, record):
        # 遮蔽常见敏感字段
        record.msg = re.sub(r'password=.*?\s', 'password=*** ', str(record.msg))
        record.msg = re.sub(r'token=.*?\s', 'token=*** ', str(record.msg))
        return True
```

然后在 `LOGGING` 配置中引用：

```
python

LOGGING = {
    'filters': {
        'sensitive_filter': {
            '()': 'core.logging.SensitiveDataFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['sensitive_filter'],
        },
    },
    # ...
}
```

---

## 4. XSS 与输出安全

- DRF 返回 JSON 数据，前端渲染时需注意对用户输入数据进行转义。

- 若后端输出 HTML 片段（如提示消息），必须对富文本进行消毒：  
  推荐使用 `bleach` 限制允许的标签和属性。

```
python

import bleach
def sanitize_html(content):
    allowed_tags = ['p', 'br', 'strong', 'em']
    return bleach.clean(content, tags=allowed_tags, strip=True)
```

---

## 5. 输入校验（防注入与业务完整性）

### 5.1 Serializer 校验

- 字段级：`validate_<field>()`

- 对象级：`validate()` 处理跨字段逻辑（如状态流转前置校验）。

```
python

class AssetStatusChangeSerializer(serializers.Serializer):
    new_status = serializers.CharField()
    def validate_new_status(self, value):
        # 校验状态值是否合法
        if value not in dict(Asset.STATUS_CHOICES):
            raise serializers.ValidationError("无效的资产状态")
        return value
    def validate(self, data):
        # 资产管理专属：状态流转前置校验
        asset = self.context['asset']
        if not asset.can_change_to(data['new_status']):
            raise serializers.ValidationError("当前状态不允许变更到目标状态")
        return data
```

- **绝对禁止** 未校验的数据直接进入 Service 层。

### 5.2 模型层约束

利用 Django 字段约束（`unique`, `max_length`, `validators`）及 `clean()` 方法进行补充校验。

```
python

from django.core.exceptions import ValidationError
class Asset(BaseModel):
    sn = models.CharField(max_length=50, unique=True)
    def clean(self):
        if self.purchase_date > timezone.now().date():
            raise ValidationError("采购日期不能晚于当前日期")
```

### 5.3 文件上传安全

- 限制文件大小（如 ≤ 10MB）。

- 限制允许的 MIME 类型（如 PDF, PNG, JPEG）。

- 使用文件签名检验真实类型（可选）。

```
python

def validate_file(value):
    if value.size > 10 * 1024 * 1024:
        raise serializers.ValidationError("文件大小不超过10MB")
    allowed = ['application/pdf', 'image/png', 'image/jpeg']
    if value.content_type not in allowed:
        raise serializers.ValidationError("仅支持PDF/PNG/JPG文件")
```

---

## 6. 依赖安全

- 使用虚拟环境（`venv`）隔离依赖。

- 锁定依赖版本：`requirements.txt` 纳入版本控制。

- 定期审计已知漏洞：
  
  ```
  bash
  
  pip install pip-audit
  pip-audit
  ```
  
  或使用 `safety`。

- 升级依赖前检查 CHANGELOG，在测试环境验证后部署。

---

## 7. 环境安全

### 7.1 多环境配置

```text
config/
├── settings.py          # 公共配置
├── settings_dev.py      # 开发环境
└── settings_prod.py     # 生产环境
```

通过环境变量 `DJANGO_ENV` 加载对应配置。

### 7.2 生产环境强制项（🔴 上线前必查）

| 配置项                       | 要求                  | 说明                            |
| ------------------------- | ------------------- | ----------------------------- |
| `DEBUG`                   | `False`             | 绝对禁止生产环境开启                    |
| `ALLOWED_HOSTS`           | 显式指定域名              | 禁止使用 `["*"]`                  |
| `SECURE_SSL_REDIRECT`     | `True`（若前端启用 HTTPS） | 强制 HTTPS                      |
| `SECURE_PROXY_SSL_HEADER` | 配置反向代理 SSL          | 如 nginx X-Forwarded-Proto     |
| CSRF 保护                   | DRF 默认启用            | 若使用 Session 认证，需携带 CSRF Token |
| 数据库密码                     | 强密码，限制 IP 访问        | 定期备份                          |
| 日志级别                      | INFO 或 WARNING      | 禁止输出 debug 日志；日志文件轮转          |

---

## 8. 业务安全强化（资产系统特有）

| 实践        | 目标                    | 实现手段                              |
| --------- | --------------------- | --------------------------------- |
| **审计留痕**  | 所有资产核心变更记录操作人、时间、前后快照 | 信号 + Service 显式调用审计工具             |
| **事务安全**  | 库存/状态变更不可部分生效         | `@transaction.atomic` 包裹整个写操作     |
| **数据不可逆** | 已审核单据禁止直接修改/物理删除      | 通过红冲/反向单据实现；`is_delete` 软删除       |
| **唯一标识**  | 资产编码全局唯一，事务内生成        | `unique=True` + `editable=False`  |
| **幂等性**   | 创建接口防重复提交             | Idempotency-Key（存储于 Redis 并设 TTL） |

---

## 9. 提交前安全自检清单

| 类别       | 检查项                                                              |
| -------- | ---------------------------------------------------------------- |
| **权限**   | ✅ 所有视图配置 `permission_classes`，对象操作调用了 `check_object_permissions` |
|          | ✅ 实现了行级数据隔离（get_queryset 过滤）                                     |
|          | ✅ 自定义权限逻辑无越权漏洞                                                   |
| **认证**   | ✅ JWT 配置生效，Access Token 有效期 ≤ 2h                                 |
|          | ✅ 401 异常统一格式，无敏感信息泄漏                                             |
| **敏感信息** | ✅ 密钥、密码等通过环境变量管理，未硬编码                                            |
|          | ✅ Serializer 中敏感字段已设置 `write_only` 或动态脱敏                         |
|          | ✅ 日志输出已过滤敏感信息                                                    |
| **输入**   | ✅ Serializer / 模型层包含完整校验（含状态流转校验）                                |
|          | ✅ 文件上传限制了类型、大小                                                   |
| **环境**   | ✅ 生产环境 `DEBUG=False`，`ALLOWED_HOSTS` 已配置                         |
|          | ✅ 已执行 `pip-audit`，无已知高危漏洞                                        |
| **业务**   | ✅ 核心操作包裹事务，审计日志生成逻辑就绪                                            |
|          | ✅ 创建类接口已加入幂等键机制                                                  |

> ⚠️ 任何未通过此清单的变更不得合并至主分支。