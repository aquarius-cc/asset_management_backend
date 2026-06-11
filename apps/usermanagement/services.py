"""
用户管理服务层
"""
import copy

from django.db import transaction
from typing import Optional, Dict, Any, List
from core.exceptions import ValidationError, BusinessLogicError
from .models import Employee, Department, MAX_DEPARTMENT_LEVEL
from .selectors import DepartmentSelector, EmployeeSelector


class EmployeeService:
    """
    员工服务
    """

    @staticmethod
    @transaction.atomic
    def create_employee(employee_data: Dict[str, Any]) -> Employee:
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

    @staticmethod
    def batch_create_employee(
        employee_data_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量创建员工（逐条独立执行，返回详细结果）
        复用 EmployeeService.create_employee() 单条创建逻辑。
        使用 copy.deepcopy 避免原始数据被修改。
        """
        MAX_BATCH_SIZE = 100
        if len(employee_data_list) > MAX_BATCH_SIZE:
            raise ValidationError(detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条")

        success_items: List[Employee] = []
        fail_items: List[Dict[str, Any]] = []

        for idx, employee_data in enumerate(employee_data_list):
            try:
                result = EmployeeService.create_employee(
                    employee_data=copy.deepcopy(employee_data)
                )
                success_items.append(result)
            except ValidationError as e:
                fail_items.append({
                    "index": idx,
                    "row_number": employee_data.get('row_number'),
                    "input_data": employee_data,
                    "error_code": _map_employee_error_code(str(e.detail)),
                    "error_message": str(e.detail)
                })
            except Exception:
                fail_items.append({
                    "index": idx,
                    "row_number": employee_data.get('row_number'),
                    "input_data": employee_data,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(employee_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items
        }

    @staticmethod
    def batch_delete_employee(
        employee_jobcodes: List[str]
    ) -> Dict[str, Any]:
        """
        批量删除员工（硬删除，逐条独立执行）

        前置校验：
        - 员工必须存在
        - 员工不存在关联出库记录（作为申请人/保管人）
        """
        from apps.assetmanagement.models import OutAsset

        MAX_BATCH_SIZE = 100
        if len(employee_jobcodes) > MAX_BATCH_SIZE:
            raise ValidationError(detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条")

        success_ids: List[str] = []
        fail_items: List[Dict[str, Any]] = []

        for jobcode in employee_jobcodes:
            try:
                employee = EmployeeSelector.get_employee_by_jobcode(jobcode)
                if not employee:
                    fail_items.append({
                        "id": jobcode,
                        "error_code": "NOT_FOUND",
                        "error_message": f"员工 {jobcode} 不存在"
                    })
                    continue

                # 检查关联资产（作为申请人）
                if OutAsset.objects.filter(outasset_applicant_jobcode=employee, is_deleted=False).exists():
                    fail_items.append({
                        "id": jobcode,
                        "error_code": "HAS_RELATED_ASSETS",
                        "error_message": "员工存在关联出库记录（申请人），不允许删除"
                    })
                    continue

                # 检查关联资产（作为保管人）
                if OutAsset.objects.filter(outasset_manager_jobcode=employee, is_deleted=False).exists():
                    fail_items.append({
                        "id": jobcode,
                        "error_code": "HAS_RELATED_ASSETS",
                        "error_message": "员工存在关联出库记录（保管人），不允许删除"
                    })
                    continue

                employee.delete()
                success_ids.append(jobcode)

            except Exception:
                fail_items.append({
                    "id": jobcode,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(employee_jobcodes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items
        }


class DepartmentService:
    """
    部门服务

    提供部门的业务逻辑处理，包括创建、移动、排序等操作。
    """

    @staticmethod
    @transaction.atomic
    def create_department(dept_data: Dict[str, Any]) -> Department:
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
        target_parent_code: Optional[str]
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
    def batch_update_sort_order(items: List[Dict[str, Any]]) -> int:
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

    @staticmethod
    def batch_create_department(
        dept_data_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量创建部门（逐条独立执行，返回详细结果）
        复用 DepartmentService.create_department() 单条创建逻辑。
        使用 copy.deepcopy 避免原始数据被修改。
        """
        MAX_BATCH_SIZE = 100
        if len(dept_data_list) > MAX_BATCH_SIZE:
            raise ValidationError(detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条")

        success_items: List[Department] = []
        fail_items: List[Dict[str, Any]] = []

        for idx, dept_data in enumerate(dept_data_list):
            try:
                result = DepartmentService.create_department(
                    dept_data=copy.deepcopy(dept_data)
                )
                success_items.append(result)
            except ValidationError as e:
                fail_items.append({
                    "index": idx,
                    "row_number": dept_data.get('row_number'),
                    "input_data": dept_data,
                    "error_code": _map_department_error_code(str(e.detail)),
                    "error_message": str(e.detail)
                })
            except Exception:
                fail_items.append({
                    "index": idx,
                    "row_number": dept_data.get('row_number'),
                    "input_data": dept_data,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(dept_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items
        }

    @staticmethod
    def batch_delete_department(
        department_codes: List[str]
    ) -> Dict[str, Any]:
        """
        批量删除部门（硬删除，逐条独立执行）

        前置校验：
        - 部门必须存在
        - 部门下不存在员工
        - 部门下不存在子部门
        """
        MAX_BATCH_SIZE = 100
        if len(department_codes) > MAX_BATCH_SIZE:
            raise ValidationError(detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条")

        success_ids: List[str] = []
        fail_items: List[Dict[str, Any]] = []

        for dept_code in department_codes:
            try:
                department = DepartmentSelector.get_department_by_code(dept_code)
                if not department:
                    fail_items.append({
                        "id": dept_code,
                        "error_code": "NOT_FOUND",
                        "error_message": f"部门 {dept_code} 不存在"
                    })
                    continue

                # 检查下属员工
                if Employee.objects.filter(employee_department=department).exists():
                    fail_items.append({
                        "id": dept_code,
                        "error_code": "HAS_EMPLOYEES",
                        "error_message": "部门下存在员工，不允许删除"
                    })
                    continue

                # 检查子部门
                if Department.objects.filter(parent_code=dept_code).exists():
                    fail_items.append({
                        "id": dept_code,
                        "error_code": "HAS_CHILD_DEPARTMENTS",
                        "error_message": "部门下存在子部门，不允许删除"
                    })
                    continue

                department.delete()
                success_ids.append(dept_code)

            except Exception:
                fail_items.append({
                    "id": dept_code,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(department_codes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items
        }


def _map_employee_error_code(error_detail: str) -> str:
    """将员工错误详情映射为错误码"""
    msg = str(error_detail).lower()
    if "已存在" in msg and "工号" in msg:
        return "DUPLICATE_EMPLOYEE_JOBCODE"
    elif "已存在" in msg and "电话" in msg:
        return "DUPLICATE_EMPLOYEE_PHONE"
    return "VALIDATION_ERROR"


def _map_department_error_code(error_detail: str) -> str:
    """将部门错误详情映射为错误码"""
    msg = str(error_detail).lower()
    if "已存在" in msg:
        return "DUPLICATE_DEPARTMENT_CODE"
    elif "不存在" in msg and "上级" in msg:
        return "PARENT_NOT_FOUND"
    elif "层级" in msg:
        return "LEVEL_EXCEEDED"
    return "VALIDATION_ERROR"
