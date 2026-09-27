"""员工域两套搜索口径的契约护栏（BF-052 遗留③）。

**背景**：员工域同时暴露两个都叫「搜索」但语义不同的查询参数，历史上没有任何
文档说明差异：

============  =========================================  =========================
参数          匹配口径                                    实现
============  =========================================  =========================
``?search=``  窄：仅 ``search_fields``（3 个字段）         DRF ``SearchFilter``
``?keyword=`` 宽：4 文本字段 + 部门名称 + 中文状态别名     ``EmployeeSelector.search_employees``
============  =========================================  =========================

DRF 侧自动产出的 ``?search=`` 描述只有泛化英文 ``A search term.``，既不说明字段集，
也不说明与 ``keyword`` 的差异；``?keyword=`` 的描述则只有「搜索关键词」四个字。消费方
按直觉选错就会拿到不同结果集，而**没有任何报错**。

**护栏分两层**（缺一不可）：

1. **功能性用例**（``TestSearchSemanticsDivergence``）——真调接口，证明「同一个词换
   参数结果不同」这个症状本身。若有人日后把两套口径「统一」（无论统一到哪一侧），
   本组用例会红，从而把「统一」这个决定变成**显式审批**而非静默重构。
2. **文档声明用例**（``TestSearchParamDocumentation`` / ``TestSearchParamDescriptionScope``）
   ——断言 OpenAPI 描述已说清差异，且**只**出现在真正暴露该参数的端点上。

**不重复造轮子（DR-1/DR-2）**：``?search=`` / ``?keyword=`` 是否**真的生效**由既有
DB 级运行时用例守护（``test_employee_export.py:196`` keyword、:226/:231 等），本文件
只守护「两者的差异被文档说清」与「差异确实存在」这一层。
"""

import pytest
from rest_framework import status

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.employee_search import (
    AND_SEMANTICS_HINT,
    keyword_param_description,
)
from apps.usermanagement.models import Department, Employee, EmployeeRole, EmployeeStatus
from apps.usermanagement.selectors import (
    SEARCH_DEPARTMENT_FIELD,
    SEARCH_STATUS_ALIASES,
    SEARCH_TEXT_FIELDS,
)
from apps.usermanagement.views.employee_view import EmployeeViewSet
from core.tests import TEST_PASSWORD


LIST_URL = "/api/v1/users/employees/"
SEARCH_URL = "/api/v1/users/employees/search/"
EXPORT_URL = "/api/v1/users/employees/export/"
STATS_URL = "/api/v1/users/employees/statistics/"
EMPLOYEE_URL_PREFIX = "/api/v1/users/employees"

#: 真正暴露 ``?search=`` 且与 ``?keyword=`` 并存的 4 个端点。
#: 必须与 EmployeeViewSet.search_param_description_actions 一致（由护栏互锁）。
SEARCH_PARAM_ENDPOINTS = {LIST_URL, SEARCH_URL, EXPORT_URL, STATS_URL}

#: 运行时**不**消费 ``?search=`` 的员工域 operation（detail / 批量 / 派生只读）。
#: 反向护栏：一旦 search 被注入这些 operation 即制造「文档有、运行时无」的失真。
#: 按 ``(路径, 方法)`` 列出——这些路由的方法集各不相同（如 ``batch-delete`` 仅 POST、
#: ``sort`` 仅 PUT），只列路径会让用例在取 ``get`` 键时 KeyError。
NON_SEARCH_EMPLOYEE_OPERATIONS = {
    "/api/v1/users/employees/{employee_jobcode}/": ("get", "put", "patch", "delete"),
    "/api/v1/users/employees/{employee_jobcode}/department/": ("get",),
    "/api/v1/users/employees/{employee_jobcode}/permissions/": ("get",),
    "/api/v1/users/employees/{employee_jobcode}/bind-auth-user/": ("post",),
    "/api/v1/users/employees/{employee_jobcode}/change_status/": ("post",),
    "/api/v1/users/employees/{employee_jobcode}/replace-auth-user/": ("post",),
    "/api/v1/users/employees/{employee_jobcode}/unbind-auth-user/": ("post",),
    "/api/v1/users/employees/employees/{employee_jobcode}/": ("get",),
    "/api/v1/users/employees/batch-create/": ("post",),
    "/api/v1/users/employees/batch-delete/": ("post",),
    "/api/v1/users/employees/active_employees/": ("get",),
    "/api/v1/users/employees/by-auth-user/{auth_id}/": ("get",),
    "/api/v1/users/employees/sort/": ("put",),
}

