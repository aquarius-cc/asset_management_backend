"""
员工/部门服务覆盖率补充测试

覆盖 EmployeeService 的 auth 账号绑定/解绑/替换、状态变更、批量创建/删除,
以及 DepartmentService 的边界与批量路径。
"""

from datetime import date

import pytest

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department, Employee
from apps.usermanagement.services import DepartmentService, EmployeeService
from core.exceptions import AppValidationError, BusinessLogicError
from core.tests import TEST_PASSWORD


ValidationError = AppValidationError


@pytest.mark.django_db
class TestEmployeeAuthBinding:
    """员工认证账号绑定/解绑/替换"""

    @pytest.fixture
    def bind_employee(self, department):
        return Employee.objects.create(
            employee_jobcode="BIND001",
            employee_name="绑定员工",
            employee_department=department,
            employee_phone="13710000101",
        )

    @pytest.fixture
    def auth_user_a(self, db):
        return AuthUser.objects.create_user(
            auth_username="auth_a", password=TEST_PASSWORD, auth_phone="13710000201"
        )

    @pytest.fixture
    def auth_user_b(self, db):
        return AuthUser.objects.create_user(
            auth_username="auth_b", password=TEST_PASSWORD, auth_phone="13710000202"
        )

    def test_bind_auth_user_success(self, bind_employee, auth_user_a):
        employee = EmployeeService.bind_auth_user("BIND001", "auth_a")

        employee.refresh_from_db()
        assert employee.auth_user == auth_user_a

    def test_bind_auth_user_already_bound(self, bind_employee, auth_user_a):
        EmployeeService.bind_auth_user("BIND001", "auth_a")

        with pytest.raises(BusinessLogicError):
            EmployeeService.bind_auth_user("BIND001", "auth_a")

    def test_bind_auth_user_not_found(self, bind_employee):
        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.bind_auth_user("BIND001", "no_such_user")
        assert exc_info.value.error_code == "AUTH_USER_NOT_FOUND"

    def test_bind_auth_user_already_bound_elsewhere(self, department, bind_employee, auth_user_a):
        other = Employee.objects.create(
            employee_jobcode="BIND002",
            employee_name="另一员工",
            employee_department=department,
            employee_phone="13710000301",
            auth_user=auth_user_a,
        )

        with pytest.raises(BusinessLogicError) as exc_info:
            EmployeeService.bind_auth_user("BIND001", "auth_a")
        assert exc_info.value.error_code == "AUTH_USER_ALREADY_BOUND"
        assert other.auth_user == auth_user_a

    def test_unbind_auth_user_success(self, bind_employee, auth_user_a):
        EmployeeService.bind_auth_user("BIND001", "auth_a")

        employee = EmployeeService.unbind_auth_user("BIND001")

        employee.refresh_from_db()
        assert employee.auth_user is None

    def test_unbind_auth_user_not_bound(self, bind_employee):
        with pytest.raises(BusinessLogicError) as exc_info:
            EmployeeService.unbind_auth_user("BIND001")
        assert exc_info.value.error_code == "EMPLOYEE_NOT_BOUND"

    def test_replace_auth_user_success(self, bind_employee, auth_user_a, auth_user_b):
        EmployeeService.bind_auth_user("BIND001", "auth_a")

        employee = EmployeeService.replace_auth_user("BIND001", "auth_b")

        employee.refresh_from_db()
        assert employee.auth_user == auth_user_b

    def test_replace_auth_user_same(self, bind_employee, auth_user_a):
        EmployeeService.bind_auth_user("BIND001", "auth_a")

        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.replace_auth_user("BIND001", "auth_a")
        assert exc_info.value.error_code == "AUTH_USER_SAME"

    def test_replace_auth_user_not_found(self, bind_employee, auth_user_a):
        EmployeeService.bind_auth_user("BIND001", "auth_a")

        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.replace_auth_user("BIND001", "no_such_user")
        assert exc_info.value.error_code == "AUTH_USER_NOT_FOUND"

    def test_replace_auth_user_already_bound_elsewhere(self, department, bind_employee, auth_user_a, auth_user_b):
        EmployeeService.bind_auth_user("BIND001", "auth_a")
        Employee.objects.create(
            employee_jobcode="BIND003",
            employee_name="第三人",
            employee_department=department,
            employee_phone="13710000401",
            auth_user=auth_user_b,
        )

        with pytest.raises(BusinessLogicError) as exc_info:
            EmployeeService.replace_auth_user("BIND001", "auth_b")
        assert exc_info.value.error_code == "AUTH_USER_ALREADY_BOUND"


