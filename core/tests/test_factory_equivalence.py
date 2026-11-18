"""工厂等价性门禁（MA-23 包 1a）：证明「工厂造数」≡「存量手写 create 造数」。

三层证据（缺一不可）：
1. **值等价**：同一组显式入参下，``Factory.build()`` 与手写构造的**全部具体字段**逐项相等
   （含默认值），证明工厂没有偷偷改写任何字段语义。
2. **持久化等价**：工厂 ``create()`` 后从 DB 重读，字段快照与内存实例一致，
   证明落盘路径（含 ``AuthUserManager.create_user`` 的密码哈希）无偏差。
3. **零副作用**：工厂不得静默多造关联对象（可空外键默认 ``None``）、
   不得越权绑定 ``Employee.auth_user``（模型禁止直写）。

覆盖模型：Department / Employee / AuthUser / AssetType / Storage / Contract / Asset。
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.assetmanagement.tests.factories import (
    AssetFactory,
    AssetTypeFactory,
    ContractFactory,
    StorageFactory,
)
from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.tests.factories import AuthUserFactory, SuperUserFactory
from apps.usermanagement.models import Department, Employee
from apps.usermanagement.tests.factories import DepartmentFactory, EmployeeFactory
from core.tests import TEST_PASSWORD


#: 自动生成/时间戳字段：两条构造路径本就不应相等，不参与比较
_VOLATILE_FIELDS = frozenset({"recordcode", "created_at", "updated_at"})


def _snapshot(obj: object) -> dict[str, object]:
    """取对象全部具体字段（FK 取 ``*_id``），排除主键与易变字段。"""
    model = obj._meta  # type: ignore[attr-defined]
    values: dict[str, object] = {}
    for field in model.concrete_fields:
        if field.primary_key or field.name in _VOLATILE_FIELDS:
            continue
        values[field.attname] = getattr(obj, field.attname)
    return values


def _assert_same_fields(left: object, right: object, *, ignore: set[str] | None = None) -> None:
    skip = ignore or set()
    left_values = {k: v for k, v in _snapshot(left).items() if k not in skip}
    right_values = {k: v for k, v in _snapshot(right).items() if k not in skip}
    assert left_values == right_values, (
        f"字段快照不一致\n  左: {left_values}\n  右: {right_values}"
    )


# --------------------------------------------------------------------------- #
# 1. 值等价（build，零 DB 写入 → 无唯一约束冲突，可逐字段全量比较）
# --------------------------------------------------------------------------- #
class TestFactoryValueEquivalence:
    """同一显式入参下，工厂与手写构造的字段快照必须逐项相等。"""

    def test_department_matches_legacy_construction(self) -> None:
        legacy = Department(department_code="D001", department_name="测试部门")
        produced = DepartmentFactory.build(department_code="D001", department_name="测试部门")
        _assert_same_fields(legacy, produced)

    def test_employee_matches_legacy_construction(self) -> None:
        department = DepartmentFactory.build(department_code="D001", department_name="测试部门")
        legacy = Employee(
            employee_jobcode="U001",
            employee_name="测试用户",
            employee_department=department,
            employee_phone="13800131001",
        )
        produced = EmployeeFactory.build(
            employee_jobcode="U001",
            employee_name="测试用户",
            employee_department=department,
            employee_phone="13800131001",
        )
        _assert_same_fields(legacy, produced)

    def test_auth_user_matches_legacy_construction(self) -> None:
        # build 不经 _create，密码字段两条路径同为空串，故可全字段比较；
        # 哈希落盘的证据见 TestFactoryPersistenceEquivalence.test_auth_user_password_*
        legacy = AuthUser(auth_username="testuser", auth_phone="13800138000")
        produced = AuthUserFactory.build(auth_username="testuser", auth_phone="13800138000")
        _assert_same_fields(legacy, produced)

    def test_asset_type_matches_legacy_construction(self) -> None:
        legacy = AssetType(type_code="AT001", type_name="服务器")
        produced = AssetTypeFactory.build(type_code="AT001", type_name="服务器")
        _assert_same_fields(legacy, produced)

    def test_storage_matches_legacy_construction(self) -> None:
        legacy = Storage(
            storage_code="S001",
            storage_name="测试仓库",
            storage_address="测试地点",
            storage_location="测试地点",
            storage_capacity=100,
            sort_order=0,
        )
        produced = StorageFactory.build(
            storage_code="S001",
            storage_name="测试仓库",
            storage_address="测试地点",
            storage_location="测试地点",
            storage_capacity=100,
            sort_order=0,
        )
        _assert_same_fields(legacy, produced)

    def test_contract_matches_legacy_construction(self) -> None:
        legacy = Contract(
            contract_code="C001",
            contract_name="测试合同",
            contract_amount=10000.00,
            contract_status="purchasing",
            contract_type="service",
            contract_start_date=date(2024, 1, 1),
            contract_end_date=date(2025, 1, 1),
        )
        produced = ContractFactory.build(
            contract_code="C001",
            contract_name="测试合同",
            contract_amount=10000.00,
            contract_status="purchasing",
            contract_type="service",
            contract_start_date=date(2024, 1, 1),
            contract_end_date=date(2025, 1, 1),
        )
        _assert_same_fields(legacy, produced)

    def test_asset_matches_legacy_construction(self) -> None:
        storage = StorageFactory.build()
        asset_type = AssetTypeFactory.build(type_code="AT001", type_name="服务器")
        person = EmployeeFactory.build()
        legacy = Asset(
            asset_code="A001",
            asset_name="测试资产",
            asset_purchase_price=1000.00,
            asset_purchase_date=date(2024, 1, 1),
            asset_entry_date=date(2024, 1, 15),
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_entry_person_recordcode=person,
            asset_current_status="in_store",
        )
        produced = AssetFactory.build(
            asset_code="A001",
            asset_name="测试资产",
            asset_purchase_price=1000.00,
            asset_purchase_date=date(2024, 1, 1),
            asset_entry_date=date(2024, 1, 15),
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_entry_person_recordcode=person,
            asset_current_status="in_store",
        )
        _assert_same_fields(legacy, produced)


# --------------------------------------------------------------------------- #
# 2. 持久化等价（create → 重读 DB，字段不漂移；密码必须哈希）
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestFactoryPersistenceEquivalence:
    """工厂落盘后从 DB 重读，字段快照与内存实例一致。"""

    @pytest.mark.parametrize(
        ("factory", "kwargs"),
        [
            (DepartmentFactory, {"department_code": "D001", "department_name": "测试部门"}),
            (EmployeeFactory, {"employee_jobcode": "U001", "employee_name": "测试用户"}),
            (AssetTypeFactory, {"type_code": "AT001", "type_name": "服务器"}),
            (StorageFactory, {"storage_code": "S001", "storage_name": "测试仓库"}),
            (ContractFactory, {"contract_code": "C001", "contract_name": "测试合同"}),
            (AssetFactory, {"asset_code": "A001", "asset_name": "测试资产"}),
        ],
    )
    def test_round_trip_preserves_fields(self, factory, kwargs) -> None:  # type: ignore[no-untyped-def]
        produced = factory.create(**kwargs)
        reloaded = type(produced).objects.get(pk=produced.pk)
        _assert_same_fields(produced, reloaded)

    def test_auth_user_password_is_hashed_and_verifiable(self) -> None:
        produced = AuthUserFactory.create(auth_username="testuser", auth_phone="13800138000")
        reloaded = AuthUser.objects.get(pk=produced.pk)
        assert reloaded.password != TEST_PASSWORD, "密码必须哈希落库，禁止明文"
        assert reloaded.check_password(TEST_PASSWORD) is True

    def test_superuser_factory_flags_match_create_superuser(self) -> None:
        produced = SuperUserFactory.create()
        reloaded = AuthUser.objects.get(pk=produced.pk)
        assert reloaded.is_superuser is True
        assert reloaded.auth_is_staff is True
        assert reloaded.auth_is_active is True
        assert reloaded.check_password(TEST_PASSWORD) is True


# --------------------------------------------------------------------------- #
# 3. 零副作用（可空外键默认 None；不越权绑定 auth_user；Sequence 不撞唯一约束）
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestFactoryNoSideEffects:
    """工厂不得静默改变对象图与既有约束语义。"""

    def test_asset_factory_does_not_create_optional_relations(self) -> None:
        departments = Department.objects.count()
        storages = Storage.objects.count()
        contracts = Contract.objects.count()
        employees = Employee.objects.count()

        asset = AssetFactory.create()

        assert asset.asset_contract_recordcode is None
        assert asset.asset_storage_recordcode is None
        assert asset.asset_entry_person_recordcode is None
        assert asset.asset_manager_recordcode is None
        assert asset.asset_applicant_recordcode is None
        # 必填外键才允许自动建：AssetType +1，其余关联零增长
        assert Department.objects.count() == departments
        assert Storage.objects.count() == storages
        assert Contract.objects.count() == contracts
        assert Employee.objects.count() == employees
        # 注意：Asset→AssetType 走 to_field="recordcode"，故用 recordcode 而非 pk 过滤
        assert AssetType.objects.filter(recordcode=asset.asset_type_recordcode_id).exists()

    def test_employee_factory_leaves_auth_user_unbound(self) -> None:
        """模型禁止直写 auth_user 绑定，工厂必须保持 None（MA-23 v1.1 约束）。"""
        employee = EmployeeFactory.create()
        assert employee.auth_user_id is None

    def test_sequence_defaults_do_not_collide(self) -> None:
        first = DepartmentFactory.create()
        second = DepartmentFactory.create()
        assert first.department_code != second.department_code
        assert first.department_name != second.department_name

        employee_a = EmployeeFactory.create()
        employee_b = EmployeeFactory.create()
        assert employee_a.employee_jobcode != employee_b.employee_jobcode
        assert employee_a.employee_phone != employee_b.employee_phone