#: DRF SearchFilter 自动产出的原始描述。出现它即说明本次改写对该端点没生效。
LIBRARY_DEFAULT_SEARCH_DESCRIPTION = "A search term."


def _param(schema, url, name, method="get"):
    return next(p for p in schema["paths"][url][method]["parameters"] if p["name"] == name)


def _param_names(schema, url, method="get"):
    return {p["name"] for p in schema["paths"][url][method].get("parameters", [])}


def _operations_declaring(schema, url_prefix, param_name):
    """产出 ``url_prefix`` 下声明了 ``param_name`` 的全部 ``(url, method)``。

    ``paths`` 的 value 里混有 ``parameters`` / ``summary`` 等非 operation 键，故按
    HTTP 方法白名单过滤，而不是 ``isinstance`` 猜结构。
    """
    methods = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
    for url, operations in schema["paths"].items():
        if not url.startswith(url_prefix):
            continue
        for method in methods:
            operation = operations.get(method)
            if isinstance(operation, dict) and param_name in _param_names(schema, url, method):
                yield url, method


@pytest.fixture
def tech_department(db):
    """部门名含「技术部」——用于证明窄口径搜不到、宽口径搜得到。"""
    return Department.objects.create(
        department_code="TECH_D",
        department_name="技术部",
        parent=None,
        level=0,
        path="/TECH_D",
    )


@pytest.fixture
def sys_admin(db):
    """system_admin 角色：可见范围不受部门收窄，才能看到 tech_department 的员工。"""
    user = AuthUser.objects.create_user(
        auth_username="search_sys",
        password=TEST_PASSWORD,
        auth_phone="13700000001",
    )
    Employee.objects.create(
        employee_jobcode="search_sys",
        employee_name="搜索管理员",
        role=EmployeeRole.SYSTEM_ADMIN,
        employee_phone="13800000001",
    )
    return user


@pytest.fixture
def tech_employee(db, tech_department):
    """隶属「技术部」的员工——其部门名是窄口径**匹配不到**的唯一线索。"""
    return Employee.objects.create(
        employee_jobcode="TECH_E1",
        employee_name="张三",
        employee_department=tech_department,
        employee_phone="13800000002",
        employee_status=EmployeeStatus.ACTIVE,
    )


def _result_jobcodes(response):
    payload = response.json()["data"]
    return {row["employee_jobcode"] for row in payload["results"]}


# ------------------------------------------- 第一层：差异确实存在（功能性）


