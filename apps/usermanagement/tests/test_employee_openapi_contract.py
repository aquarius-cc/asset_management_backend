"""员工域 OpenAPI 契约回归（BF-049 / BF-050）。

**为什么需要这个文件**：BF-049 / BF-050 都是「运行时正确、OpenAPI 失真」类缺陷，
不会让任何既有测试变红——既有测试断言的是 HTTP 行为，没人断言文档。已实测：
BF-050 的三处错误（错误响应结构 / 无处可填的 path 参数 / 虚假分页参数）在
1595 个用例全绿的情况下长期存在。故此处把「基线必须与运行时一致」变成断言。

**护栏原理**：drf-spectacular 的「手工声明覆盖自动注入」机制只做替换、不做校正，
写错不报错。因此护栏必须**逐项对照运行时事实**断言，而不是快照整个文件
（快照会把无关变更卷进来，也指不出错在哪）。

**分工（避免重复造测试，DR-1/DR-2）**：
- 本文件只守护「文档声明」这一侧：参数/响应结构与运行时消费的事实是否一致。
- 「参数真的生效」已由 DB 级运行时用例守护，无需在此重复：
  ``test_employee_export.py:196`` keyword、``:226`` employee_status、
  ``:231`` department_code、``:258`` limit/offset。
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

from apps.usermanagement.models import EmployeeStatus


EXPORT_URL = "/api/v1/users/employees/export/"
STATS_URL = "/api/v1/users/employees/statistics/"

# 10 个走 Mixin 默认 get_export_queryset()（不跑 filter_queryset）的资产导出端点，
# 只声明 limit/offset 是如实的。operation-logs 导出自带业务参数 override，不属此类。
# 全基线共 12 个 export 路径 = 员工 1 + operation-logs 1 + 本集合 10。
BARE_ASSET_EXPORTS = {
    "/api/v1/assets/assets/export/",
    "/api/v1/assets/broken-assets/export/",
    "/api/v1/assets/contracts/export/",
    "/api/v1/assets/damaged-assets/export/",
    "/api/v1/assets/found-assets/export/",
    "/api/v1/assets/lost-assets/export/",
    "/api/v1/assets/out-assets/export/",
    "/api/v1/assets/recycle-assets/export/",
    "/api/v1/assets/repair-assets/export/",
    "/api/v1/assets/waste-assets/export/",
}


@pytest.fixture(scope="module")
def employee_schema():
    """整份 schema 只生成一次（module 级，避免每个用例重复 introspect 全量视图）。"""
    return SchemaGenerator().get_schema(request=None, public=True)


def _param_names(schema, url, method="get"):
    return {p["name"] for p in schema["paths"][url][method].get("parameters", [])}


def _param(schema, url, name, method="get"):
    return next(p for p in schema["paths"][url][method]["parameters"] if p["name"] == name)


# ------------------------------------------------------------------ BF-050


def test_statistics_response_is_aggregate_dict_not_paginated_list(employee_schema):
    """statistics 返回聚合字典，不得再声明为分页员工数组。"""
    response = employee_schema["paths"][STATS_URL]["get"]["responses"]["200"]
    ref = response["content"]["application/json"]["schema"]
    assert ref["$ref"] == "#/components/schemas/EmployeeStatistics"

    props = employee_schema["components"]["schemas"]["EmployeeStatistics"]["properties"]
    assert set(props) == {
        "total_employees",
        "active_employees",
        "by_status",
        "by_department",
    }


def test_statistics_drops_phantom_path_and_pagination_params(employee_schema):
    """``name``(path) 无处可填、page/page_size 端点不分页，三者必须消失。"""
    names = _param_names(employee_schema, STATS_URL)
    assert not names & {"name", "page", "page_size"}


def test_statistics_keeps_runtime_effective_filters(employee_schema):
    """修对响应会让自动筛选参数消失（``_is_list_view`` 启发式），必须显式找回。

    运行时 ``statistics`` 走 ``filter_queryset(get_queryset())``，确实接受这四个
    参数；一旦丢声明就退回「文档缺参」——即 BF-049/BF-050 的原症状。
    """
    names = _param_names(employee_schema, STATS_URL)
    assert {"employee_status", "department_code", "ordering", "search"} <= names


# ------------------------------------------------------------------ BF-049


def test_employee_export_declares_runtime_effective_filters(employee_schema):
    """员工导出走 ``_filtered_employee_queryset``，实际消费这些筛选参数，必须声明。"""
    names = _param_names(employee_schema, EXPORT_URL)
    assert {"keyword", "employee_status", "department_code", "ordering", "search"} <= names


def test_filter_params_keep_enum_and_pagination_declared(employee_schema):
    """两处回归防线：

    1. 手工追加 ``keyword`` 若覆盖而非合并自动注入，会削平 employee_status 的 enum
       （BF-047 回归）——手工声明是替换语义，必须锁死 enum。
    2. ``limit``/``offset`` 来自 Mixin 的共享 schema，追随其导入不能丢分页声明。

    enum 期望值直接取自 ``EmployeeStatus``（§3 跨端契约的权威源），不在测试里
    硬编码字面量：枚举演进时本用例应自动跟随，而不是靠人工同步。
    """
    expected = [code for code, _label in EmployeeStatus.choices]
    for url in (EXPORT_URL, STATS_URL):
        assert _param(employee_schema, url, "employee_status")["schema"]["enum"] == expected

    assert {"limit", "offset"} <= _param_names(employee_schema, EXPORT_URL)


def test_bare_asset_exports_not_overstated(employee_schema):
    """反向护栏：其余导出端点运行时**不**消费筛选参数，不得顺手工声明。

    误加会制造「文档有、运行时无」的反向失真——和 BF-049 同类，只是方向相反。
    """
    for url in BARE_ASSET_EXPORTS:
        assert _param_names(employee_schema, url) == {"limit", "offset"}, url
