"""
并发重复建号兜底回归测试【BF-139 / M-26】

锚定 5 处 exists→create 落库点的 IntegrityError → 业务 error_code 映射:
- contract_code 单约束(re_raise_or_map_integrity_error 单 token);
  employee 三约束 jobcode/phone/auth_user(match_integrity_error_rules 三规则,
  【M-45/BF-154】phone/auth_user 由原样重抛改为映射,原 500 → 400)
- department(code+name) / storage(code+name) / asset_type(code+name) 双约束
  (match_integrity_error_rules 多规则按序匹配)
- 双消息形锚定: PG 约束名形(duplicate key value violates unique constraint "...") +
  SQLite 表.列形(UNIQUE constraint failed: <table>.<column>)
- 非目标列的 IntegrityError 必须原样重抛, 防止误标为重复
- 真并发用例(PG-only): SQLite 无行级唯一约束竞态语义, skipif 跳过(CI 为 postgres:16)
"""

from decimal import Decimal
from threading import Thread
from typing import Any
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection

from apps.assetmanagement.models import AssetType, Contract, Storage
from apps.assetmanagement.services.asset_type_service import AssetTypeService
from apps.assetmanagement.services.contract_service import ContractService
from apps.assetmanagement.services.storage_service import StorageService
from apps.usermanagement.models import Department, Employee
from apps.usermanagement.services import DepartmentService, EmployeeService
from core.exceptions import AppValidationError, match_integrity_error_rules


requires_postgres = pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite 不支持并发唯一约束竞态语义, 跳过真并发用例(CI 为 Postgres, 不受影响)",
)


def _contract_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "contract_code": "M26-C1",
        "contract_name": "M26测试合同",
        "contract_type": "tender_procurement",
        "contract_amount": Decimal("10000.00"),
        "supplier_name": "供应商M26",
        "contract_start_date": "2026-01-01",
        "contract_end_date": "2026-12-31",
        "contract_status": "purchasing",
    }
    data.update(overrides)
    return data


def _employee_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "employee_jobcode": "M26E1",
        "employee_name": "M26员工",
        "employee_phone": "13800001111",
    }
    data.update(overrides)
    return data


def _department_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"department_code": "M26D1", "department_name": "M26部门"}
    data.update(overrides)
    return data


def _storage_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "storage_code": "M26S1",
        "storage_name": "M26仓库",
        "storage_address": "M26地址",
        "storage_capacity": 100,
    }
    data.update(overrides)
    return data


def _asset_type_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"type_code": "M26T1", "type_name": "M26类型"}
    data.update(overrides)
    return data


def _pg_message(constraint: str) -> str:
    """PostgreSQL 唯一约束冲突消息形(约束名含列名)"""
    return f'duplicate key value violates unique constraint "{constraint}"'


def _sqlite_message(model: type, column: str) -> str:
    """SQLite 唯一约束冲突消息形(表.列)"""
    return f"UNIQUE constraint failed: {model._meta.db_table}.{column}"


@pytest.mark.django_db
class TestMatchIntegrityErrorRules:
    """多规则匹配器本体: 双消息形命中 + 全未命中原样重抛"""

    def test_pg_message_first_matching_rule_wins(self) -> None:
        exc = IntegrityError(_pg_message("unique_department_code_not_deleted"))
        with pytest.raises(AppValidationError) as info:
            match_integrity_error_rules(
                exc,
                [
                    ("department_code", "DUPLICATE_DEPARTMENT_CODE", "编码已存在"),
                    ("department_name", "DUPLICATE_DEPARTMENT_NAME", "名称已存在"),
                ],
            )
        assert info.value.error_code == "DUPLICATE_DEPARTMENT_CODE"
        assert info.value.__cause__ is exc

    def test_sqlite_message_second_rule_hits(self) -> None:
        exc = IntegrityError(_sqlite_message(Department, "department_name"))
        with pytest.raises(AppValidationError) as info:
            match_integrity_error_rules(
                exc,
                [
                    ("department_code", "DUPLICATE_DEPARTMENT_CODE", "编码已存在"),
                    ("department_name", "DUPLICATE_DEPARTMENT_NAME", "名称已存在"),
                ],
            )
        assert info.value.error_code == "DUPLICATE_DEPARTMENT_NAME"

    def test_no_rule_matches_reraise_original(self) -> None:
        exc = IntegrityError(_sqlite_message(Department, "level"))
        with pytest.raises(IntegrityError) as info:
            match_integrity_error_rules(exc, [("department_code", "DUP_CODE", "编码已存在")])
        assert info.value is exc


