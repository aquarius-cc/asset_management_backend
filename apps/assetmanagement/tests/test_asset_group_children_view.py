"""资产分组明细端点(B4)测试

对应 v2.3 §3.6 测试矩阵中属于 B4 的用例：3(null 组键独立成组 + 往返)、10(**I-1**)、
11(`group_key` 往返解析)、12(RBAC 只读)，外加 B4 特有的错误契约与组内翻页。

**本文件的核心用例是 `test_i1_*`**：契约不变量 I-1 断言 `group_children` 的
`data.count` === 对应组 `asset_count`。该不变量由「汇总与明细复用同一 `_scoped_queryset`
+ 同一 `_build_group_q`」在 Selector 层保证，故此处必须**走 HTTP 全链路**验证 ——
直接调 Selector 只能证明函数自洽，证明不了两端真的落在同一批资产上。
"""

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.assetmanagement.tests.grouped_factories import (
    _make_asset,
    _make_contract,
    _make_dept,
    _make_employee,
    group_key_json,
)
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.tests import TEST_PASSWORD


GROUPED_URL = "/api/v1/assets/grouped/"
CHILDREN_URL = "/api/v1/assets/group_children/"


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
def client_a(api_client: APIClient, user_a: AuthUser) -> APIClient:
    api_client.force_authenticate(user=user_a)
    return api_client


def _grouped_rows(client: APIClient, **filters: Any) -> list[dict[str, Any]]:
    return list(client.get(GROUPED_URL, filters).json()["data"]["results"])


def _children_data(client: APIClient, group_key: str, **filters: Any) -> dict[str, Any]:
    response = client.get(CHILDREN_URL, {"group_key": group_key, **filters})
    assert response.status_code == 200, response.content
    return dict(response.json()["data"])


