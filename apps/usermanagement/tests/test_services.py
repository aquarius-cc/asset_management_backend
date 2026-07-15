"""
用户和部门服务测试
"""

import pytest

from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department
from apps.usermanagement.selectors import DepartmentSelector, EmployeeSelector
from apps.usermanagement.services import DepartmentService, EmployeeService
from core.exceptions import BusinessLogicError, AppValidationError
ValidationError = AppValidationError  # 测试中统一使用 AppValidationError


@pytest.mark.django_db
class TestEmployeeService:
    """员工服务测试"""

    def test_create_employee(self, department):
        """测试创建员工"""
        employee_data = {"employee_jobcode": "U001", "employee_name": "新员工", "employee_department": department}

        employee = EmployeeService.create_employee(employee_data)

        assert employee.employee_jobcode == "U001"
        assert employee.employee_name == "新员工"

    def test_create_duplicate_jobcode(self, test_employee):
        """测试重复工号"""
        with pytest.raises(ValidationError):
            EmployeeService.create_employee(
                {
                    "employee_jobcode": "UTEST",
                    "employee_name": "重复员工",
                    "employee_department": test_employee.employee_department,
                }
            )

    def test_get_employee_by_jobcode(self, test_employee):
        """测试通过工号获取员工"""
        employee = EmployeeSelector.get_employee_by_jobcode("UTEST")

        assert employee is not None
        assert employee.employee_jobcode == "UTEST"


@pytest.mark.django_db
class TestDepartmentService:
    """部门服务测试"""

    def test_create_department(self):
        """测试创建部门"""
        dept_data = {"department_code": "D002", "department_name": "新部门", "department_information": "信息员"}

        dept = DepartmentService.create_department(dept_data)

        assert dept.department_code == "D002"
        assert dept.department_name == "新部门"
        assert dept.level == 0  # 根部门
        assert dept.path == "/D002"

    def test_create_department_with_parent(self, department):
        """测试创建带父部门的部门"""
        dept_data = {
            "department_code": "D002",
            "department_name": "子部门",
            "department_information": "信息员",
            "parent_department_code": department.department_code,
        }

        dept = DepartmentService.create_department(dept_data)

        assert dept.parent == department
        assert dept.level == 1
        assert dept.path == f"{department.path}/D002"

    def test_create_department_level_exceeded(self, db):
        """测试创建部门层级超限"""
        # 创建 6 层部门（level 0-5）
        parent = None
        parent_path = ""
        for i in range(MAX_DEPARTMENT_LEVEL + 1):  # 0, 1, 2, 3, 4, 5
            dept = Department.objects.create(
                department_code=f"D{i}",
                department_name=f"部门{i}",
                department_information="信息员",
                parent=parent,
                level=i,
                path=f"{parent_path}/D{i}",
            )
            parent = dept
            parent_path = dept.path

        # 尝试创建第 7 层（level 6），应该失败
        with pytest.raises(ValidationError):
            DepartmentService.create_department(
                {
                    "department_code": "D6",
                    "department_name": "超限部门",
                    "department_information": "信息员",
                    "parent_department_code": parent.department_code,
                }
            )

    def test_get_all_departments(self, department):
        """测试获取所有部门"""
        depts = DepartmentSelector.get_all_departments()

        assert len(depts) >= 1

    def test_move_department(self, department, child_department):
        """测试移动部门"""
        # 创建一个新的根部门
        new_parent = Department.objects.create(
            department_code="NEW_PARENT", department_name="新父部门", department_information="信息员",
            level=0, path="/NEW_PARENT"
        )

        # 移动子部门到新父部门下
        moved = DepartmentService.move_department(child_department.department_code, new_parent.department_code)

        assert moved.parent == new_parent
        assert moved.level == 1
        assert moved.path == f"{new_parent.path}/DTEST_CHILD"

    def test_move_department_to_root(self, child_department):
        """测试移动部门成为根部门"""
        moved = DepartmentService.move_department(
            child_department.department_code,
            None,  # 成为根部门
        )

        assert moved.parent is None
        assert moved.level == 0
        assert moved.path == "/DTEST_CHILD"

    def test_move_department_circular_reference(self, department, child_department):
        """测试移动部门循环引用"""
        # 尝试将父部门移动到子部门下，应该失败
        with pytest.raises(BusinessLogicError):
            DepartmentService.move_department(department.department_code, child_department.department_code)

    def test_batch_update_sort_order(self, department, child_department):
        """测试批量更新排序"""
        items = [
            {"department_code": department.department_code, "sort_order": 10},
            {"department_code": child_department.department_code, "sort_order": 5},
        ]

        updated_count = DepartmentService.batch_update_sort_order(items)

        assert updated_count == 2

        # 验证排序已更新
        department.refresh_from_db()
        child_department.refresh_from_db()

        assert department.sort_order == 10
        assert child_department.sort_order == 5
