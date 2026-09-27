"""JWT 双通道认证 scheme 的 OpenAPI 护栏（BF-051）。

【为什么需要它】
``components.securitySchemes`` 的条目**只**由匹配到的
``OpenApiAuthenticationExtension`` 注册（drf-spectacular ``openapi.py:352-360``），
没有第二个来源；而 drf-spectacular **不自动 import 用户扩展模块**。这两条叠在一起，
使「扩展写错 / 忘了 import / scheme 名写错」三类失误全部**静默生效**——不抛异常、
不报 warning 之外的错，只是 ``securitySchemes`` 悄悄空着，而每个 operation 仍在
引用 ``BearerAuth``，形成**悬空 scheme 引用**（BF-051 实测：面 = 全部 267 个
operation，即 100% 端点）。

因此本文件不测「有没有写扩展」，而是测**最终产物**：

1. 扩展确实注册且能匹配认证类（锁死「忘了 import」）
2. ``securitySchemes`` 真的物化出两个 scheme，且 cookie 名与 settings 逐字一致
3. **全量 operation 的 security 引用均可解析**（核心：直击根因，未来新增认证类
   造成的同类悬空也会被这条抓住）
4. operation 数组逐字未变（反向护栏：防日后被「顺手改成引用」导致 267 处漂移）
5. 生成期不再有 ``could not resolve authenticator`` 告警

【与既有护栏的分工】
「参数/响应真的生效」由 DB 级运行时用例守护（见
``test_employee_openapi_contract.py`` 文件头），本文件只守护**声明侧**。
"""

import pytest
from django.conf import settings
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from apps.authusermanagement.authentication import JWTCookieAuthentication


