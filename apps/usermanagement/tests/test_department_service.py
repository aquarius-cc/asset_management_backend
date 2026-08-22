"""
部门服务覆盖率测试
"""


import pytest

from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department
from apps.usermanagement.services import DepartmentService
from core.exceptions import AppValidationError, BusinessLogicError


ValidationError = AppValidationError


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
