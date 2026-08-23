"""
用户管理服务层
"""
from typing import Any

from django.db import transaction

from core.exceptions import BusinessLogicError, ValidationError

from .models import MAX_DEPARTMENT_LEVEL, Department, Employee
from .selectors import DepartmentSelector


class EmployeeService:
    """
    员工服务
    """

    @staticmethod
    @transaction.atomic
    def create_employee(employee_data: dict[str, Any]) -> Employee:
        """
        创建员工

        Args:
            employee_data: 员工数据

        Returns:
            创建的员工实例
        """
        if Employee.objects.filter(
            employee_jobcode=employee_data['employee_jobcode']
        ).exists():
            raise ValidationError(
                detail=f"工号 {employee_data['employee_jobcode']} 已存在"
            )

        employee = Employee.objects.create(**employee_data)
        return employee

    # 【AGENTS 规范 - P2-09】get_employee_by_jobcode 已删除，
    # 与 EmployeeSelector.get_employee_by_jobcode 完全重复，调用方请改用 EmployeeSelector

    @staticmethod
    @transaction.atomic
    def change_employee_status(employee: Employee, new_status: str) -> Employee:
        """
        更改员工状态

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.change_status 使用，
        将状态变更逻辑从视图层迁移到 Service 层，确保业务逻辑内聚

        Args:
            employee: 员工实例
            new_status: 新状态值，必须是 Employee.EMPLOYEE_STATUS_CHOICES 中的有效值

        Returns:
            更新后的员工实例

        Raises:
            ValidationError: 当 new_status 不是合法状态值时
        """
        valid_statuses = dict(Employee.EMPLOYEE_STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise ValidationError(
                detail=f'无效的员工状态: {new_status}，有效值为 {list(valid_statuses.keys())}'
            )

        employee.employee_status = new_status
        employee.save(update_fields=['employee_status'])
        return employee


class DepartmentService:
    """
    部门服务

    提供部门的业务逻辑处理，包括创建、移动、排序等操作。
    """

    @staticmethod
    @transaction.atomic
    def create_department(dept_data: dict[str, Any]) -> Department:
        """
        创建部门

        Args:
            dept_data: 部门数据

        Returns:
            创建的部门实例

        Raises:
            ValidationError: 部门编码已存在或层级验证失败
        """
        if Department.objects.filter(
            department_code=dept_data['department_code']
        ).exists():
            raise ValidationError(
                detail=f"部门编码 {dept_data['department_code']} 已存在"
            )

        # 如果指定了父部门，验证并计算层级
        parent_code = dept_data.get('parent_code')
        if parent_code:
            parent = DepartmentSelector.get_department_by_code(parent_code)
            if not parent:
                raise ValidationError(
                    detail=f"上级部门 {parent_code} 不存在"
                )
            # 计算层级
            dept_data['level'] = parent.level + 1
            if dept_data['level'] > MAX_DEPARTMENT_LEVEL:
                raise ValidationError(
                    detail=f"部门层级不能超过 {MAX_DEPARTMENT_LEVEL} 层"
                )
        else:
            dept_data['level'] = 0

        department = Department.objects.create(**dept_data)
        return department

    # 【AGENTS 规范 - P2-10】get_all_departments 已删除，
    # 与 DepartmentSelector.get_all_departments 完全重复，调用方请改用 DepartmentSelector

    @staticmethod
    @transaction.atomic
    def move_department(
        department_code: str,
        target_parent_code: str | None
    ) -> Department:
        """
        移动部门到新的父部门下

        核心业务逻辑：
        1. 验证目标父部门存在性
        2. 检查循环引用（不能移动到自己的子部门下）
        3. 验证层级约束（移动后不超过 6 层）
        4. 更新当前部门及其所有子部门的层级

        Args:
            department_code: 要移动的部门编码
            target_parent_code: 目标父部门编码，None 表示成为根部门

        Returns:
            Department: 更新后的部门实例

        Raises:
            BusinessLogicError: 循环引用或层级超限
            ValidationError: 部门不存在
        """
        # 获取要移动的部门
        department = DepartmentSelector.get_department_by_code(department_code)
        if not department:
            raise ValidationError(detail=f"部门 {department_code} 不存在")

        # 如果目标父部门为 None，移动为根部门
        if target_parent_code is None:
            new_level = 0
            department.parent_code = None
            department.level = new_level
            department.save()

            # 递归更新子部门层级
            DepartmentService._update_children_level(department, new_level)

            return department

        # 验证目标父部门存在
        target_parent = DepartmentSelector.get_department_by_code(target_parent_code)
        if not target_parent:
            raise ValidationError(detail=f"目标父部门 {target_parent_code} 不存在")

        # 检查循环引用：不能移动到自己
        if target_parent_code == department_code:
            raise BusinessLogicError(detail="不能将部门移动到自己下面")

        # 检查循环引用：不能移动到自己的子部门下
        descendants = department.get_all_descendants()
        if target_parent_code in descendants:
            raise BusinessLogicError(
                detail="不能将部门移动到自己的子部门下面，这会形成循环引用"
            )

        # 计算新层级
        new_level = target_parent.level + 1

        # 计算当前部门的最大子树深度
        max_child_depth = DepartmentService._get_max_child_depth(department)
        total_depth = new_level + max_child_depth

        # 验证层级约束
        if total_depth > MAX_DEPARTMENT_LEVEL:
            raise BusinessLogicError(
                detail=f"移动后部门层级将超过 {MAX_DEPARTMENT_LEVEL} 层限制"
            )

        # 更新部门信息
        department.parent_code = target_parent_code
        department.level = new_level
        department.save()

        # 递归更新子部门层级
        DepartmentService._update_children_level(department, new_level)

        return department

    @staticmethod
    def _update_children_level(department: Department, parent_level: int) -> None:
        """
        递归更新子部门的层级

        当部门移动后，需要更新其所有子部门的层级。

        Args:
            department: 父部门实例
            parent_level: 父部门的新层级
        """
        children = department.get_children()
        for child in children:
            child.level = parent_level + 1
            child.save()
            # 递归更新子部门
            DepartmentService._update_children_level(child, child.level)

    @staticmethod
    def _get_max_child_depth(department: Department) -> int:
        """
        计算部门的最大子树深度

        Args:
            department: 部门实例

        Returns:
            int: 最大子树深度（相对于当前部门）
        """
        children = department.get_children()
        if not children.exists():
            return 0

        max_depth = 0
        for child in children:
            child_depth = DepartmentService._get_max_child_depth(child)
            max_depth = max(max_depth, child_depth + 1)

        return max_depth

    @staticmethod
    @transaction.atomic
    def batch_update_sort_order(items: list[dict[str, Any]]) -> int:
        """
        批量更新部门排序

        Args:
            items: 排序项列表，每项包含 department_code 和 sort_order

        Returns:
            int: 更新的记录数

        Raises:
            ValidationError: 部门不存在
        """
        updated_count = 0

        for item in items:
            department_code = item['department_code']
            sort_order = item['sort_order']

            # 更新排序
            updated = Department.objects.filter(
                department_code=department_code
            ).update(sort_order=sort_order)

            if updated:
                updated_count += 1

        return updated_count
