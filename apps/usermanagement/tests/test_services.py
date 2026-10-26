"""
用户和部门服务测试
"""

import pytest

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department, Employee
from apps.usermanagement.selectors import DepartmentSelector, EmployeeSelector
from apps.usermanagement.services import DepartmentService, EmployeeService
from core.exceptions import AppValidationError, BusinessLogicError


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

    def test_create_duplicate_phone_maps_integrity_error(self, department):
        """【M-45/BF-154】并发手机号重复 → IntegrityError 映射 DUPLICATE_EMPLOYEE_PHONE(而非裸 500)"""
        EmployeeService.create_employee(
            {
                "employee_jobcode": "PH01",
                "employee_name": "手机甲",
                "employee_department": department,
                "employee_phone": "13900000021",
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.create_employee(
                {
                    "employee_jobcode": "PH02",
                    "employee_name": "手机乙",
                    "employee_department": department,
                    "employee_phone": "13900000021",
                }
            )
        assert exc_info.value.error_code == "DUPLICATE_EMPLOYEE_PHONE"

    def test_create_duplicate_auth_user_maps_integrity_error(self, department):
        """【M-45/BF-154】并发认证账号重复绑定 → IntegrityError 映射 DUPLICATE_EMPLOYEE_AUTH_USER(而非裸 500)"""
        auth_user = AuthUser.objects.create_user(auth_username="m45_dup_user", password="Str0ngPass!123")
        EmployeeService.create_employee(
            {
                "employee_jobcode": "AU01",
                "employee_name": "绑定甲",
                "employee_department": department,
                "employee_phone": "13900000031",
                "auth_user": auth_user,
            }
        )
        with pytest.raises(ValidationError) as exc_info:
            EmployeeService.create_employee(
                {
                    "employee_jobcode": "AU02",
                    "employee_name": "绑定乙",
                    "employee_department": department,
                    "employee_phone": "13900000032",
                    "auth_user": auth_user,
                }
            )
        assert exc_info.value.error_code == "DUPLICATE_EMPLOYEE_AUTH_USER"

    def test_get_employee_by_jobcode(self, test_employee):
        """测试通过工号获取员工"""
        employee = EmployeeSelector.get_employee_by_jobcode("UTEST")

        assert employee is not None
        assert employee.employee_jobcode == "UTEST"

    def test_get_employee_by_jobcode_nonexistent(self, db):
        """【P1-6 回归屏障】不存在的工号返回 None 而非抛异常"""
        assert EmployeeSelector.get_employee_by_jobcode("NO_SUCH_CODE") is None

    def test_get_employee_by_jobcode_none_returns_none(self, db):
        """【P1-6 回归屏障】None 工号返回 None(与原 get() 捕获 DoesNotExist 等价)"""
        assert EmployeeSelector.get_employee_by_jobcode(None) is None

    def test_get_employee_by_jobcode_with_soft_deleted_duplicate(self, db, department):
        """【P1-6 回归屏障】软删除重复工号场景返回一条而非抛 MultipleObjectsReturned→500"""
        Employee.objects.create(
            employee_jobcode="UTEST", employee_name="在职工号", employee_department=department, is_deleted=False
        )
        Employee.objects.create(
            employee_jobcode="UTEST", employee_name="软删除工号", employee_department=department, is_deleted=True
        )

        employee = EmployeeSelector.get_employee_by_jobcode("UTEST")

        assert employee is not None
        assert employee.employee_jobcode == "UTEST"

    def test_batch_update_sort_updates_and_returns_ordered(self, department):
        """【M-35】写在 Service:两员工排序对调落库,回读按 sort_order 升序"""
        e1 = Employee.objects.create(
            employee_jobcode="SRT1",
            employee_name="排序甲",
            employee_department=department,
            sort_order=5,
            employee_phone="13900000011",
        )
        e2 = Employee.objects.create(
            employee_jobcode="SRT2",
            employee_name="排序乙",
            employee_department=department,
            sort_order=6,
            employee_phone="13900000012",
        )

        result = EmployeeService.batch_update_sort(
            [{"employee_jobcode": "SRT1", "sort_order": 2}, {"employee_jobcode": "SRT2", "sort_order": 1}]
        )

        e1.refresh_from_db()
        e2.refresh_from_db()
        assert (e1.sort_order, e2.sort_order) == (2, 1)
        assert [emp.employee_jobcode for emp in result] == ["SRT2", "SRT1"]

    def test_batch_update_sort_ignores_unknown_jobcode(self, test_employee):
        """【M-35】不存在的工号静默忽略(与原实现语义一致),不整批失败"""
        result = EmployeeService.batch_update_sort(
            [{"employee_jobcode": "UTEST", "sort_order": 9}, {"employee_jobcode": "GHOST", "sort_order": 1}]
        )

        test_employee.refresh_from_db()
        assert test_employee.sort_order == 9
        assert [emp.employee_jobcode for emp in result] == ["UTEST"]

    def test_batch_sort_write_lives_in_service_not_selector(self):
        """【M-35 回归屏障】Selector 禁写:batch_update_sort 下沉 Service 后不得回潮"""
        assert not hasattr(EmployeeSelector, "batch_update_sort")
        assert hasattr(EmployeeService, "batch_update_sort")


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
        # 创建 6 层部门(level 0-5)
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

        # 尝试创建第 7 层(level 6),应该失败
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
            department_code="NEW_PARENT",
            department_name="新父部门",
            department_information="信息员",
            level=0,
            path="/NEW_PARENT",
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
        # 尝试将父部门移动到子部门下,应该失败
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
