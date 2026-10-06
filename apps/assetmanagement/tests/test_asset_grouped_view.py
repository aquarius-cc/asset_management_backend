"""资产分组汇总端点(B2)测试

对应 v2.3 §3.6 测试矩阵中属于 B2 的用例 11~14, 外加分页/补码衔接与
`PaginateAndRespondMixin` 钩子的回归护栏。

本文件只守「字段全集恰为 8 项 + price_min/price_max 不外泄」这条形状契约;
`group_key` / `price_display` 的**取值**与往返断言在 `test_asset_group_summary_fields.py`(B5)。
"""

from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.test import APIClient, APIRequestFactory

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.assetmanagement.serializers.asset_crud_serializers import AssetListSerializer
from apps.assetmanagement.tests.grouped_factories import (
    _cold,
    _make_asset,
    _make_contract,
    _make_dept,
    _make_employee,
)
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.mixins import PaginateAndRespondMixin
from core.pagination import CustomPageNumberPagination
from core.tests import TEST_PASSWORD


GROUPED_URL = "/api/v1/assets/grouped/"

# 汇总行字段全集（B5 落地后为 8 个 = 分组键 4 + group_key + 数量 + 价格展示 + 编码）
SUMMARY_FIELDS = {
    "group_key",
    "contract_code",
    "asset_name",
    "asset_specification",
    "asset_brand",
    "asset_count",
    "price_display",
    "asset_codes",
}


@pytest.fixture
def contract_c001(db: Any) -> Contract:
    return _make_contract("C001")


@pytest.fixture
def contract_c002(db: Any) -> Contract:
    return _make_contract("C002")


@pytest.fixture
def dept_a(db: Any) -> Department:
    return _make_dept("DA01", "部门A")


@pytest.fixture
def dept_b(db: Any) -> Department:
    return _make_dept("DB01", "部门B")


@pytest.fixture
def emp_a(db: Any, dept_a: Department) -> Employee:
    return _make_employee(dept_a, "empA", "员工A")


@pytest.fixture
def emp_b(db: Any, dept_b: Department) -> Employee:
    return _make_employee(dept_b, "empB", "员工B")


@pytest.fixture
def user_a(db: Any, emp_a: Employee) -> AuthUser:
    return AuthUser.objects.create_user(
        auth_username=emp_a.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002001"
    )


@pytest.fixture
def user_b(db: Any, emp_b: Employee) -> AuthUser:
    return AuthUser.objects.create_user(
        auth_username=emp_b.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002002"
    )


@pytest.fixture
def client_a(api_client: APIClient, user_a: AuthUser) -> APIClient:
    api_client.force_authenticate(user=user_a)
    return api_client


