"""
用户和部门服务测试
"""
import pytest
from apps.usermanagement.services import EmployeeService, DepartmentService
from apps.usermanagement.selectors import EmployeeSelector, DepartmentSelector
from apps.usermanagement.models import Employee, Department, MAX_DEPARTMENT_LEVEL
from core.exceptions import ValidationError, BusinessLogicError


@pytest.mark.django_db
class TestEmployeeService:
    """员工服务测试"""

    def test_create_employee(self, department):
        """测试创建员工"""
        employee_data = {
            'employee_jobcode': 'U001',
            'employee_name': '新员工',
            'employee_department': department
        }

        employee = EmployeeService.create_employee(employee_data)

        assert employee.employee_jobcode == 'U001'
        assert employee.employee_name == '新员工'

    def test_create_duplicate_jobcode(self, test_employee):
        """测试重复工号"""
        with pytest.raises(ValidationError):
            EmployeeService.create_employee({
                'employee_jobcode': 'UTEST',
                'employee_name': '重复员工',
                'employee_department': test_employee.employee_department
            })

    def test_get_employee_by_jobcode(self, test_employee):
        """测试通过工号获取员工"""
        # 【AGENTS 规范 - P2-09】改用 EmployeeSelector.get_employee_by_jobcode
        employee = EmployeeSelector.get_employee_by_jobcode('UTEST')

        assert employee is not None
        assert employee.employee_jobcode == 'UTEST'


@pytest.mark.django_db
class TestDepartmentService:
    """部门服务测试"""

    def test_create_department(self):
        """测试创建部门"""
        dept_data = {
            'department_code': 'D002',
            'department_name': '新部门',
            'department_information': '信息员'
        }

        dept = DepartmentService.create_department(dept_data)

        assert dept.department_code == 'D002'
        assert dept.department_name == '新部门'
        assert dept.level == 0  # 根部门

    def test_create_department_with_parent(self, department):
        """测试创建带父部门的部门"""
        dept_data = {
            'department_code': 'D002',
            'department_name': '子部门',
            'department_information': '信息员',
            'parent_code': department.department_code
        }

        dept = DepartmentService.create_department(dept_data)

        assert dept.parent_code == department.department_code
        assert dept.level == 1  # 一级部门

    def test_create_department_level_exceeded(self, db):
        """测试创建部门层级超限"""
        # 创建 6 层部门（level 0-5）
        parent_code = None
        for i in range(MAX_DEPARTMENT_LEVEL + 1):  # 0, 1, 2, 3, 4, 5
            dept = Department.objects.create(
                department_code=f'D{i}',
                department_name=f'部门{i}',
                department_information='信息员',
                parent_code=parent_code,
                level=i
            )
            parent_code = dept.department_code

        # 尝试创建第 7 层（level 6），应该失败
        with pytest.raises(ValidationError):
            DepartmentService.create_department({
                'department_code': 'D6',
                'department_name': '超限部门',
                'department_information': '信息员',
                'parent_code': parent_code
            })

    def test_get_all_departments(self, department):
        """测试获取所有部门"""
        # 【AGENTS 规范 - P2-10】改用 DepartmentSelector.get_all_departments
        depts = DepartmentSelector.get_all_departments()

        assert len(depts) >= 1

    def test_move_department(self, department, child_department):
        """测试移动部门"""
        # 创建一个新的根部门
        new_parent = Department.objects.create(
            department_code='NEW_PARENT',
            department_name='新父部门',
            department_information='信息员',
            level=0
        )

        # 移动子部门到新父部门下
        moved = DepartmentService.move_department(
            child_department.department_code,
            new_parent.department_code
        )

        assert moved.parent_code == new_parent.department_code
        assert moved.level == 1

    def test_move_department_to_root(self, child_department):
        """测试移动部门成为根部门"""
        moved = DepartmentService.move_department(
            child_department.department_code,
            None  # 成为根部门
        )

        assert moved.parent_code is None
        assert moved.level == 0

    def test_move_department_circular_reference(self, department, child_department):
        """测试移动部门循环引用"""
        # 尝试将父部门移动到子部门下，应该失败
        with pytest.raises(BusinessLogicError):
            DepartmentService.move_department(
                department.department_code,
                child_department.department_code
            )

    def test_batch_update_sort_order(self, department, child_department):
        """测试批量更新排序"""
        items = [
            {'department_code': department.department_code, 'sort_order': 10},
            {'department_code': child_department.department_code, 'sort_order': 5}
        ]

        updated_count = DepartmentService.batch_update_sort_order(items)

        assert updated_count == 2

        # 验证排序已更新
        department.refresh_from_db()
        child_department.refresh_from_db()

        assert department.sort_order == 10
        assert child_department.sort_order == 5