@pytest.mark.django_db
class TestContractCreateRace:
    def test_pg_message_maps_to_duplicate_code(self) -> None:
        with patch.object(Contract.objects, "create", side_effect=IntegrityError(_pg_message("unique_contract_code"))):
            with pytest.raises(AppValidationError) as info:
                ContractService.create_contract(_contract_data())
        assert info.value.error_code == "DUPLICATE_CONTRACT_CODE"

    def test_sqlite_message_maps_to_duplicate_code(self) -> None:
        with patch.object(
            Contract.objects, "create", side_effect=IntegrityError(_sqlite_message(Contract, "contract_code"))
        ):
            with pytest.raises(AppValidationError) as info:
                ContractService.create_contract(_contract_data())
        assert info.value.error_code == "DUPLICATE_CONTRACT_CODE"

    def test_other_column_integrity_error_propagates(self) -> None:
        """非 contract_code 的完整性错误不得误标为重复"""
        other = IntegrityError(_sqlite_message(Contract, "contract_amount"))
        with patch.object(Contract.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError) as info:
                ContractService.create_contract(_contract_data())
        assert info.value is other

    def test_precheck_still_fast_fails(self) -> None:
        """预检未失效时, 重复编码仍由预检拦截"""
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as info:
            ContractService.create_contract(_contract_data(contract_name="另一个"))
        assert info.value.error_code == "DUPLICATE_CONTRACT_CODE"


@pytest.mark.django_db
class TestEmployeeCreateRace:
    def test_pg_message_maps_to_duplicate_jobcode(self) -> None:
        with patch.object(
            Employee.objects, "create", side_effect=IntegrityError(_pg_message("unique_employee_jobcode"))
        ):
            with pytest.raises(AppValidationError) as info:
                EmployeeService.create_employee(_employee_data())
        assert info.value.error_code == "DUPLICATE_EMPLOYEE_JOBCODE"

    def test_sqlite_message_maps_to_duplicate_jobcode(self) -> None:
        with patch.object(
            Employee.objects, "create", side_effect=IntegrityError(_sqlite_message(Employee, "employee_jobcode"))
        ):
            with pytest.raises(AppValidationError) as info:
                EmployeeService.create_employee(_employee_data())
        assert info.value.error_code == "DUPLICATE_EMPLOYEE_JOBCODE"

    def test_phone_and_auth_user_messages_map_to_business_codes(self) -> None:
        """【M-45/BF-154】phone/auth_user 冲突由原样重抛(500)改为业务错误码映射(400)"""
        with patch.object(
            Employee.objects, "create", side_effect=IntegrityError(_sqlite_message(Employee, "employee_phone"))
        ):
            with pytest.raises(AppValidationError) as info:
                EmployeeService.create_employee(_employee_data())
        assert info.value.error_code == "DUPLICATE_EMPLOYEE_PHONE"

        with patch.object(
            Employee.objects, "create", side_effect=IntegrityError(_sqlite_message(Employee, "auth_user"))
        ):
            with pytest.raises(AppValidationError) as info:
                EmployeeService.create_employee(_employee_data())
        assert info.value.error_code == "DUPLICATE_EMPLOYEE_AUTH_USER"

    def test_other_column_integrity_error_propagates(self) -> None:
        """非映射列(employee_name 等)完整性错误仍原样重抛, 不误标为重复"""
        other = IntegrityError(_sqlite_message(Employee, "employee_name"))
        with patch.object(Employee.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError) as info:
                EmployeeService.create_employee(_employee_data())
        assert info.value is other


@pytest.mark.django_db
class TestDepartmentCreateRace:
    def test_pg_message_code_rule_hits(self) -> None:
        with patch.object(
            Department.objects, "create", side_effect=IntegrityError(_pg_message("unique_department_code"))
        ):
            with pytest.raises(AppValidationError) as info:
                DepartmentService.create_department(_department_data())
        assert info.value.error_code == "DUPLICATE_DEPARTMENT_CODE"

    def test_sqlite_message_name_rule_hits(self) -> None:
        """code 预检未失效但 name 约束在并发窗口触发 → 第二规则命中"""
        with patch.object(
            Department.objects, "create", side_effect=IntegrityError(_sqlite_message(Department, "department_name"))
        ):
            with pytest.raises(AppValidationError) as info:
                DepartmentService.create_department(_department_data(department_name="M26重名部门"))
        assert info.value.error_code == "DUPLICATE_DEPARTMENT_NAME"

    def test_other_column_integrity_error_propagates(self) -> None:
        other = IntegrityError(_sqlite_message(Department, "path"))
        with patch.object(Department.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError) as info:
                DepartmentService.create_department(_department_data())
        assert info.value is other

    def test_precheck_still_fast_fails(self) -> None:
        DepartmentService.create_department(_department_data())
        with pytest.raises(AppValidationError) as info:
            DepartmentService.create_department(_department_data(department_name="另一个"))
        assert info.value.error_code == "DUPLICATE_DEPARTMENT_CODE"


