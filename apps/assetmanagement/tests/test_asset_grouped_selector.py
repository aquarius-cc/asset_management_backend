"""资产分组聚合查询(B1)测试

对应 v2.3 §3.6 测试矩阵中属于 B1 的用例 1~9 与 15；
用例 5(price_display)/10(group_children)/11~14(端点与响应) 依赖 B2/B4/B5, 不在本文件。

B1 只负责「分组键聚合 + asset_count + price_min/max + asset_codes」,
`group_key` 与 `price_display` 由 B5 序列化器生成, 此处不重复断言。
"""

import pytest

from apps.assetmanagement.models import Asset, Contract
from apps.assetmanagement.selectors.asset_grouped_selector import (
    CONTRACT_CODE_PATH,
    GROUP_KEY_PATHS,
    AssetGroupedSelector,
)
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.tests import TEST_PASSWORD


def _make_asset(
    code,
    *,
    storage,
    asset_type,
    manager=None,
    contract=None,
    name="笔记本",
    spec="14寸",
    brand="联想",
    price=4500.00,
    status="in_store",
):
    return Asset.objects.create(
        asset_code=code,
        asset_name=name,
        asset_purchase_price=price,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_specification=spec,
        asset_brand=brand,
        asset_contract_recordcode=contract,
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_manager_recordcode=manager,
        asset_current_status=status,
    )


def _key(row):
    return tuple(row[path] for path in GROUP_KEY_PATHS)


@pytest.fixture
def contract_c001(db):
    return Contract.objects.create(
        contract_code="C001",
        contract_name="采购合同1",
        contract_amount=10000.00,
        contract_status="purchasing",
        contract_type="service",
        contract_start_date="2024-01-01",
        contract_end_date="2025-01-01",
    )


@pytest.fixture
def contract_c002(db):
    return Contract.objects.create(
        contract_code="C002",
        contract_name="采购合同2",
        contract_amount=20000.00,
        contract_status="purchasing",
        contract_type="service",
        contract_start_date="2024-01-01",
        contract_end_date="2025-01-01",
    )


@pytest.mark.django_db
class TestGroupKeyAggregation:
    """用例 1~4、6: 分组键正确性"""

    def test_four_keys_identical_forms_one_group(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 1
        assert rows[0]["asset_count"] == 2

    @pytest.mark.parametrize(
        ("field", "value"),
        [("name", "服务器"), ("spec", "15寸"), ("brand", "戴尔")],
    )
    def test_any_single_key_difference_splits_group(
        self, admin_auth_user, storage, asset_type, contract_c001, field, value
    ):
        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001, **{field: value})

        total, _rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 2

    def test_different_contract_splits_group(self, admin_auth_user, storage, asset_type, contract_c001, contract_c002):
        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c002)

        total, _rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 2

    def test_no_contract_goes_to_sentinel_group(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("G001", storage=storage, asset_type=asset_type)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 2
        # 两组 asset_count 相等(均为 1) -> 落到次键, 合同 null 置末, 哨兵组在后
        assert [row[CONTRACT_CODE_PATH] for row in rows] == ["C001", None]
        assert rows[1]["asset_codes"] == ["G001"]

    def test_null_brand_and_null_spec_each_form_own_group(self, admin_auth_user, storage, asset_type, contract_c001):
        """用例 3: null 品牌 / null 规格不得被合并成一组"""
        both_null = {"spec": None, "brand": None}
        spec_only_null = {"spec": None, "brand": "联想"}
        brand_only_null = {"spec": "14寸", "brand": None}

        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001, **both_null)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001, **spec_only_null)
        _make_asset("G003", storage=storage, asset_type=asset_type, contract=contract_c001, **brand_only_null)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 3
        assert all(row["asset_count"] == 1 for row in rows)
        assert len({_key(row) for row in rows}) == 3

    def test_asset_codes_length_equals_asset_count(self, admin_auth_user, storage, asset_type, contract_c001):
        """用例 6: asset_codes 与 asset_count 必须自洽(I-1 的 B1 侧前提)"""
        for i in range(3):
            _make_asset(f"G00{i}", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("G100", storage=storage, asset_type=asset_type, name="服务器")

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        for row in rows:
            assert len(row["asset_codes"]) == row["asset_count"]

    def test_soft_deleted_asset_excluded(self, admin_auth_user, storage, asset_type, contract_c001):
        deleted = _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001)
        deleted.delete()

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert total == 0
        assert rows == []