@pytest.mark.django_db
class TestGroupedEndpointEnvelope:
    """用例 11/12: 端点可达性与响应信封"""

    def test_url_reverse_matches_contract(self) -> None:
        """契约路径必须是 /api/v1/assets/grouped/(04 §2.4b.1)"""
        assert reverse("asset-grouped") == GROUPED_URL

    def test_envelope_and_pagination_keys(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001")

        resp = client_a.get(GROUPED_URL)

        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "查询成功"
        assert set(body["data"]) == {
            "count",
            "total_pages",
            "page",
            "page_size",
            "next",
            "previous",
            "results",
        }

    def test_result_row_shape_is_exactly_contract_fields(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001")

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert set(row) == SUMMARY_FIELDS
        # price_min / price_max 是内部聚合字段,不得外泄 —— 否则同一组价格有两种表达
        assert "price_min" not in row
        assert "price_max" not in row

    def test_null_group_key_dimensions_serialized_as_null(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", spec=None, brand=None, contract=None)

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert row["contract_code"] is None
        assert row["asset_specification"] is None
        assert row["asset_brand"] is None
        assert row["asset_codes"] == ["A001"]

    def test_count_is_group_count_not_asset_count(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """3 条资产同组 + 1 条异组 => count=2(组数), 而非 4(资产条数)"""
        for code in ("A001", "A002", "A003"):
            _make_asset(storage, asset_type, emp_a, code, contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=contract_c001)

        data = client_a.get(GROUPED_URL).json()["data"]

        assert data["count"] == 2
        assert sum(row["asset_count"] for row in data["results"]) == 4

    def test_requires_authentication(self, api_client: APIClient, db: Any) -> None:
        resp = api_client.get(GROUPED_URL)

        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestGroupedEndpointPaging:
    """分页衔接: 切片发生在补码之前"""

    def test_defaults_to_first_page_of_twenty(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        for i in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name=f"资产{i}")

        data = client_a.get(GROUPED_URL).json()["data"]

        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["results"]) == 3

    def test_page_size_clamped_to_max(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001")

        data = client_a.get(GROUPED_URL, {"page_size": "1000"}).json()["data"]

        assert data["page_size"] == 100

    def test_second_page_returns_distinct_group(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
    ) -> None:
        for i in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name=f"资产{i}")

        first = client_a.get(GROUPED_URL, {"page_size": "2"}).json()["data"]
        second = client_a.get(GROUPED_URL, {"page_size": "2", "page": "2"}).json()["data"]

        assert first["total_pages"] == 2
        assert len(first["results"]) == 2
        assert len(second["results"]) == 1
        first_codes = {code for row in first["results"] for code in row["asset_codes"]}
        second_codes = {code for row in second["results"] for code in row["asset_codes"]}
        assert not (first_codes & second_codes)

    def test_out_of_range_page_returns_404(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001")

        resp = client_a.get(GROUPED_URL, {"page": "999"})

        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert resp.json()["code"] == 404

    def test_query_count_independent_of_group_count(
        self,
        client_a: APIClient,
        user_a: AuthUser,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        django_assert_num_queries: Any,
    ) -> None:
        """核心护栏: 补码只发生在切页之后一次, 故查询数与分组数无关(无 N+1)

        4 次查询的固定构成(已用 CaptureQueriesContext 逐条打印核实):
          1) RBAC 把 AuthUser 解析为 Employee —— get_employee_for_user 的首次查找
          2) Paginator.count            —— SELECT COUNT(*) FROM (... GROUP BY ...) subquery
          3) 当页 SELECT                —— ... GROUP BY ... ORDER BY ... LIMIT n
          4) 当页 asset_codes           —— 按当页组键 OR 拼出的窄查询

        注: 第 1 次有请求级缓存(core/department_scope.py:26 的 user._rbac_employee),
        故每次测量前需 _cold() 清缓存, 否则同一 user 实例复用会少一次查询而误判为 N+1。
        若有人把补码提前到分页之前、或改为逐组取码, 组数一多此断言立即变红。
        """
        for i in range(2):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name=f"资产{i}")
        _cold(user_a)
        with django_assert_num_queries(4):
            first = client_a.get(GROUPED_URL, {"page_size": "20"}).json()["data"]

        for i in range(2, 8):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name=f"资产{i}")
        _cold(user_a)
        with django_assert_num_queries(4):
            grown = client_a.get(GROUPED_URL, {"page_size": "20"}).json()["data"]

        assert first["count"] == 2
        assert grown["count"] == 8


@pytest.mark.django_db
class TestGroupedEndpointFilters:
    """用例 13: 五个 query 参数端到端 + 互斥校验"""

    def test_filter_by_contract_code(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
        contract_c002: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=contract_c002)

        data = client_a.get(GROUPED_URL, {"contract_code": "C001"}).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["contract_code"] == "C001"

    def test_filter_by_no_contract_returns_sentinel_group_only(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=None)

        data = client_a.get(GROUPED_URL, {"no_contract": "true"}).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["contract_code"] is None
        assert data["results"][0]["asset_codes"] == ["B001"]

    def test_filter_by_status(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", status="in_use", contract=contract_c001)

        data = client_a.get(GROUPED_URL, {"asset_current_status": "in_use"}).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["asset_name"] == "服务器"

    def test_no_contract_false_returns_all_groups(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """HTTP 层显式 false = 不筛选（B1 只有 selector 级用例，传输层此前无覆盖）"""
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=None)

        data = client_a.get(GROUPED_URL, {"no_contract": "false"}).json()["data"]

        assert data["count"] == 2

    def test_multi_filters_are_anded(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
        contract_c002: Contract,
    ) -> None:
        """多条件为 AND 交集，且每个条件都真实参与收窄

        此前无任何多条件组合用例，单条件全绿不能证明 AND 语义（后写覆盖前的实现同样会全绿）。
        ⚠️ `asset_name` **不是**筛选参数而是分组键，传它会被当未知参数忽略 —— 组键维度不可筛。
        """
        printer_type = AssetType.objects.create(type_code="AT002", type_name="打印机")

        def _mk(code: str, *, at: AssetType, status: str, contract: Contract) -> Asset:
            return _make_asset(storage, at, emp_a, code, name="打印机", status=status, contract=contract)

        hit = _mk("A001", at=printer_type, status="in_use", contract=contract_c001)
        bad_status = _mk("A002", at=printer_type, status="in_store", contract=contract_c001)
        bad_type = _mk("A003", at=asset_type, status="in_use", contract=contract_c001)
        bad_contract = _mk("A004", at=printer_type, status="in_use", contract=contract_c002)

        def _codes(params: dict[str, str]) -> tuple[int, list[str]]:
            data = client_a.get(GROUPED_URL, params).json()["data"]
            return data["count"], sorted(c for row in data["results"] for c in row["asset_codes"])

        three = {
            "asset_current_status": "in_use",
            "contract_code": "C001",
            "asset_type_recordcode": printer_type.recordcode,
        }

        assert _codes(three) == (1, [hit.asset_code])
        # 逐对少一个条件 -> 命中集必须变宽, 证明三个条件各自都在收窄而非后写覆盖
        assert _codes({k: v for k, v in three.items() if k != "asset_type_recordcode"}) == (
            1,
            sorted([hit.asset_code, bad_type.asset_code]),
        )
        assert _codes({k: v for k, v in three.items() if k != "contract_code"}) == (
            2,
            sorted([hit.asset_code, bad_contract.asset_code]),
        )
        assert _codes({k: v for k, v in three.items() if k != "asset_current_status"}) == (
            1,
            sorted([hit.asset_code, bad_status.asset_code]),
        )

    def test_asset_codes_equals_asset_count_under_filters(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """I-1 在**筛选路径**下必须成立：每组 len(asset_codes) == asset_count

        B1 只在无筛选路径断言过（test_asset_codes_length_equals_asset_count）。而本端点
        的结构性风险恰在此：`build_summary_queryset` 与 `attach_asset_codes` 各自重算一次
        筛选集，任何一侧漂移都会让汇总数与明细数不一致，而响应本身不会报错。
        """
        for i in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name="打印机", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=None)
        _make_asset(storage, asset_type, emp_a, "C001", name="服务器", contract=contract_c001)

        params = {"contract_code": "C001", "asset_current_status": "in_store", "page_size": "1"}
        seen_pages = 0
        while True:
            data = client_a.get(GROUPED_URL, params).json()["data"]
            for row in data["results"]:
                assert len(row["asset_codes"]) == row["asset_count"], f"I-1 被破坏: {row}"
            seen_pages += 1
            if not data["next"] or seen_pages > data["total_pages"]:
                break
            params = {**params, "page": str(data["page"] + 1)}

        # 3 组命中筛选: 打印机x3(合同C001) / 服务器x1(C001) / 服务器x1(无合同被排除)
        assert data["count"] == 2
        assert seen_pages == 2

    def test_filter_by_type_and_storage(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)

        # asset_type_recordcode / asset_storage_recordcode 是 FK,契约口径为 recordcode
        # (非 type_code / storage_code —— 双尝试解析只对 `asset_type` 键生效)
        by_type = client_a.get(GROUPED_URL, {"asset_type_recordcode": asset_type.recordcode}).json()["data"]
        by_storage = client_a.get(GROUPED_URL, {"asset_storage_recordcode": storage.recordcode}).json()["data"]

        assert by_type["count"] == 1
        assert by_storage["count"] == 1

    def test_unknown_type_recordcode_returns_empty_not_all(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001")

        data = client_a.get(GROUPED_URL, {"asset_type_recordcode": "NO-SUCH-CODE"}).json()["data"]

        assert data["count"] == 0
        assert data["results"] == []

    def test_no_contract_with_contract_code_conflicts_400(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)

        resp = client_a.get(GROUPED_URL, {"no_contract": "true", "contract_code": "C001"})

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        body = resp.json()
        assert body["code"] == 400
        assert "no_contract" in body["message"]

    def test_invalid_no_contract_value_400(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """DRF BooleanField 的合法字面量含 yes/y/on/t/1 与其否向对应项(实测 TRUE_VALUES),
        故「非法」须取真正不在两侧集合中的值, 不能想当然写 yes。"""
        _make_asset(storage, asset_type, emp_a, "A001")

        resp = client_a.get(GROUPED_URL, {"no_contract": "maybe"})

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.json()["code"] == 400

    def test_yes_is_accepted_as_true(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """DRF 会把 yes 归一化为 True, 序列化器把 bool 交给 Selector, 两端口径一致"""
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器", contract=None)

        data = client_a.get(GROUPED_URL, {"no_contract": "yes"}).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["contract_code"] is None

    def test_blank_filter_treated_as_absent(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", contract=contract_c001)

        data = client_a.get(GROUPED_URL, {"contract_code": "", "no_contract": ""}).json()["data"]

        assert data["count"] == 1

    def test_ordering_param_cannot_override_contract_sort(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
    ) -> None:
        """排序由契约固定（asset_count desc 为主键），客户端不可控

        `ordering`/`search` 来自全局 DEFAULT_FILTER_BACKENDS，但本端点 filter_backends=[]
        且不调用 filter_queryset，故这两个参数既不出现在 OpenAPI，也不改变结果。
        本用例钉住该决策：若日后有人为分组端点加上 OrderingFilter，排序契约即被破坏。
        """
        # 组 A 数量 3，组 B 数量 1；故意让字典序与契约序相反
        for i in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{i:03d}", name="打印机")
        _make_asset(storage, asset_type, emp_a, "B001", name="服务器")

        contract_order = client_a.get(GROUPED_URL).json()["data"]["results"]
        forced_alpha = client_a.get(GROUPED_URL, {"ordering": "asset_name"}).json()["data"]["results"]
        forced_search = client_a.get(GROUPED_URL, {"search": "服务器"}).json()["data"]["results"]

        assert [r["asset_count"] for r in contract_order] == [3, 1]
        assert forced_alpha == contract_order
        assert forced_search == contract_order


@pytest.mark.django_db
class TestGroupedEndpointScope:
    """用例 14: 行级 RBAC 端到端"""

    def test_other_department_group_invisible(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        emp_b: Employee,
    ) -> None:
        _make_asset(storage, asset_type, emp_a, "A001", name="本部门资产")
        _make_asset(storage, asset_type, emp_b, "B001", name="他部门资产")

        data = client_a.get(GROUPED_URL).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["asset_name"] == "本部门资产"
        assert data["results"][0]["asset_codes"] == ["A001"]


class _StubPagedViewSet(PaginateAndRespondMixin, viewsets.GenericViewSet):
    """mixin 回归用最小视图"""

    queryset = Asset.objects.all()
    serializer_class = AssetListSerializer
    pagination_class = CustomPageNumberPagination


@pytest.mark.django_db
class TestPaginateAndRespondHookRegression:
    """`PaginateAndRespondMixin._post_paginate_hook` 不得改变既有调用方行为

    既有 6 处 `_paginate_and_respond` 调用点(damaged/recycle/out/waste)全部
    未覆写钩子, 故响应必须与加钩子之前逐字段一致。
    """

    def test_default_hook_returns_none(self) -> None:
        assert _StubPagedViewSet()._post_paginate_hook([{"a": 1}]) is None

    def test_hook_invoked_exactly_once_when_paginating(self, db: Any) -> None:
        calls: list[Any] = []

        class _Counting(_StubPagedViewSet):
            def _post_paginate_hook(self, page: Any) -> None:
                calls.append(page)

        view = _Counting()
        view.action_map = {"get": "list"}  # ViewSetMixin.initialize_request 依赖 as_view 注入
        view.format_kwarg = None  # 该属性由 perform_content_negotiation 赋值, 裸调不走 dispatch
        view.request = view.initialize_request(APIRequestFactory().get("/stub/"))  # type: ignore[assignment]
        view._paginate_and_respond(Asset.objects.all())

        assert len(calls) == 1

    def test_envelope_unchanged_for_existing_callers(self, client_a: APIClient, db: Any) -> None:
        resp = client_a.get("/api/v1/assets/assets/?page_size=5")

        assert resp.status_code == status.HTTP_200_OK
        body = resp.json()
        assert body["code"] == 0
        assert set(body["data"]) == {
            "count",
            "total_pages",
            "page",
            "page_size",
            "next",
            "previous",
            "results",
        }