@pytest.mark.django_db
class TestStorageCreateRace:
    def test_pg_message_code_rule_hits(self) -> None:
        with patch.object(Storage.objects, "create", side_effect=IntegrityError(_pg_message("unique_storage_code"))):
            with pytest.raises(AppValidationError) as info:
                StorageService.create_storage(_storage_data())
        assert info.value.error_code == "DUPLICATE_STORAGE_CODE"

    def test_sqlite_message_name_rule_hits(self) -> None:
        with patch.object(
            Storage.objects, "create", side_effect=IntegrityError(_sqlite_message(Storage, "storage_name"))
        ):
            with pytest.raises(AppValidationError) as info:
                StorageService.create_storage(_storage_data(storage_name="M26重名仓库"))
        assert info.value.error_code == "DUPLICATE_STORAGE_NAME"

    def test_other_column_integrity_error_propagates(self) -> None:
        other = IntegrityError(_sqlite_message(Storage, "storage_capacity"))
        with patch.object(Storage.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError) as info:
                StorageService.create_storage(_storage_data())
        assert info.value is other

    def test_precheck_still_fast_fails(self) -> None:
        StorageService.create_storage(_storage_data())
        with pytest.raises(AppValidationError) as info:
            StorageService.create_storage(_storage_data(storage_code="M26S1", storage_name="另一个"))
        assert info.value.error_code == "DUPLICATE_STORAGE_CODE"


@pytest.mark.django_db
class TestAssetTypeCreateRace:
    def test_pg_message_code_rule_hits(self) -> None:
        with patch.object(AssetType.objects, "create", side_effect=IntegrityError(_pg_message("unique_type_code"))):
            with pytest.raises(AppValidationError) as info:
                AssetTypeService.create_asset_type(_asset_type_data())
        assert info.value.error_code == "DUPLICATE_ASSET_TYPE_CODE"

    def test_sqlite_message_name_rule_hits(self) -> None:
        with patch.object(
            AssetType.objects, "create", side_effect=IntegrityError(_sqlite_message(AssetType, "type_name"))
        ):
            with pytest.raises(AppValidationError) as info:
                AssetTypeService.create_asset_type(_asset_type_data(type_name="M26重名类型"))
        assert info.value.error_code == "DUPLICATE_ASSET_TYPE_NAME"

    def test_other_column_integrity_error_propagates(self) -> None:
        other = IntegrityError(_sqlite_message(AssetType, "level"))
        with patch.object(AssetType.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError) as info:
                AssetTypeService.create_asset_type(_asset_type_data())
        assert info.value is other

    def test_precheck_still_fast_fails(self) -> None:
        AssetTypeService.create_asset_type(_asset_type_data())
        with pytest.raises(AppValidationError) as info:
            AssetTypeService.create_asset_type(_asset_type_data(type_name="另一个"))
        assert info.value.error_code == "DUPLICATE_ASSET_TYPE_CODE"


@requires_postgres
@pytest.mark.django_db(transaction=True)
class TestConcurrentCreateRealRace:
    """真并发(PG-only): 预检竞态窗口内恰一个成功, 另一个以业务错误码收场而非裸 IntegrityError"""

    def test_storage_create_duplicate_maps_not_500(self) -> None:
        results: list[Any] = []

        def _create(tag: str) -> None:
            try:
                StorageService.create_storage(_storage_data(storage_name=f"M26并发-{tag}"))
                results.append("ok")
            except AppValidationError as exc:
                results.append(exc.error_code)
            except IntegrityError as exc:
                results.append(f"RAW:{exc}")

        threads = [
            Thread(target=_create, args=("A",)),
            Thread(target=_create, args=("B",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("ok") == 1, results
        assert results.count("DUPLICATE_STORAGE_CODE") == 1, results

    def test_department_create_duplicate_maps_not_500(self) -> None:
        results: list[Any] = []

        def _create(code_suffix: str) -> None:
            try:
                DepartmentService.create_department(
                    _department_data(department_code=f"M26D-{code_suffix}", department_name="M26并发重名部门")
                )
                results.append("ok")
            except AppValidationError as exc:
                results.append(exc.error_code)
            except IntegrityError as exc:
                results.append(f"RAW:{exc}")

        # 同名不同码: 预检(仅查 code)双双放行, 竞争 department_name 约束
        threads = [
            Thread(target=_create, args=("X",)),
            Thread(target=_create, args=("Y",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("ok") == 1, results
        assert results.count("DUPLICATE_DEPARTMENT_NAME") == 1, results
