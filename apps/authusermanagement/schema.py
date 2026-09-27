"""JWT 双通道认证的 OpenAPI scheme 声明（BF-051）。

【背景：``components.securitySchemes`` 曾整体缺失】
``config/settings/base.py`` 曾在 ``SPECTACULAR_SETTINGS`` 里写::

    "SECURITY_SCHEMES": {"BearerAuth": {...}}   # ← drf-spectacular 无此设置项
    "SECURITY": [{"BearerAuth": []}],

但 drf-spectacular **0.29 没有 ``SECURITY_SCHEMES`` 这个设置项**（``settings.py`` 里
security 相关只有 ``'SECURITY': []``），未知键被**静默忽略**、不报错。后果是：

- ``components.securitySchemes`` 键**整体缺失**（不是空对象）；
- 而 ``"SECURITY"`` 只会往每个 operation 注入**裸引用**（``openapi.py:362``），
  于是**全部 267 个 operation 都引用了一个从不存在于 components 的 ``BearerAuth``**
  ——悬空 scheme 引用，面 = 100% 端点；
- 另叠加一条生成期告警：``could not resolve authenticator
  <JWTCookieAuthentication>``，凡使用该认证类的视图各打一次。

【唯一物化途径】
``components.securitySchemes`` 的条目**只**由匹配到的
``OpenApiAuthenticationExtension`` 注册（``openapi.py:352-360``），没有第二个来源。
故本模块提供该扩展。

【为什么 scheme 名沿用 ``BearerAuth``】
已有 267 个 operation 按 ``base.py:361`` 的 ``"SECURITY"`` 引用了这个名字。改用
新造名会让那 267 处引用**继续悬空**（等于没修），故 ``BearerAuth`` 逐字保留；
``cookieJWT`` 是本批新增的第二通道名。

【边界：只物化定义，不注入 operation】
``get_security_requirement()`` 显式返回 ``None``（基类默认会返回 ``{name: []}``）。
原因：本认证类**双通道任一即可**（Bearer 优先、Cookie 兜底，见
``authentication.py::JWTCookieAuthentication``），而基类对多个 name 返回的是
``{BearerAuth: [], cookieJWT: []}`` 这种 **AND** 语义（同时提供两者），与运行时相反；
若交给全局 ``"SECURITY"`` 继续提供 ``[{"BearerAuth": []}]`` 引用，则 operation 数组
零变化——两个通道都出现在 ``components.securitySchemes`` 里（Swagger UI 的 Authorize
可任选其一），但不改动 267 个 operation。

**不要"修回"基类默认实现**：那会引入 AND 语义的 security 要求，与运行时双通道
任一即可的行为不符（属新增的文档失真，方向与 BF-049/BF-050 相反）。
"""

from typing import Any

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object


__all__ = ["JWTCookieAuthenticationExtension"]


class JWTCookieAuthenticationExtension(  # type: ignore[no-untyped-call]
    OpenApiAuthenticationExtension
):
    """为 ``JWTCookieAuthentication`` 物化 Bearer + Cookie 两个 scheme 定义。"""

    # 上面的 type: ignore 针对基类 ``__init_subclass__`` 未标注类型——任何 drf-spectacular
    # 扩展子类化都会命中，非本项目代码问题（基类自带 py.typed，但该方法无签名）。
    target_class = "apps.authusermanagement.authentication.JWTCookieAuthentication"
    # 双通道用「名称列表 + 等长定义列表」（基类约定；类型标注为 str | list[str]，
    # 故用 list 而非 tuple——tuple 会被 mypy --strict 判为不兼容）
    name = ["BearerAuth", "cookieJWT"]

    def get_security_definition(self, auto_schema: Any) -> list[dict[str, Any]]:
        return [
            build_bearer_security_scheme_object(  # type: ignore[no-untyped-call]
                header_name="HTTP_AUTHORIZATION",
                token_prefix="Bearer",
                bearer_format="JWT",
            ),
            {
                "type": "apiKey",
                "in": "cookie",
                # 权威源取 settings，不硬编码字面量（DR-4：配置项单一入口）
                "name": settings.JWT_AUTH_COOKIE_ACCESS,
                "description": (
                    f"JWT access Cookie（HttpOnly，浏览器同源场景）。"
                    f"Cookie 名取自 settings.JWT_AUTH_COOKIE_ACCESS，"
                    f"当前为 {settings.JWT_AUTH_COOKIE_ACCESS}。"
                    f"与 Bearer 通道任一即可（Bearer 优先）。"
                ),
            },
        ]

    # 下面的 type: ignore 针对上游类型标注不完整：基类声明返回 dict | list[dict]，
    # 但 openapi.py:341 显式以 `is not None` 判定是否注入，即 None 是受支持取值。
    def get_security_requirement(self, auto_schema: Any) -> None:  # type: ignore[override]
        """返回 ``None``：只注册 scheme 定义，不往 operation 注入 security 要求。

        ``openapi.py:341`` 以 ``is not None`` 判定是否注入，而定义注册在其后独立
        执行，故返回 ``None`` 不影响 ``components.securitySchemes`` 的物化。

        基类默认实现会返回 ``{name: []}``；对多 name 返回的是 **AND** 语义（两个通道
        须同时提供），与运行时「Bearer 优先、Cookie 兜底，任一即可」相反，故不复用。
        """
        return None