@pytest.mark.django_db
class TestPriceAggregation:
    """用例 5 的 B1 侧: price_min / price_max"""

    def test_same_price_gives_equal_min_max(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001, price=4500.00)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001, price=4500.00)

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert float(rows[0]["price_min"]) == 4500.00
        assert float(rows[0]["price_max"]) == 4500.00

    def test_different_price_gives_span(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("G001", storage=storage, asset_type=asset_type, contract=contract_c001, price=4500.00)
        _make_asset("G002", storage=storage, asset_type=asset_type, contract=contract_c001, price=5000.00)

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert float(rows[0]["price_min"]) == 4500.00
        assert float(rows[0]["price_max"]) == 5000.00


@pytest.mark.django_db
class TestSortingAndPaging:
    """用例 9、15"""

    def test_sort_by_asset_count_desc(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, name="笔记本")
        _make_asset("A002", storage=storage, asset_type=asset_type, contract=contract_c001, name="笔记本")
        _make_asset("B001", storage=storage, asset_type=asset_type, contract=contract_c001, name="服务器")

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert [row["asset_count"] for row in rows] == [2, 1]

    def test_sentinel_group_last_only_within_equal_count(self, admin_auth_user, storage, asset_type, contract_c001):
        """决策 13: 合同 nulls-last 是次键, 仅在数量相等时把哨兵组排到后面"""
        for i in range(2):
            _make_asset(f"A00{i}", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("Z001", storage=storage, asset_type=asset_type, name="服务器")

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert len(rows) == 2
        assert rows[0][CONTRACT_CODE_PATH] == "C001"
        assert rows[1][CONTRACT_CODE_PATH] is None

    def test_sentinel_group_first_when_count_higher(self, admin_auth_user, storage, asset_type, contract_c001):
        """数量更高时哨兵组按主键排前, 不得硬编码'恒在末位'"""
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("Z001", storage=storage, asset_type=asset_type, name="服务器")
        _make_asset("Z002", storage=storage, asset_type=asset_type, name="服务器")

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)

        assert rows[0][CONTRACT_CODE_PATH] is None
        assert rows[0]["asset_count"] == 2

    def test_sort_is_total_and_stable(self, admin_auth_user, storage, asset_type, contract_c001, contract_c002):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type, contract=contract_c002)
        _make_asset("C001", storage=storage, asset_type=asset_type, contract=contract_c001)

        first = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)[1]
        second = AssetGroupedSelector.list_group_summaries(user=admin_auth_user)[1]

        assert [_key(r) for r in first] == [_key(r) for r in second]

    def test_pagination_total_is_group_count_not_asset_count(self, admin_auth_user, storage, asset_type, contract_c001):
        """用例 9: data.count 语义为分组总数, 与 Σ asset_count 区分"""
        for i in range(3):
            _make_asset(f"A00{i}", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type, name="服务器")

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, page=1, page_size=1)

        assert total == 2
        assert len(rows) == 1
        assert sum(r["asset_count"] for r in rows) == 3

    def test_second_page_returns_remaining_group(self, admin_auth_user, storage, asset_type, contract_c001):
        for i in range(3):
            _make_asset(f"A00{i}", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type, name="服务器")

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, page=2, page_size=1)

        assert total == 2
        assert len(rows) == 1
        assert rows[0]["asset_count"] == 1

    def test_page_size_clamped_to_max(self, admin_auth_user, storage, asset_type, contract_c001):
        for i in range(4):
            _make_asset(f"A00{i}", storage=storage, asset_type=asset_type, name=f"资产{i}")

        _total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, page_size=9999)

        assert len(rows) == 4

    def test_out_of_range_page_returns_empty(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, page=99, page_size=20)

        assert total == 1
        assert rows == []