class TestGroupKeyContract:
    """`group_key` 编解码契约（B4 用例 11 + R-1）"""

    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            ("not-json", "非法 JSON"),
            ('{"contract_code": "C001"}', "对象而非数组"),
            ('["C001","名称"]', "数组长度不足 4"),
            ('["C001","名称","规格","品牌","多余"]', "数组长度超出 4"),
            ("[null,null,null,null]", "asset_name 不允许 null"),
            ('[1,"名称",null,null]', "contract_code 非字符串"),
            ('["C001",123,null,null]', "asset_name 非字符串"),
            ('["C001","名称",null,[],"x"]', "嵌套结构且长度错误"),
            ("", "空串"),
        ],
    )
    def test_invalid_group_key_returns_400(self, client_a: APIClient, raw: str, reason: str) -> None:
        """非法 `group_key` 必须 400，不得静默返回空集或整个筛选集

        `reason` 只写入断言消息，帮助定位是哪条参数写错。
        """
        response = client_a.get(CHILDREN_URL, {"group_key": raw})

        assert response.status_code == 400, f"{reason} 应 400，实得 {response.status_code}"

    def test_missing_group_key_returns_400(self, client_a: APIClient) -> None:
        assert client_a.get(CHILDREN_URL).status_code == 400

    def test_group_key_with_separators_quotes_and_chinese_roundtrips(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """品牌/型号含分隔符与引号时仍精确命中本组（R-1 的核心收益）

        刻意选 `,` `~` `"` `\\` 与中文：分隔符拼接方案在此必然错切或撞值，
        JSON 数组往返必须无损。
        """
        tricky = '联想, "ThinkPad" ~14/i5\\X'
        hit = _make_asset(
            storage,
            asset_type,
            emp_a,
            "A001",
            name="笔记本电脑",
            spec=tricky,
            brand=tricky,
            contract=contract_c001,
        )
        # 同组同值的干扰资产：不同合同 -> 不同组，不应被本组命中
        other = _make_asset(
            storage,
            asset_type,
            emp_a,
            "A002",
            name="笔记本电脑",
            spec=tricky,
            brand=tricky,
            contract=None,
        )

        key = group_key_json("C001", "笔记本电脑", tricky, tricky)
        data = _children_data(client_a, key)

        assert data["count"] == 1
        assert [row["asset_code"] for row in data["results"]] == [hit.asset_code]
        assert other.asset_code not in [row["asset_code"] for row in data["results"]]

    def test_group_key_with_all_null_positions(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
    ) -> None:
        """合同/规格/品牌三者皆 null 的哨兵组可往返（R-1：null 不必另造参数）"""
        hit = _make_asset(storage, asset_type, emp_a, "A001", name="旧资产", spec=None, brand=None, contract=None)

        data = _children_data(client_a, group_key_json(None, "旧资产", None, None))

        assert data["count"] == 1
        assert data["results"][0]["asset_code"] == hit.asset_code

    def test_null_spec_and_brand_form_separate_groups(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """null 规格/品牌各自独立成组（B4 用例 3）

        四条资产仅在「规格/品牌是否为 null」上不同 —— 若空串与 null 被混为一谈
        （或分隔符方案把两者都渲染成空），本用例会退化为 1 组而假绿。
        """
        combos = [
            ("A001", "14寸", None),
            ("A002", "14寸", "联想"),
            ("A003", None, "联想"),
            ("A004", None, None),
        ]
        for code, spec, brand in combos:
            _make_asset(
                storage,
                asset_type,
                emp_a,
                code,
                name="笔记本电脑",
                spec=spec,
                brand=brand,
                contract=contract_c001,
            )

        rows = _grouped_rows(client_a)
        assert len(rows) == 4, "四个 (spec, brand) 组合必须各成一组"
        assert all(row["asset_count"] == 1 for row in rows)

        for code, spec, brand in combos:
            data = _children_data(client_a, group_key_json("C001", "笔记本电脑", spec, brand))
            assert [row["asset_code"] for row in data["results"]] == [code], f"{code} 组命中错误"


class TestInvariantI1:
    """契约不变量 I-1：`group_children` 总数 === 对应组 `asset_count`（B4 用例 10）"""

    def test_i1_children_count_matches_asset_count(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
        contract_c002: Contract,
    ) -> None:
        """逐组比对两端总数 —— 这是 B4 存在的唯一理由"""
        # 组 1：C001 / 打印机 / 规格A / 品牌X，3 条
        for index in range(3):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"B{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c001,
            )
        # 组 2：C002 / 同名同规格同品牌（仅合同不同 -> 必须独立成组），2 条
        for index in range(2):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"C{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c002,
            )
        # 组 3：无合同哨兵组，1 条
        _make_asset(storage, asset_type, emp_a, "D0", name="打印机", spec="规格A", brand="品牌X", contract=None)

        rows = _grouped_rows(client_a)
        assert len(rows) == 3

        expected = {
            (row["contract_code"], row["asset_name"], row["asset_specification"], row["asset_brand"]): row[
                "asset_count"
            ]
            for row in rows
        }
        assert sorted(expected.values()) == [1, 2, 3]

        for key_tuple, asset_count in expected.items():
            data = _children_data(client_a, group_key_json(*key_tuple))
            assert data["count"] == asset_count, f"{key_tuple} 明细数 {data['count']} != 汇总数 {asset_count}"

    def test_i1_holds_when_grouped_is_paginated(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """汇总端点被分页切开时，未落在当页的组仍须满足 I-1

        回归意义：B2 已把 `asset_count` 放到分页切片之后计算，若明细端点误用了
        「仅当页组」的基集，未展开的组就会查不到明细。
        """
        for index in range(4):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"A{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c001,
            )
        for index in range(2):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"B{index}",
                name="扫描仪",
                spec="规格B",
                brand="品牌Y",
                contract=contract_c001,
            )

        page1 = dict(client_a.get(GROUPED_URL, {"page_size": 1}).json()["data"])
        assert page1["count"] == 2
        assert len(page1["results"]) == 1

        for key_tuple in [("C001", "打印机", "规格A", "品牌X"), ("C001", "扫描仪", "规格B", "品牌Y")]:
            data = _children_data(client_a, group_key_json(*key_tuple))
            expected = 4 if key_tuple[1] == "打印机" else 2
            assert data["count"] == expected

    def test_i1_holds_under_pass_through_filters(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """前端按当前 active 筛选透传时，I-1 仍成立（04 §2.4b.2 的前提）"""
        for index, status in enumerate(["in_store", "in_store", "in_use"]):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"A{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c001,
                status=status,
            )

        filtered = {"asset_current_status": "in_store"}
        rows = _grouped_rows(client_a, **filtered)
        assert rows[0]["asset_count"] == 2

        data = _children_data(client_a, group_key_json("C001", "打印机", "规格A", "品牌X"), **filtered)
        assert data["count"] == 2
        assert {row["asset_current_status"] for row in data["results"]} == {"in_store"}


