"""资产分组汇总的 `group_key` / `price_display`（B5）测试

对应 v2.3 §3.6 用例 5（`price_display` 单值 / 区间两态）与用例 11（`group_key` 往返），
外加 B5 特有的**编码侧 ↔ 解码侧一致性**验证。

**本文件的存在理由**：B4 交付了 `group_children`，但 `group_key` 的**编码侧**归 B5。
B5 落地前，前端拿不到 `group_key`，两个端点之间是断的。本文件的核心用例
`TestGroupKeyRoundTrip` 走完整 HTTP 链路把两端接上 —— 它验证的不只是「字段存在」，
而是「汇总吐出的 `group_key` 真的能被明细端点消费且命中同一组」。
"""

from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import AssetType, Contract, Storage
from apps.assetmanagement.serializers.asset_grouped_serializers import format_price
from apps.assetmanagement.tests.grouped_factories import (
    _make_asset,
    _make_contract,
    _make_dept,
    _make_employee,
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
def dept_a(db: Any) -> Department:
    return _make_dept("DA01", "部门A")


@pytest.fixture
def emp_a(db: Any, dept_a: Department) -> Employee:
    return _make_employee(dept_a, "empA", "员工A")


@pytest.fixture
def user_a(db: Any, emp_a: Employee) -> AuthUser:
    return AuthUser.objects.create_user(
        auth_username=emp_a.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002001"
    )


@pytest.fixture
def client_a(api_client: APIClient, user_a: AuthUser) -> APIClient:
    api_client.force_authenticate(user=user_a)
    return api_client


class TestGroupKeyEncoding:
    """`group_key` 编码侧（B5）"""

    def test_group_key_is_four_element_array_in_contract_order(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """数组顺序 = [contract_code, asset_name, asset_specification, asset_brand]

        顺序即契约。若有人按「字母序」或「模型字段序」重排，四项齐全时形状校验仍会通过，
        但 B4 会拿错位置去过滤 —— 得到空集或错组。故此处逐位断言而非只断言长度。
        """
        import json

        _make_asset(
            storage, asset_type, emp_a, "A001", name="笔记本电脑", spec="14寸/i5", brand="联想", contract=contract_c001
        )

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert json.loads(row["group_key"]) == ["C001", "笔记本电脑", "14寸/i5", "联想"]

    def test_null_dimensions_are_json_null_not_empty_string(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee
    ) -> None:
        """null 组键位必须是 JSON `null`，不得是空串或字符串 "null"

        三者对 B4 的意义完全不同：空串会匹配不到任何行（模型字段是 NULL 而非 ""），
        字符串 "null" 则会真的去查名为 "null" 的合同。往返后必须仍是 `None`。
        """
        import json

        _make_asset(storage, asset_type, emp_a, "A001", name="旧资产", spec=None, brand=None, contract=None)

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]
        decoded = json.loads(row["group_key"])

        assert decoded == [None, "旧资产", None, None]
        assert [type(item).__name__ for item in decoded] == ["NoneType", "str", "NoneType", "NoneType"]

    def test_chinese_and_separators_are_not_escaped(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """中文保持原文，不转义为 \\uXXXX

        契约示例（04 §2.4b.1）中 `group_key` 为 `"[\"HT00001\",\"笔记本电脑\",...]"`。
        两种写法都能被 `json.loads` 解析，故本条不测功能、只测**契约一致性** ——
        转义串会让前端缓存键与抓包结果不可读，排查问题时极难肉眼比对。
        """
        _make_asset(
            storage,
            asset_type,
            emp_a,
            "A001",
            name="笔记本电脑",
            spec='14寸/i5, "含引号"',
            brand="联想~特别版",
            contract=contract_c001,
        )

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert "\\u" not in row["group_key"]
        assert "笔记本电脑" in row["group_key"]

    def test_group_key_is_unique_per_group(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """不同分组的 `group_key` 互不相同

        前端按 `group_key` 做明细缓存 Map（v2.3 §3.8）的**前提**。
        若两组键值相同，两个组的缓存会互相覆盖 —— 展开 A 组却显示 B 组明细，
        且因 I-1 在单组内仍成立而**不会被任何单组断言发现**。
        """
        _make_asset(
            storage, asset_type, emp_a, "A001", name="打印机", spec="规格A", brand="品牌X", contract=contract_c001
        )
        _make_asset(storage, asset_type, emp_a, "A002", name="打印机", spec="规格A", brand="品牌X", contract=None)
        _make_asset(
            storage, asset_type, emp_a, "A003", name="扫描仪", spec="规格A", brand="品牌X", contract=contract_c001
        )

        rows = client_a.get(GROUPED_URL).json()["data"]["results"]

        assert len(rows) == 3
        keys = [row["group_key"] for row in rows]
        assert len(set(keys)) == 3, f"存在重复 group_key：{keys}"


class TestPriceDisplay:
    """`price_display`（B5，用例 5）"""

    @pytest.mark.parametrize(
        ("low", "high", "expected"),
        [
            (Decimal("4500.00"), Decimal("4500.00"), "4500.00"),
            (Decimal("4500.00"), Decimal("5000.00"), "4500.00~5000.00"),
            (Decimal("5000.00"), Decimal("4500.00"), "5000.00~4500.00"),
            (Decimal("4500"), Decimal("4500"), "4500.00"),
            (Decimal("0.5"), Decimal("0.5"), "0.50"),
            (Decimal("0"), Decimal("0"), "0.00"),
        ],
    )
    def test_format_price_two_states(self, low: Decimal, high: Decimal, expected: str) -> None:
        """单值态 / 区间态 + 两位小数（纯函数，不依赖 DB）"""
        assert format_price(low, high) == expected

    def test_format_price_none_returns_empty(self) -> None:
        """不可达的 None 兜底：返回空串而非抛错

        `asset_purchase_price` 是 NOT NULL 列且分组恒非空，故此分支在生产不可达；
        保留它是为了让「数据被外部改坏」时退化为空展示，而不是整个端点 500。
        """
        assert format_price(None, None) == ""
        assert format_price(Decimal("1"), None) == ""

    def test_single_asset_group_shows_single_price(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """单条资产的组必然 min==max -> 单值态"""
        _make_asset(storage, asset_type, emp_a, "A001", price=4500.00, contract=contract_c001)

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert row["price_display"] == "4500.00"

    def test_uniform_price_group_shows_single_value(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """多条资产但单价全同 -> 仍是单值态（不是区间）"""
        for index in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{index}", price=4500.00, contract=contract_c001)

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert row["asset_count"] == 3
        assert row["price_display"] == "4500.00"

    def test_mixed_price_group_shows_ascending_range(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """单价不一致 -> `min~max`，且恒为升序（与录入顺序无关）"""
        for index, price in enumerate([5000.00, 4500.00, 4800.00]):
            _make_asset(storage, asset_type, emp_a, f"A{index}", price=price, contract=contract_c001)

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]

        assert row["price_display"] == "4500.00~5000.00"

    def test_price_display_independent_of_asset_order(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """价格区间与聚合排序无关：即使该组排在第二页，price_display 仍正确"""
        for index in range(3):
            _make_asset(storage, asset_type, emp_a, f"A{index}", price=9000.00, contract=contract_c001)
        for index in range(4):
            _make_asset(storage, asset_type, emp_a, f"B{index}", name="扫描仪", price=100.00, contract=contract_c001)

        page2 = client_a.get(GROUPED_URL, {"page_size": 1, "page": 2}).json()["data"]["results"][0]

        assert page2["asset_count"] == 3
        assert page2["price_display"] == "9000.00"


class TestGroupKeyRoundTrip:
    """编码侧 ↔ 解码侧一致性 —— B4 与 B5 之间的桥梁（B5 的核心价值）"""

    @pytest.fixture
    def four_groups(self, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract) -> None:
        """四组数据，覆盖合同有/无 × 规格品牌有/无的组合"""
        # 组 A：C001 / 全字段齐备，3 条
        for index in range(3):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"A{index}",
                name="打印机",
                spec="规格A",
                brand="品牌X",
                price=4500.00,
                contract=contract_c001,
            )
        # 组 B：无合同 + 规格/品牌皆 null（哨兵组），1 条
        _make_asset(storage, asset_type, emp_a, "B0", name="旧资产", spec=None, brand=None, price=100.00, contract=None)
        # 组 C：C001 / null 规格 + 有品牌，2 条
        for index in range(2):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"C{index}",
                name="扫描仪",
                spec=None,
                brand="品牌Y",
                price=2000.00 + index,
                contract=contract_c001,
            )
        # 组 D：C001 / 有规格 + null 品牌，2 条
        for index in range(2):
            _make_asset(
                storage,
                asset_type,
                emp_a,
                f"D{index}",
                name="复印机",
                spec="规格B",
                brand=None,
                price=3000.00,
                contract=contract_c001,
            )

    def test_every_group_key_feeds_group_children(self, client_a: APIClient, four_groups: None) -> None:
        """**桥梁用例**：汇总每一行的 `group_key` 原样回传明细端点，`count` === `asset_count`

        这是 v2.3 §2.4b.2 契约不变量 I-1 在**真实数据通路**上的验证：
        前端拿 `grouped` 的响应直接展开，全程无需自己拼任何参数。
        B4 落地时因汇总端点没有 `group_key` 而无法验证，本用例是它的补完。
        """
        rows = client_a.get(GROUPED_URL).json()["data"]["results"]

        assert len(rows) == 4
        for row in rows:
            response = client_a.get(CHILDREN_URL, {"group_key": row["group_key"]})
            assert response.status_code == 200, f"{row['group_key']} -> {response.content}"
            data = response.json()["data"]
            assert data["count"] == row["asset_count"], f"{row['group_key']} 明细数与汇总数不符"
            # 明细的组键四维必须与汇总行一致（否则说明 group_key 编码错位）
            for detail in data["results"]:
                assert detail["asset_name"] == row["asset_name"]
                assert detail["asset_specification"] == row["asset_specification"]
                assert detail["asset_brand"] == row["asset_brand"]
                contract = detail["asset_contract"]
                assert (contract or {}).get("contract_code") == row["contract_code"]

    def test_group_key_survives_pass_through_filters(self, client_a: APIClient, four_groups: None) -> None:
        """带筛选展开时桥梁依然成立（前端透传 active 筛选的场景）"""
        filtered = {"asset_current_status": "in_store"}

        rows = client_a.get(GROUPED_URL, filtered).json()["data"]["results"]
        assert len(rows) == 4

        for row in rows:
            data = client_a.get(CHILDREN_URL, {"group_key": row["group_key"], **filtered}).json()["data"]
            assert data["count"] == row["asset_count"]

    def test_group_key_round_trips_through_url_encoding(
        self, client_a: APIClient, storage: Storage, asset_type: AssetType, emp_a: Employee, contract_c001: Contract
    ) -> None:
        """`group_key` 经 URL 编码后仍无损（中文与引号是真正的考验）

        前端用 `request.get(url, {group_key})` 传参，axios 会 URL-encode。
        含中文与 `"` 的 JSON 数组必须在解码后与编码前逐字节一致。
        """
        spec = '14寸/i5, "含引号" \\反斜杠'
        _make_asset(
            storage, asset_type, emp_a, "A001", name="笔记本电脑", spec=spec, brand="联想", contract=contract_c001
        )

        row = client_a.get(GROUPED_URL).json()["data"]["results"][0]
        data = client_a.get(CHILDREN_URL, {"group_key": row["group_key"]}).json()["data"]

        assert data["count"] == 1
        assert data["results"][0]["asset_specification"] == spec