@pytest.mark.django_db
class TestSearchSemanticsDivergence:
    """把「两套口径不同」钉成事实——统一它必须先改这些用例。

    **端点选择**：只有 ``/search/`` 与 ``/export/`` 同时暴露两个参数。选 ``/search/``
    而非 ``/export/``，因为前者返回 JSON 可直接断言结果集；代价是它**强制要求**
    ``keyword``（``global_search`` 缺参即 ``error_response``），故每条用例都必须带上
    ``keyword``——而这恰好就是消费方真实的使用形态。
    """

    def test_adding_narrow_param_empties_department_name_result(self, api_client, sys_admin, tech_employee):
        """症状本体：部门名只在宽口径内，给查询**加上**窄参数反而把结果清空。

        「我搜技术部有结果，再加个 search=技术部让它更精确，怎么一条都没了」——这正是
        文档缺失导致的真实踩坑。部门名不在 ``search_fields`` 内，故交集为空。
        若日后有人把 ``department_name`` 加进 ``search_fields``「修好」这个不一致，
        本用例即红——那时应先决定统一到哪一侧，而不是让它悄悄发生。
        """
        api_client.force_authenticate(user=sys_admin)

        wide_only = api_client.get(SEARCH_URL, {"keyword": "技术部"})
        narrowed = api_client.get(SEARCH_URL, {"keyword": "技术部", "search": "技术部"})

        assert wide_only.status_code == status.HTTP_200_OK
        assert narrowed.status_code == status.HTTP_200_OK
        assert _result_jobcodes(wide_only) == {tech_employee.employee_jobcode}
        assert _result_jobcodes(narrowed) == set(), "search 含部门名，窄/宽口径已无差异"

    def test_adding_narrow_param_empties_status_alias_result(self, api_client, sys_admin, tech_employee):
        """状态别名同理：别名映射只存在于 Selector，``search`` 不认。

        ``employee_status`` 不在 ``search_fields`` 内，别名「在职」只在宽口径生效。
        宽口径结果是**包含**关系而非精确相等——``sys_admin`` 自身状态同为 active，
        按状态匹配本就该带上它，这里要断言的是「目标员工在集合内」+「收窄后清空」。
        """
        api_client.force_authenticate(user=sys_admin)
        alias = SEARCH_STATUS_ALIASES["active"][0]

        wide_only = api_client.get(SEARCH_URL, {"keyword": alias})
        narrowed = api_client.get(SEARCH_URL, {"keyword": alias, "search": alias})

        assert wide_only.status_code == status.HTTP_200_OK
        assert narrowed.status_code == status.HTTP_200_OK
        assert tech_employee.employee_jobcode in _result_jobcodes(wide_only)
        assert _result_jobcodes(narrowed) == set()

    def test_both_params_matching_keeps_row(self, api_client, sys_admin, tech_employee):
        """两个都匹配时交集**保留**该行——证明是 AND 而非「search 覆盖 keyword」。

        消费方最容易踩的第二个坑：多传一个参数直觉上以为「OR 放宽」，实际是收窄。
        ``filter_queryset`` 叠在 ``search_employees`` 结果之上，故为交集。
        """
        api_client.force_authenticate(user=sys_admin)

        response = api_client.get(SEARCH_URL, {"keyword": "技术部", "search": "张三"})
        assert _result_jobcodes(response) == {tech_employee.employee_jobcode}

    def test_search_alone_is_rejected_because_keyword_is_required(self, api_client, sys_admin, tech_employee):
        """``/search/`` 上 ``keyword`` 必填：只传 ``search`` 是 400，而非「按 search 搜」。

        锁定这条容易误解的接口事实：``search`` 在**本端点**并非独立可用的查询入口，
        它只能是 ``keyword`` 结果的收窄器。消费方若以为「search 能单独用」会拿到 400。
        """
        api_client.force_authenticate(user=sys_admin)

        response = api_client.get(SEARCH_URL, {"search": "技术部"})
        assert response.status_code != status.HTTP_200_OK

    def test_keyword_is_silent_noop_on_list_endpoint(self, api_client, sys_admin, tech_employee):
        """``?keyword=`` 在 list 端点是**静默空操作**：不读、不声明、且返回 200。

        故 list 端点**不得**声明 ``keyword``（声明了就是 §7 OC 口径下禁止的「文档超前于
        运行时」）。本用例锁定「不读」这一侧，声明侧由
        ``test_keyword_declared_only_where_runtime_reads_it`` 锁定。
        """
        api_client.force_authenticate(user=sys_admin)

        response = api_client.get(LIST_URL, {"keyword": "技术部"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["data"]["results"]) > 0, "list 端点应忽略 keyword 而返回全部可见员工"


# ------------------------------------------- 第二层：差异已被文档说清


class TestSearchParamDocumentation:
    """OpenAPI 描述必须说清字段集与两参数差异。"""

    def test_search_description_derived_from_search_fields(self, api_schema):
        """``search`` 描述的字段清单由视图 ``search_fields`` 派生，不得手写漂移。

        断言方式是「描述里出现 ``search_fields`` 的每个字段」而非逐字比对文案——
        这样往 ``search_fields`` 增删字段时，本用例仍应通过（描述自动跟随），
        只有派生断了才会红。
        """
        for url in SEARCH_PARAM_ENDPOINTS:
            description = _param(api_schema, url, "search")["description"]
            assert description != LIBRARY_DEFAULT_SEARCH_DESCRIPTION, url
            for field in EmployeeViewSet.search_fields:
                assert field in description, f"{url} 描述缺字段 {field}: {description}"

    def test_search_description_states_narrow_vs_wide(self, api_schema):
        """窄口径描述必须点明「不含部门名称与状态」并指向 keyword。"""
        for url in SEARCH_PARAM_ENDPOINTS:
            description = _param(api_schema, url, "search")["description"]
            assert "窄口径" in description, url
            assert "keyword" in description, url
            assert "AND" in description, f"{url} 未说明同传语义"

    def test_keyword_description_states_wide_semantics(self, api_schema):
        """``keyword`` 描述必须写出宽口径独有的两类匹配：部门名称与中文状态别名。"""
        for url in (SEARCH_URL, EXPORT_URL):
            description = _param(api_schema, url, "keyword")["description"]
            assert "宽口径" in description, url
            assert "部门名称" in description, url
            assert SEARCH_STATUS_ALIASES["active"][0] in description, url
            assert "AND" in description, url
            assert "窄口径" in description, f"{url} 未提示 search 是窄口径"

    def test_keyword_description_derived_from_selector_constants(self):
        """文案必须由 Selector 权威常量派生（DR-1），而非手写一份字段清单。

        手写必然随实现漂移——而「文档字段清单与实现分叉」正是本条要修的病本身。
        """
        description = keyword_param_description()
        for field in SEARCH_TEXT_FIELDS:
            assert field in description
        assert SEARCH_DEPARTMENT_FIELD in description

    def test_narrow_field_set_is_a_strict_subset_of_wide(self):
        """语义前提断言：窄口径字段是宽口径的**真子集**。

        若有人把 ``search_fields`` 加了宽口径之外的新字段，两套口径的差异性质就变了
        （不再只是「窄/宽」，可能变成「交叉」），此时上面所有「窄 vs 宽」的文案与用例
        都需重新审视。本用例先把它变成显式失败。
        """
        assert set(EmployeeViewSet.search_fields) < set(SEARCH_TEXT_FIELDS)

    def test_and_semantics_hint_is_shared_constant(self):
        """AND 语义提示必须与文案同源，避免两处各写一份后说法不一。"""
        assert "AND" in AND_SEMANTICS_HINT
        assert AND_SEMANTICS_HINT in keyword_param_description()


class TestSearchParamDescriptionScope:
    """反向护栏：描述只加在真正暴露该参数的端点上，且声明与运行时一致。"""

    def test_search_param_not_leaked_to_non_search_operations(self, api_schema):
        """``search`` 不得出现在 detail / 批量 / 派生只读 operation 上。

        这些 operation 运行时**不读** ``?search=``。一旦被注入即制造「文档有、运行时
        无」——与 BF-049/BF-050 同类，只是方向相反。
        """
        for url, methods in NON_SEARCH_EMPLOYEE_OPERATIONS.items():
            for method in methods:
                assert "search" not in _param_names(api_schema, url, method), f"{method.upper()} {url}"

    def test_search_param_endpoints_match_view_optin_list(self, api_schema):
        """互锁：schema 里带 ``search`` 的员工域端点集合 == 视图 opt-in 名单。

        两个方向都要锁：
        - **名单多登记**（action 在名单里却没暴露 ``search``）→ 文案写了却无处显示；
        - **名单漏登记**（新 action 暴露了 ``search`` 却没进名单）→ 该端点的 ``search``
          仍是库默认的 ``A search term.``，正是本次要修的失真。

        URL 与 action 名的对应由 drf-spectacular 生成，测试侧不重复推导（避免两处
        维护），故改为「schema 扫描出的 URL 集合与名单相等」+「名单内容固定」双重断言。
        """
        scanned = {url for url, method in _operations_declaring(api_schema, EMPLOYEE_URL_PREFIX, "search")}
        assert scanned == SEARCH_PARAM_ENDPOINTS
        assert EmployeeViewSet.search_param_description_actions == frozenset(
            {"list", "global_search", "export_excel", "statistics"}
        )

    def test_keyword_declared_only_where_runtime_reads_it(self, api_schema):
        """``keyword`` 只在运行时真读它的 2 个端点声明（list / statistics 不声明）。"""
        for url in (SEARCH_URL, EXPORT_URL):
            assert "keyword" in _param_names(api_schema, url), url
        for url in (LIST_URL, STATS_URL):
            assert "keyword" not in _param_names(api_schema, url), url

    def test_employee_endpoints_param_set_unchanged(self, api_schema):
        """端点与参数名集合不得因本次改写而增减（防注入/防丢失）。

        BF-050 的教训：手工声明是替换语义，修响应结构时会把自动注入的参数整体削平。
        """
        expected = {
            LIST_URL: {
                "department_code",
                "employee_department__department_code",
                "employee_status",
                "ordering",
                "page",
                "page_size",
                "search",
            },
            SEARCH_URL: {
                "department_code",
                "employee_department__department_code",
                "employee_status",
                "keyword",
                "ordering",
                "page",
                "page_size",
                "search",
            },
            EXPORT_URL: {
                "department_code",
                "employee_department__department_code",
                "employee_status",
                "keyword",
                "limit",
                "offset",
                "ordering",
                "search",
            },
            STATS_URL: {
                "department_code",
                "employee_department__department_code",
                "employee_status",
                "ordering",
                "search",
            },
        }
        for url, names in expected.items():
            assert _param_names(api_schema, url) == names, url

    def test_search_param_keeps_required_false(self, api_schema):
        """``search`` 必须保留 ``required: false``。

        库对 override 参数在 ``required=False`` 时会**整个省略该键**
        （``plumbing.py:390-391``）。本条改写走的是「改写自动发现结果」而非 override
        注入，正是为了保住这个键——否则基线 diff 会从「仅 description」变成
        「description + 丢键」。虽然二者语义等价（OpenAPI 3 中缺省即 false），但基线
        diff 应保持最小可审。
        """
        for url in SEARCH_PARAM_ENDPOINTS:
            assert _param(api_schema, url, "search")["required"] is False, url