@pytest.mark.django_db
class TestFilterPassthrough:
    """用例 8"""

    def test_filter_by_status(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, status="in_store")
        _make_asset("A002", storage=storage, asset_type=asset_type, contract=contract_c001, status="in_use")

        total, rows = AssetGroupedSelector.list_group_summaries(
            user=admin_auth_user, filters={"asset_current_status": "in_use"}
        )

        assert total == 1
        assert rows[0]["asset_count"] == 1

    def test_filter_by_asset_type(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, _rows = AssetGroupedSelector.list_group_summaries(
            user=admin_auth_user, filters={"asset_type_recordcode": asset_type.recordcode}
        )

        assert total == 1

    def test_filter_by_storage(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, _rows = AssetGroupedSelector.list_group_summaries(
            user=admin_auth_user, filters={"asset_storage_recordcode": storage.recordcode}
        )

        assert total == 1

    def test_filter_by_contract_code(self, admin_auth_user, storage, asset_type, contract_c001, contract_c002):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type, contract=contract_c002)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, filters={"contract_code": "C001"})

        assert total == 1
        assert rows[0][CONTRACT_CODE_PATH] == "C001"

    @pytest.mark.parametrize("truthy", [True])
    def test_no_contract_filter_returns_sentinel_only(
        self, admin_auth_user, storage, asset_type, contract_c001, truthy
    ):
        """归一化后的 bool 才生效；查询串字面量解析是 Serializer 的职责（DR-1）"""
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type)

        total, rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, filters={"no_contract": truthy})

        assert total == 1
        assert rows[0][CONTRACT_CODE_PATH] is None

    @pytest.mark.parametrize("falsy", [False, None])
    def test_no_contract_falsy_does_not_filter(self, admin_auth_user, storage, asset_type, contract_c001, falsy):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type)

        total, _rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, filters={"no_contract": falsy})

        assert total == 2

    @pytest.mark.parametrize("misuse", ["true", "True", " true ", "yes", "on", "1", 1, 0])
    def test_non_bool_no_contract_rejected_not_silently_ignored(
        self, admin_auth_user, storage, asset_type, contract_c001, misuse
    ):
        """字符串/数字一律拒绝而非静默当作「未传」

        静默多返回数据比 400 更危险：调用方以为筛了，实际没筛。故此处钉死为响亮失败。
        `1` / `0` 同样拒绝——Python 里 `1 is True` 为 False，收紧可避免调用方误以为整数可用。
        """
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type)

        with pytest.raises(TypeError, match="必须是已归一化的 bool"):
            AssetGroupedSelector.list_group_summaries(user=admin_auth_user, filters={"no_contract": misuse})

    def test_no_contract_absent_key_does_not_filter(self, admin_auth_user, storage, asset_type, contract_c001):
        """键缺省（非 None）时安静视为不筛选，兼容 `filters` 默认空字典"""
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)
        _make_asset("B001", storage=storage, asset_type=asset_type)

        total, _rows = AssetGroupedSelector.list_group_summaries(user=admin_auth_user, filters={})

        assert total == 2

    def test_empty_filters_do_not_narrow(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001)

        total, _rows = AssetGroupedSelector.list_group_summaries(
            user=admin_auth_user, filters={"asset_current_status": None, "contract_code": ""}
        )

        assert total == 1

    def test_combined_filters_are_and_logic(self, admin_auth_user, storage, asset_type, contract_c001):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, status="in_store")
        _make_asset("A002", storage=storage, asset_type=asset_type, contract=contract_c001, status="in_use")

        total, rows = AssetGroupedSelector.list_group_summaries(
            user=admin_auth_user, filters={"contract_code": "C001", "asset_current_status": "in_use"}
        )

        assert total == 1
        assert rows[0]["asset_count"] == 1


@pytest.mark.django_db
class TestRowLevelScope:
    """用例 7: 行级 RBAC 隔离"""

    @pytest.fixture
    def dept_a(self, db):
        return Department.objects.create(department_code="DA01", department_name="部门A")

    @pytest.fixture
    def dept_b(self, db):
        return Department.objects.create(department_code="DB01", department_name="部门B")

    @pytest.fixture
    def emp_a(self, db, dept_a):
        return Employee.objects.create(
            employee_jobcode="empA",
            employee_name="员工A",
            employee_department=dept_a,
            employee_phone="13800001001",
            role="regular_user",
        )

    @pytest.fixture
    def emp_b(self, db, dept_b):
        return Employee.objects.create(
            employee_jobcode="empB",
            employee_name="员工B",
            employee_department=dept_b,
            employee_phone="13800001002",
            role="regular_user",
        )

    @pytest.fixture
    def user_a(self, db, emp_a):
        return AuthUser.objects.create_user(
            auth_username=emp_a.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002001"
        )

    @pytest.fixture
    def user_b(self, db, emp_b):
        return AuthUser.objects.create_user(
            auth_username=emp_b.employee_jobcode, password=TEST_PASSWORD, auth_phone="13800002002"
        )

    def test_user_sees_only_own_department_groups(self, storage, asset_type, contract_c001, user_a, emp_b):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, manager=emp_b)
        _make_asset(
            "B001", storage=storage, asset_type=asset_type, contract=contract_c001, name="服务器", manager=emp_b
        )

        total, rows = AssetGroupedSelector.list_group_summaries(user=user_a)

        assert total == 0
        assert rows == []

    def test_cross_department_asset_not_counted_in_group(
        self, storage, asset_type, contract_c001, emp_a, emp_b, user_a
    ):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, manager=emp_a)
        _make_asset("B001", storage=storage, asset_type=asset_type, contract=contract_c001, manager=emp_b)

        _total, rows = AssetGroupedSelector.list_group_summaries(user=user_a)

        assert len(rows) == 1
        assert rows[0]["asset_count"] == 1
        assert rows[0]["asset_codes"] == ["A001"]

    def test_user_b_sees_other_group_only(self, storage, asset_type, contract_c001, emp_a, emp_b, user_b):
        _make_asset("A001", storage=storage, asset_type=asset_type, contract=contract_c001, manager=emp_a)
        _make_asset(
            "B001", storage=storage, asset_type=asset_type, contract=contract_c001, name="服务器", manager=emp_b
        )

        _total, rows = AssetGroupedSelector.list_group_summaries(user=user_b)

        assert len(rows) == 1
        assert rows[0]["asset_count"] == 1
        assert rows[0]["asset_codes"] == ["B001"]