@pytest.mark.django_db
class TestEmployeeStatusAndBatch:
    """员工状态变更与批量操作"""

    def test_change_employee_status_success(self, test_employee):
        employee = EmployeeService.change_employee_status(test_employee, "left")

        assert employee.employee_status == "left"

    def test_change_employee_status_invalid(self, test_employee):
        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.change_employee_status(test_employee, "invalid_status")
        assert exc_info.value.error_code == "INVALID_EMPLOYEE_STATUS"

    def test_batch_create_employee_success(self, department):
        result = EmployeeService.batch_create_employee(
            [
                {
                    "employee_jobcode": "BC001",
                    "employee_name": "批量一",
                    "employee_department": department,
                    "employee_phone": "13710001001",
                },
                {
                    "employee_jobcode": "BC002",
                    "employee_name": "批量二",
                    "employee_department": department,
                    "employee_phone": "13710001002",
                },
            ]
        )

        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["fail_count"] == 0

    def test_batch_create_employee_exceed_size(self, department):
        items = [
            {"employee_jobcode": f"BC{i:03d}", "employee_name": f"员工{i}", "employee_phone": f"1371000{i:04d}"}
            for i in range(101)
        ]

        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.batch_create_employee(items)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_create_employee_mixed(self, department):
        result = EmployeeService.batch_create_employee(
            [
                {
                    "employee_jobcode": "BC011",
                    "employee_name": "有效",
                    "employee_department": department,
                    "employee_phone": "13710001101",
                },
                {
                    "employee_jobcode": "BC011",
                    "employee_name": "重复",
                    "employee_department": department,
                    "employee_phone": "13710001102",
                },
            ]
        )

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DUPLICATE_EMPLOYEE_JOBCODE"

    def test_batch_create_employee_internal_error(self, department):
        result = EmployeeService.batch_create_employee(
            [
                {
                    "employee_jobcode": "BC021",
                    "employee_name": "异常",
                    "employee_department": department,
                    "employee_phone": "13710001201",
                    "invalid_field": "boom",
                }
            ]
        )

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"

    def test_batch_delete_employee_success(self, department):
        Employee.objects.create(
            employee_jobcode="BD001",
            employee_name="待删员工",
            employee_department=department,
            employee_phone="13710001301",
        )

        result = EmployeeService.batch_delete_employee(["BD001"])

        assert result["success_count"] == 1
        employee = Employee.all_objects.get(employee_jobcode="BD001")
        assert employee.is_deleted is True

    def test_batch_delete_employee_exceed_size(self):
        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.batch_delete_employee([f"BD{i:03d}" for i in range(101)])
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_employee_not_found(self):
        result = EmployeeService.batch_delete_employee(["NO_SUCH_EMP"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_delete_employee_has_related_assets(self, department):
        employee = Employee.objects.create(
            employee_jobcode="BD011",
            employee_name="有资产员工",
            employee_department=department,
            employee_phone="13710001401",
        )
        storage = Storage.objects.create(
            storage_code="BD-S001",
            storage_name="批量删除仓库",
            storage_address="测试地址",
            storage_location="测试位置",
            storage_capacity=100,
        )
        asset_type = AssetType.objects.create(type_code="BD-AT01", type_name="测试类型")
        Asset.objects.create(
            asset_code="BD-A001",
            asset_name="关联资产",
            asset_purchase_price=1000,
            asset_purchase_date=date(2024, 1, 1),
            asset_entry_date=date(2024, 1, 15),
            asset_type_recordcode=asset_type,
            asset_storage_recordcode=storage,
            asset_applicant_recordcode=employee,
        )

        result = EmployeeService.batch_delete_employee(["BD011"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "HAS_RELATED_ASSETS"

    def test_batch_delete_employee_internal_error(self, department, monkeypatch):
        Employee.objects.create(
            employee_jobcode="BD021",
            employee_name="异常删除",
            employee_department=department,
            employee_phone="13710001501",
        )
        original_delete = Employee.delete

        def raising_delete(self, *args, **kwargs):
            if self.employee_jobcode == "BD021":
                raise RuntimeError("boom")
            return original_delete(self, *args, **kwargs)

        monkeypatch.setattr(Employee, "delete", raising_delete)

        result = EmployeeService.batch_delete_employee(["BD021"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"


@pytest.mark.django_db
class TestDepartmentServiceExtra:
    """部门服务边界路径"""

    def test_create_department_duplicate_code(self, department):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": department.department_code,
                    "department_name": "重复部门",
                }
            )
        assert exc_info.value.error_code == "DUPLICATE_DEPARTMENT_CODE"

    def test_create_department_parent_code_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": "D101",
                    "department_name": "子部门",
                    "parent_department_code": "NO_SUCH_PARENT",
                }
            )
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_create_department_parent_rc_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": "D102",
                    "department_name": "子部门",
                    "parent": "NO_SUCH_RECORDCODE",
                }
            )
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_move_department_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department("NO_SUCH_DEPT", None)
        assert exc_info.value.error_code == "DEPARTMENT_NOT_FOUND"

    def test_move_department_target_not_found(self, department):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department(department.department_code, "NO_SUCH_TARGET")
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_move_department_to_self(self, department):
        with pytest.raises(BusinessLogicError) as exc_info:
            DepartmentService.move_department(department.department_code, department.department_code)
        assert exc_info.value.error_code == "CIRCULAR_REFERENCE"

    def test_move_department_level_exceeded(self, db):
        root = Department.objects.create(
            department_code="LROOT", department_name="根", department_information="", level=0, path="/LROOT"
        )
        moving = Department.objects.create(
            department_code="LMOVE",
            department_name="待移",
            department_information="",
            level=0,
            path="/LMOVE",
        )
        parent = moving
        parent_path = moving.path
        for i in range(MAX_DEPARTMENT_LEVEL + 1):
            child = Department.objects.create(
                department_code=f"LC{i}",
                department_name=f"子{i}",
                department_information="",
                parent=parent,
                level=i + 1,
                path=f"{parent_path}/LC{i}",
            )
            parent = child
            parent_path = child.path

        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department("LMOVE", root.department_code)
        assert exc_info.value.error_code == "DEPARTMENT_LEVEL_EXCEEDED"

    def test_move_department_empty_path_children(self, db):
        target = Department.objects.create(
            department_code="EMPTY_TARGET",
            department_name="目标部门",
            department_information="",
            level=0,
            path="/EMPTY_TARGET",
        )
        empty_path_dept = Department.objects.create(
            department_code="EMPTY1",
            department_name="空路径",
            department_information="",
            parent=target,
            level=1,
            path="",
        )
        assert empty_path_dept.pk is not None

        moved = DepartmentService.move_department("EMPTY1", "EMPTY_TARGET")

        assert moved.parent == target
        assert moved.level == 1
        assert moved.path == "/EMPTY_TARGET/EMPTY1"

    def test_move_department_updates_children(self, db):
        root_a = Department.objects.create(
            department_code="RA", department_name="根A", department_information="", level=0, path="/RA"
        )
        dept_b = Department.objects.create(
            department_code="RB",
            department_name="部门B",
            department_information="",
            parent=root_a,
            level=1,
            path="/RA/RB",
        )
        Department.objects.create(
            department_code="RC",
            department_name="子C",
            department_information="",
            parent=dept_b,
            level=2,
            path="/RA/RB/RC",
        )
        root_x = Department.objects.create(
            department_code="RX", department_name="根X", department_information="", level=0, path="/RX"
        )

        moved = DepartmentService.move_department("RB", root_x.department_code)

        assert moved.path == "/RX/RB"
        child = Department.objects.get(department_code="RC")
        assert child.path == "/RX/RB/RC"
        assert child.level == 2

    def test_batch_update_sort_order_exceed_size(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_update_sort_order(
                [{"department_code": f"D{i}", "sort_order": i} for i in range(101)]
            )
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_create_department_success(self):
        result = DepartmentService.batch_create_department(
            [
                {"department_code": "BC201", "department_name": "批量一"},
                {"department_code": "BC202", "department_name": "批量二"},
            ]
        )

        assert result["success_count"] == 2
        assert result["fail_count"] == 0

    def test_batch_create_department_exceed_size(self):
        items = [
            {"department_code": f"BC{i:03d}", "department_name": f"部门{i}"} for i in range(101)
        ]

        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_create_department(items)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_create_department_mixed(self):
        result = DepartmentService.batch_create_department(
            [
                {"department_code": "BC211", "department_name": "有效"},
                {"department_code": "BC211", "department_name": "重复"},
            ]
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DUPLICATE_DEPARTMENT_CODE"

    def test_batch_create_department_internal_error(self):
        result = DepartmentService.batch_create_department(
            [{"department_code": "BC221", "department_name": "异常", "invalid_field": "boom"}]
        )

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"

    def test_batch_delete_department_success(self):
        dept = Department.objects.create(department_code="BD301", department_name="待删部门")
        assert dept.pk is not None

        result = DepartmentService.batch_delete_department(["BD301"])

        assert result["success_count"] == 1
        assert Department.objects.filter(department_code="BD301").count() == 0

    def test_batch_delete_department_exceed_size(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_delete_department([f"D{i}" for i in range(101)])
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_department_not_found(self):
        result = DepartmentService.batch_delete_department(["NO_SUCH_DEPT"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_delete_department_has_employees(self, department, test_employee):
        result = DepartmentService.batch_delete_department([department.department_code])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DEPT_HAS_EMPLOYEES"

    def test_batch_delete_department_has_children(self, department, child_department):
        result = DepartmentService.batch_delete_department([department.department_code])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "HAS_CHILD_DEPARTMENTS"

    def test_batch_delete_department_internal_error(self, monkeypatch):
        dept = Department.objects.create(department_code="BD311", department_name="异常删除")
        assert dept.pk is not None
        original_delete = Department.delete

        def raising_delete(self, *args, **kwargs):
            if self.department_code == "BD311":
                raise RuntimeError("boom")
            return original_delete(self, *args, **kwargs)

        monkeypatch.setattr(Department, "delete", raising_delete)

        result = DepartmentService.batch_delete_department(["BD311"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"