# 允许匿名访问的 operation：它们的 security 形如 [{"BearerAuth": []}, {}]，
# 第二个元素 {} 表示「或无需认证」。除此以外**所有** operation 必须严格是
# 单元素形态 [{"BearerAuth": []}]。
ANONYMOUS_OPERATIONS = {
    ("/api/v1/auth/login/", "post"),
    ("/api/v1/auth/logout/", "post"),
    ("/api/v1/auth/register/", "post"),
    ("/api/v1/auth/token/refresh/", "post"),
    ("/api/v1/auth/users/", "post"),
    ("/api/v1/assets/public/scan/{recordcode}/", "get"),
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _iter_operations(schema):
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                yield path, method, operation


def _scheme_names(security) -> set[str]:
    """从 operation 的 security 数组里收集全部被引用的 scheme 名。"""
    return {name for requirement in security for name in requirement}


def test_extension_resolves_auth_class():
    """扩展已注册且能匹配到认证类——锁死「模块没被 import 则静默失效」。

    扩展靠 ``__init_subclass__`` 进 ``_registry``，而 drf-spectacular 不做模块自动
    发现，故注册完全依赖 ``AuthusermanagementConfig.ready()`` 里的显式 import。

    **本用例刻意不在此处 import 本项目的 schema 模块**：若 import 了，扩展就会在
    ready() 之前被注册，即使 ``ready()`` 被误删，本用例仍会通过——恰好漏掉要防的
    失效模式。改为断言「注册表里已经有一个能匹配的扩展」。
    """
    matched = OpenApiAuthenticationExtension.get_match(JWTCookieAuthentication())

    assert matched is not None, "JWTCookieAuthentication 无已注册的 OpenApi 认证扩展"
    # ``_matches()`` 会把 ``target_class`` 由字符串**解析并改写**为类对象
    # （plumbing.py::_load_class），故此处断言类对象而非字面量路径。
    assert matched.target_class is JWTCookieAuthentication
    assert matched.name == ["BearerAuth", "cookieJWT"]
    # 「只物化定义、不注入 operation」的约定本身也锁住：改回基类默认会变成 AND 语义
    assert matched.get_security_requirement(None) is None


def test_security_schemes_materialized(api_schema):
    """两个 scheme 均已物化，且 cookie 名与 settings 权威源逐字一致（不硬编码）。"""
    schemes = api_schema["components"]["securitySchemes"]

    assert set(schemes) == {"BearerAuth", "cookieJWT"}

    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schemes["BearerAuth"]["bearerFormat"] == "JWT"

    assert schemes["cookieJWT"]["type"] == "apiKey"
    assert schemes["cookieJWT"]["in"] == "cookie"
    # 逐字对齐 settings：字面量改了而扩展没跟上时，这条会红
    assert schemes["cookieJWT"]["name"] == settings.JWT_AUTH_COOKIE_ACCESS


def test_no_dangling_security_references(api_schema):
    """核心护栏：全量 operation 的 security 引用都必须能在 components 里解析。

    BF-051 的根因就是「operation 引用了从未物化的 BearerAuth」。本条不关心引用是否
    「应该」存在，只关心**引用必能解析**——新增认证类若忘了写扩展，会在这里被抓住。
    """
    declared = set(api_schema["components"].get("securitySchemes", {}))

    dangling: list[tuple[str, str, str]] = []
    for path, method, operation in _iter_operations(api_schema):
        for name in _scheme_names(operation.get("security", [])):
            if name and name not in declared:
                dangling.append((path, method, name))

    assert not dangling, f"以下 operation 引用了未声明的 security scheme：{dangling}"


def test_operation_security_unchanged(api_schema):
    """反向护栏：双 scheme 注册**不得**改动 operation 的 security 数组。

    逐字断言两种形态：需认证端点严格 ``[{"BearerAuth": []}]``；仅 6 个 AllowAny 端点
    允许多一个 ``{}``。``cookieJWT`` 在任何 operation 中出现即失败——那意味着有人把
    扩展的 ``get_security_requirement`` 改回了基类默认（AND 语义），会引入与运行时
    「双通道任一即可」相反的文档失真。
    """
    for path, method, operation in _iter_operations(api_schema):
        security = operation.get("security", [])
        if (path, method) in ANONYMOUS_OPERATIONS:
            assert security == [{"BearerAuth": []}, {}], f"{method} {path}: {security}"
        else:
            assert security == [{"BearerAuth": []}], f"{method} {path}: {security}"
        assert "cookieJWT" not in _scheme_names(security), f"{method} {path}"


def test_no_unresolved_authenticator_warning(api_schema):
    """生成期不得再有 ``could not resolve authenticator`` 告警。

    告警落在 ``drf_spectacular.drainage.GENERATOR_STATS``（``drainage.warn`` 在未传
    ``delayed`` 时走 ``GENERATOR_STATS.emit``），**不是** Python ``warnings``，故用
    ``recwarn`` 断言不到。``emit`` 无条件把格式化后的消息写入 ``_warn_cache``
    （drainage.py:90），且该 cache 是类级、进程内累积、按消息去重。

    刻意**不**调 ``GENERATOR_STATS.reset()``：那会连同本次生成的证据一起抹掉。
    直接断言「累积至今的告警里没有本认证类」，对累积免疫（缺席断言），且
    ``api_schema`` 参数已保证 schema 在本用例之前生成过、告警已入账。
    """
    unresolved = [
        message
        for message in GENERATOR_STATS._warn_cache
        if "could not resolve authenticator" in message and "JWTCookieAuthentication" in message
    ]
    assert not unresolved, unresolved


@pytest.mark.parametrize("scheme_name", ["BearerAuth", "cookieJWT"])
def test_scheme_definition_is_valid_security_scheme_object(api_schema, scheme_name):
    """OpenAPI 3 安全方案对象的两种合法形态，防止写出四不像的第三种。"""
    definition = api_schema["components"]["securitySchemes"][scheme_name]

    if definition["type"] == "http":
        assert definition["scheme"] in {"basic", "bearer", "digest", "mutual", "negotiate", "oauth2"}
    elif definition["type"] == "apiKey":
        assert definition["in"] in {"query", "header", "cookie"}
        assert isinstance(definition["name"], str) and definition["name"]
    else:
        pytest.fail(f"{scheme_name} 的 type 既非 http 也非 apiKey：{definition['type']}")