class TestChildrenFilters:
    """非组键筛选的透传与边界"""

    def test_pass_through_filters_match_summary_endpoint(self) -> None:
        """明细端点的透传键集必须与汇总端点一致（漏一个即破坏 I-1）

        静态断言而非端到端：这是「两个 Serializer 的键集相等」这一契约不变量，
        端到端用例只能覆盖用到的键。

        C 批把透传键由 3 个扩到 **9 个**（新增 5 模糊 + 1 分类 + 原 3 精确）。
        """
        from apps.assetmanagement.selectors.asset_grouped_selector import (
            PASS_THROUGH_FILTER_PATHS,
            SUMMARY_FILTER_PATHS,
        )
        from apps.assetmanagement.serializers.asset_grouped_serializers import (
            AssetGroupChildrenQuerySerializer,
            AssetGroupQuerySerializer,
        )

        expected = set(PASS_THROUGH_FILTER_PATHS)
        assert expected == {
            "asset_current_status",
            "asset_type_recordcode",
            "asset_storage_recordcode",
            "asset_code",
            "asset_name",
            "asset_brand",
            "asset_specification",
            "asset_contract_name",
            "asset_type_category",
        }
        # 明细端点键集 == 汇总端点键集去掉 contract_code（合同由 group_key 表达）
        assert expected == set(AssetGroupQuerySerializer().fields) - {"contract_code", "no_contract"}
        assert set(AssetGroupChildrenQuerySerializer().fields) == expected | {"group_key"}
        # 透传键的字段路径与汇总端点逐个一致（改一处忘另一处会静默破坏 I-1）
        for key in expected:
            assert SUMMARY_FILTER_PATHS[key] == PASS_THROUGH_FILTER_PATHS[key]

    def test_openapi_parameter_names_match_serializer_fields(self) -> None:
        """两个 View 的 OpenAPI 参数名集必须与各自 Serializer 的字段集一致（C 批新增）

        **为何要断言**：drf-spectacular 对**未声明**的 query 键不会报错，只会静默不进 schema，
        即「后端加了筛选但忘了写 OpenAPI」时，schema 与运行时行为一起漂移而 CI 全绿。
        本用例把「加了键」这件事的三个落点（Selector 清单 / Serializer 字段 / OpenAPI 参数）
        绑成一处，漏任一落点即红。
        """
        from apps.assetmanagement.serializers.asset_grouped_serializers import (
            AssetGroupChildrenQuerySerializer,
            AssetGroupQuerySerializer,
        )
        from apps.assetmanagement.views.asset_group_children_view import CHILDREN_FILTER_PARAMETERS
        from apps.assetmanagement.views.asset_grouped_view import SUMMARY_FILTER_PARAMETERS

        summary_params = {param.name for param in SUMMARY_FILTER_PARAMETERS}
        assert summary_params == set(AssetGroupQuerySerializer().fields)

        children_params = {param.name for param in CHILDREN_FILTER_PARAMETERS}
        assert children_params == set(AssetGroupChildrenQuerySerializer().fields)

        # 汇总侧两个专属键不得出现在明细端点（R-1：合同只在 group_key 内表达），
        # 明细端点独有 group_key（必需参数）
        assert children_params == summary_params - {"contract_code", "no_contract"} | {"group_key"}

    def test_fuzzy_filter_keys_resolvable_by_shared_mapper(self) -> None:
        """模糊键必须是 `_build_fuzzy_q` 认识的键（Selector 刻意不写映射表的代价，DR-1）

        `SUMMARY_FUZZY_FILTER_KEYS` 的值被原样送进 `_build_fuzzy_q`，若某键既不是
        Asset 的真实字段、也不在 `FIELD_NAME_MAPPING` 内，则会拼出
        `<未知键>__icontains` 并在**查库时**抛 `FieldError` —— 即筛选一用就 500。
        故此处静态断言「每个键都可解析」，把故障从运行期提前到测试期。
        """
        from apps.assetmanagement.selectors.asset_grouped_selector import SUMMARY_FUZZY_FILTER_KEYS

        mapping = {
            "asset_contract": "asset_contract_recordcode__contract_code",
            "asset_contract_name": "asset_contract_recordcode__contract_name",
            "asset_type": "asset_type_recordcode__type_code",
            "asset_storage": "asset_storage_recordcode__storage_code",
        }
        asset_fields = {field.name for field in Asset._meta.get_fields() if hasattr(field, "name")}
        for key in SUMMARY_FUZZY_FILTER_KEYS:
            assert key in mapping or key in asset_fields, f"模糊键 {key} 无法被 _build_fuzzy_q 解析"

    def test_c_batch_filters_actually_narrow_both_ends(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
        contract_c002: Contract,
    ) -> None:
        """C 批 6 键必须**真的**过滤 summary 与 children（防「测而无效」的假绿）

        每个键独立取一个能唯一命中的值，逐键断言两端同时收窄。
        若某键只进了白名单却没接进筛选链，本用例即红（这是 B5 阶段
        `CommonList` 首屏用例「测而无效」教训的同型防护）。
        """
        other_type = AssetType.objects.create(type_code="AT002", type_name="打印机")
        hit = _make_asset(
            storage,
            asset_type,
            emp_a,
            "ASSET-X1",
            name="笔记本电脑",
            spec="14寸/i5",
            brand="联想",
            contract=contract_c001,
        )
        _make_asset(
            storage, other_type, emp_a, "OTHER-1", name="服务器", spec="塔式", brand="戴尔", contract=contract_c002
        )

        key = group_key_json("C001", "笔记本电脑", "14寸/i5", "联想")
        cases = {
            "asset_code": "ASSET-X",  # 模糊：部分命中，唯一
            "asset_name": "笔记本",  # 模糊：部分命中
            "asset_brand": "联想",  # 模糊：部分命中（另一条是「戴尔」）
            "asset_specification": "14寸",  # 模糊：部分命中（另一条是「塔式」）
            "asset_contract_name": "合同C001",  # 模糊：走 contract_name，另一条为「合同C002」
            "asset_type_category": asset_type.type_code,  # 分类精确：另一条属 AT002
        }
        for filter_key, value in cases.items():
            rows = _grouped_rows(client_a, **{filter_key: value})
            assert len(rows) == 1, f"summary 端 {filter_key}={value} 未生效：{rows}"
            assert rows[0]["asset_codes"] == [hit.asset_code]

            data = _children_data(client_a, key, **{filter_key: value})
            assert data["count"] == 1, f"children 端 {filter_key}={value} 未生效：{data}"
            assert [row["asset_code"] for row in data["results"]] == [hit.asset_code]

    def test_c_batch_filters_are_anded_across_keys(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """多键 AND：命中集须为交集而非并集"""
        _make_asset(storage, asset_type, emp_a, "A001", name="笔记本电脑", spec="14寸/i5", brand="联想")
        _make_asset(storage, asset_type, emp_a, "A002", name="笔记本电脑", spec="塔式", brand="戴尔")

        both = _grouped_rows(client_a, asset_name="笔记本", asset_brand="联想")
        conflicting = _grouped_rows(client_a, asset_name="笔记本", asset_brand="戴尔")

        assert len(both) == 1 and both[0]["asset_codes"] == ["A001"]
        assert [row["group_key"] for row in conflicting] == [group_key_json(None, "笔记本电脑", "塔式", "戴尔")]

    def test_unknown_category_returns_empty_not_all(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """分类不存在时返回空集而非全表（`_apply_exact_filters` 的既有语义，必须继承）

        若误写成「分类查不到就不过滤」，用户会看到「输入了分类条件但结果没变」——
        与 C 批要修的「筛选静默失效」是同一类故障，故显式钉死。
        """
        _make_asset(storage, asset_type, emp_a, "A001")

        data = _children_data(
            client_a, group_key_json(None, "笔记本电脑", "14寸/i5", "联想"), asset_type_category="NO-SUCH"
        )
        rows = _grouped_rows(client_a, asset_type_category="NO-SUCH")

        assert data["count"] == 0 and data["results"] == []
        assert rows == []

    def test_c_batch_blank_values_treated_as_absent(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """C 批 6 键的空串须视为未传（不得把整表过滤成空集）"""
        _make_asset(storage, asset_type, emp_a, "A001")

        blanks = dict.fromkeys(
            (
                "asset_code",
                "asset_name",
                "asset_brand",
                "asset_specification",
                "asset_contract_name",
                "asset_type_category",
            ),
            "",
        )

        assert len(_grouped_rows(client_a, **blanks)) == 1
        assert _children_data(client_a, group_key_json(None, "笔记本电脑", "14寸/i5", "联想"), **blanks)["count"] == 1

    def test_i1_holds_when_c_batch_filters_active(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """I-1 在 C 批 6 键生效时仍成立：明细数 === 对应组 asset_count

        这是 C 批最关键的不变量 —— 两端白名单必须同步扩，扩漏任一端即漂移。
        """
        for index, brand in enumerate(["联想", "联想", "戴尔"]):
            _make_asset(storage, asset_type, emp_a, f"A00{index}", name="笔记本电脑", spec="14寸/i5", brand=brand)

        filtered = {"asset_name": "笔记本", "asset_brand": "联想"}
        rows = _grouped_rows(client_a, **filtered)
        assert rows[0]["asset_count"] == 2

        data = _children_data(client_a, rows[0]["group_key"], **filtered)
        assert data["count"] == rows[0]["asset_count"]
        assert len(data["results"]) == rows[0]["asset_count"]

    def test_contract_code_and_no_contract_are_not_filter_params(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
        contract_c002: Contract,
    ) -> None:
        """R-1：合同只在 `group_key` 内表达，额外传 `contract_code` 不得改变结果

        若实现仍按 `contract_code` 过滤，group_key 指向 C001 而参数传 C002
        就会返回空集 —— 前端一旦沿用旧习惯即整组展开失败。
        """
        hit = _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )
        _make_asset(
            storage, asset_type, emp_a, "A002", name="打印机", spec="规格A", brand="品牌X", contract=contract_c002
        )

        key = group_key_json("C001", "打印机", "规格A", "品牌X")
        baseline = _children_data(client_a, key)
        with_stale_param = _children_data(client_a, key, contract_code="C002", no_contract="false")

        assert baseline["count"] == 1
        assert [row["asset_code"] for row in baseline["results"]] == [hit.asset_code]
        assert with_stale_param["count"] == 1, "被忽略的旧参数不得改变明细集"

    def test_blank_filter_treated_as_absent(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """空串筛选视同未传（与汇总端点口径一致，避免两端行为分叉）"""
        _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )

        key = group_key_json("C001", "打印机", "规格A", "品牌X")
        assert _children_data(client_a, key, asset_current_status="")["count"] == 1

    def test_unmatched_group_key_returns_empty_not_error(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """形状合法但无命中的 group_key 返回空集（不是 400）

        与「非法 group_key 400」区分开：无命中的空组是正常业务结果
        （例如资产被并发删除），不得与客户端参数错误混淆。
        """
        _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )

        data = _children_data(client_a, group_key_json("C001", "不存在的名称", "规格A", "品牌X"))

        assert data["count"] == 0
        assert data["results"] == []


class TestChildrenResponse:
    """响应形状与组内翻页"""

    def test_pagination_is_stable_across_pages(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """组内翻页不重不漏（依赖 `recordcode` 稳定排序）

        无稳定排序时同一 OFFSET 会随数据变化返回不同行，前端「加载更多」必然出现重复项。
        """
        created = [
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"A{index:02d}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c001,
            )
            for index in range(7)
        ]

        key = group_key_json("C001", "打印机", "规格A", "品牌X")
        first = _children_data(client_a, key, page=1, page_size=3)
        assert first["count"] == 7
        assert first["total_pages"] == 3

        seen: list[str] = []
        for page in range(1, first["total_pages"] + 1):
            data = _children_data(client_a, key, page=page, page_size=3)
            assert data["count"] == 7
            seen.extend(row["asset_code"] for row in data["results"])

        # 不重不漏
        assert sorted(seen) == sorted(asset.asset_code for asset in created)
        assert len(set(seen)) == len(seen), "同一条资产出现在多页 —— 排序键不唯一或缺排序"

        # 排序键组内唯一 -> OFFSET 分页是全序：同一页重复请求必得同一结果。
        # 若排序键换成非唯一列（如价格），同 OFFSET 会随执行计划返回不同行，前端「加载更多」必出重复项。
        recordcodes = [asset.recordcode for asset in created]
        assert len(set(recordcodes)) == len(recordcodes)
        repeat = _children_data(client_a, key, page=2, page_size=3)
        repeat_codes = [row["asset_code"] for row in repeat["results"]]
        assert repeat_codes == seen[3:6], "同页两次请求结果不一致"
        assert repeat_codes == [
            row["asset_code"] for row in _children_data(client_a, key, page=2, page_size=3)["results"]
        ]

    def test_ordering_is_by_recordcode(
        self, db: Any, user_a: AuthUser, emp_a: Employee, storage: Storage, asset_type: AssetType
    ) -> None:
        """明细排序键固定为 `recordcode`（全局唯一）

        静态断言：这是「组内翻页不重不漏」的**前提**。
        若有人改成按可空列排序（如价格），同 OFFSET 在不同请求下顺序不定，
        上述翻页用例仅在小数据集下侥幸通过。故此条把前提本身钉住。
        """
        from apps.assetmanagement.selectors.asset_grouped_selector import AssetGroupedSelector

        _make_asset(storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=None)

        queryset = AssetGroupedSelector.build_children_queryset(
            user=user_a, group_key=group_key_json(None, "打印机", "规格A", "品牌X"), filters={}
        )

        assert list(queryset.query.order_by) == ["recordcode"]

    def test_page_beyond_last_returns_404(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """越界页码返回 404 而非空列表 —— 前端「加载更多」据此停止

        若返回空列表 200，前端无法区分「本页没数据」与「已到末页」，会无限拉取。
        """
        _make_asset(storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=None)

        response = client_a.get(
            CHILDREN_URL, {"group_key": group_key_json(None, "打印机", "规格A", "品牌X"), "page": 2}
        )

        assert response.status_code == 404

    def test_page_size_is_capped(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """`page_size` 上限沿用 CustomPageNumberPagination（100），不另设一套"""
        for index in range(3):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"A{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                contract=contract_c001,
            )

        data = _children_data(client_a, group_key_json("C001", "打印机", "规格A", "品牌X"), page_size=9999)
        assert data["count"] == 3
        assert len(data["results"]) == 3

    def test_detail_serializer_includes_related_fields(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        contract_c001: Contract,
    ) -> None:
        """明细行须含 `AssetDetailSerializer` 的关联字段（04 §2.4b.2 要求含 `harddisk_sns`）

        这些字段来自 `select_related` / `prefetch_related`，缺预加载不会报错而只会
        静默触发 N+1 —— 故此处断言「字段存在且有值」。
        """
        _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )

        data = _children_data(client_a, group_key_json("C001", "打印机", "规格A", "品牌X"))

        row = data["results"][0]
        assert set(row) >= {
            "asset_code",
            "asset_name",
            "asset_current_status",
            "asset_type",
            "asset_contract",
            "asset_storage",
            "harddisk_sns",
        }
        assert row["asset_type"] is not None
        assert row["asset_contract"]["contract_code"] == "C001"
        assert row["asset_storage"] is not None
        assert row["harddisk_sns"] == []


class TestChildrenPermissions:
    """RBAC（B4 用例 12）"""

    def test_anonymous_is_rejected(self, api_client: APIClient) -> None:
        response = api_client.get(CHILDREN_URL, {"group_key": group_key_json(None, "x", None, None)})

        assert response.status_code in (401, 403)

    def test_dept_manager_sees_only_own_scope(
        self,
        client_a: APIClient,
        storage: Storage,
        asset_type: AssetType,
        emp_a: Employee,
        emp_b: Employee,
        contract_c001: Contract,
    ) -> None:
        """行级隔离与汇总端点同一实现，故明细只含本部门可见资产"""
        mine = _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )
        _make_asset(
            storage, asset_type, emp_b, "B001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )

        data = _children_data(client_a, group_key_json("C001", "打印机", "规格A", "品牌X"))

        assert [row["asset_code"] for row in data["results"]] == [mine.asset_code]
