"""
部门管理服务层,封装部门的创建、移动、排序等核心业务逻辑

类:
  - DepartmentService: 部门服务(所有写操作 @transaction.atomic)

函数/方法:
  - create_department: 创建部门(含父部门解析、层级/路径计算)
  - move_department: 移动部门(含循环引用检测、层级约束验证、子孙路径批量更新)
  - batch_update_sort_order: 批量更新部门排序
  - batch_create_department: 批量创建部门(逐条执行,返回成功/失败详情)
  - batch_delete_department: 批量删除部门(含员工/子部门前置校验)

调用链:
  本模块被 views/department_view.py 调用
  本模块依赖 selectors.DepartmentSelector、audit_adapter.DepartmentAuditAdapter
"""

import copy
from typing import Any

from django.db import transaction

from apps.usermanagement.audit_adapter import DepartmentAuditAdapter
from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department, Employee
from apps.usermanagement.selectors import DepartmentSelector
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError, BusinessLogicError


class DepartmentService:
    """
    部门服务

    提供部门的业务逻辑处理,包括创建、移动、排序等操作。

    树形关联设计(方案 D):
    - 使用 parent FK 存储父子关系
    - 使用 path 字段存储物化路径,加速子孙查询
    """

    @staticmethod
    def _generate_path(parent_path: str, department_code: str) -> str:
        """
        生成部门的物化路径

        Args:
            parent_path: 父部门的 path(根部门为空字符串)
            department_code: 当前部门编码

        Returns:
            str: 完整路径,如 /ROOT/IT/DEV
        """
        return f"{parent_path}/{department_code}"

    @staticmethod
    @transaction.atomic
    def create_department(dept_data: dict[str, Any]) -> Department:
        """
        创建部门

        Args:
            dept_data: 部门数据,支持 parent_department_code(业务编码)或 parent(recordcode)

        Returns:
            创建的部门实例

        Raises:
            ValidationError: 部门编码已存在或层级验证失败
        """
        if Department.objects.filter(department_code=dept_data["department_code"]).exists():
            raise AppValidationError(
                detail=f"部门编码 {dept_data['department_code']} 已存在", error_code="DUPLICATE_DEPARTMENT_CODE"
            )

        # 解析父部门:支持 parent_department_code(业务编码)或 parent(recordcode)
        parent = None
        parent_dept_code = dept_data.pop("parent_department_code", None)
        parent_rc = dept_data.pop("parent", None)

        if parent_dept_code:
            parent = DepartmentSelector.get_department_by_code(parent_dept_code)
            if not parent:
                raise AppValidationError(
                    detail=f"上级部门 {parent_dept_code} 不存在", error_code="PARENT_DEPARTMENT_NOT_FOUND"
                )
        elif parent_rc:
            parent = Department.objects.filter(recordcode=parent_rc).first()
            if not parent:
                raise AppValidationError(detail="上级部门不存在", error_code="PARENT_DEPARTMENT_NOT_FOUND")

        # 计算层级和路径
        if parent:
            dept_data["parent"] = parent
            dept_data["level"] = parent.level + 1
            dept_data["path"] = DepartmentService._generate_path(parent.path, dept_data["department_code"])
        else:
            dept_data["parent"] = None
            dept_data["level"] = 0
            dept_data["path"] = f"/{dept_data['department_code']}"

        if dept_data["level"] > MAX_DEPARTMENT_LEVEL:
            raise AppValidationError(
                detail=f"部门层级不能超过 {MAX_DEPARTMENT_LEVEL} 层", error_code="DEPARTMENT_LEVEL_EXCEEDED"
            )

        department = Department.objects.create(**dept_data)
        DepartmentAuditAdapter.log_create(department, dept_data.get("operator_jobcode"), dept_data.get("operator_name"))
        return department

    # 【AGENTS 规范 - P2-10】get_all_departments 已删除,
    # 与 DepartmentSelector.get_all_departments 完全重复,调用方请改用 DepartmentSelector

    @staticmethod
    @transaction.atomic
    def move_department(department_code: str, target_parent_code: str | None) -> Department:
        """
        移动部门到新的父部门下

        核心业务逻辑:
        1. 验证目标父部门存在性
        2. 检查循环引用(不能移动到自己的子部门下)
        3. 验证层级约束(移动后不超过 6 层)
        4. 更新当前部门及其所有子部门的层级和路径

        Args:
            department_code: 要移动的部门编码
            target_parent_code: 目标父部门编码,None 表示成为根部门

        Returns:
            Department: 更新后的部门实例

        Raises:
            BusinessLogicError: 循环引用或层级超限
            ValidationError: 部门不存在
        """
        # 获取要移动的部门
        department = DepartmentSelector.get_department_by_code(department_code)
        if not department:
            raise AppValidationError(detail=f"部门 {department_code} 不存在", error_code="DEPARTMENT_NOT_FOUND")

        old_path = department.path
        old_level = department.level

        # 如果目标父部门为 None,移动为根部门
        if target_parent_code is None:
            new_level = 0
            department.parent = None
            department.level = new_level
            department.path = f"/{department.department_code}"
            department.save(update_fields=["parent", "level", "path"])

            # 更新所有子孙的 path 和 level
            DepartmentService._update_children_paths_and_levels(department, old_path, old_level)

            return department

        # 验证目标父部门存在
        target_parent = DepartmentSelector.get_department_by_code(target_parent_code)
        if not target_parent:
            raise AppValidationError(
                detail=f"目标父部门 {target_parent_code} 不存在", error_code="PARENT_DEPARTMENT_NOT_FOUND"
            )

        # 检查循环引用:不能移动到自己
        if target_parent_code == department_code:
            raise BusinessLogicError(detail="不能将部门移动到自己下面", error_code="CIRCULAR_REFERENCE")

        # 检查循环引用:不能移动到自己的子部门下
        # get_all_descendants() 返回 department_code 字符串列表
        descendants_codes = department.get_all_descendants()
        if target_parent_code in descendants_codes:
            raise BusinessLogicError(
                detail="不能将部门移动到自己的子部门下面,这会形成循环引用", error_code="CIRCULAR_REFERENCE"
            )

        # 计算新层级
        new_level = target_parent.level + 1

        # 计算当前部门的最大子树深度
        max_child_depth = DepartmentService._get_max_child_depth(department)
        total_depth = new_level + max_child_depth

        # 验证层级约束
        if total_depth > MAX_DEPARTMENT_LEVEL:
            raise AppValidationError(
                detail=f"移动后部门层级将超过 {MAX_DEPARTMENT_LEVEL} 层限制", error_code="DEPARTMENT_LEVEL_EXCEEDED"
            )

        # 更新部门信息
        department.parent = target_parent
        department.level = new_level
        department.path = DepartmentService._generate_path(target_parent.path, department.department_code)
        department.save(update_fields=["parent", "level", "path"])

        # 更新所有子孙的 path 和 level
        DepartmentService._update_children_paths_and_levels(department, old_path, old_level)

        return department

    @staticmethod
    def _update_children_paths_and_levels(department: Department, old_parent_path: str, old_parent_level: int) -> None:
        """
        批量更新子部门的路径和层级

        当部门移动后,需要更新其所有子孙的 path 和 level。
        使用 path 前缀匹配一次性更新,避免递归。

        Args:
            department: 新的父部门实例
            old_parent_path: 移动前的父部门 path
            old_parent_level: 移动前的父部门 level
        """
        # 查找所有子孙(基于旧 path)
        if old_parent_path:
            descendants = Department.objects.filter(path__startswith=f"{old_parent_path}/")
        else:
            descendants = Department.objects.none()

        level_diff = department.level - old_parent_level

        for child in descendants:
            # 计算新的 path:替换旧前缀为新前缀
            new_child_path = department.path + child.path[len(old_parent_path) :]
            new_child_level = child.level + level_diff
            Department.objects.filter(pk=child.pk).update(path=new_child_path, level=new_child_level)

    @staticmethod
    def _get_max_child_depth(department: Department) -> int:
        """
        计算部门的最大子树深度(基于 path 查询)

        Args:
            department: 部门实例

        Returns:
            int: 最大子树深度(相对于当前部门)
        """
        if not department.path:
            return 0

        # 获取所有子孙,找出最大 level
        max_level = (
            Department.objects.filter(path__startswith=f"{department.path}/")
            .order_by("-level")
            .values_list("level", flat=True)
            .first()
        )

        if max_level is None:
            return 0

        return max_level - department.level

    @staticmethod
    @transaction.atomic
    def batch_update_sort_order(items: list[dict[str, Any]]) -> int:
        """
        批量更新部门排序

        Args:
            items: 排序项列表,每项包含 department_code 和 sort_order

        Returns:
            int: 更新的记录数

        Raises:
            ValidationError: 部门不存在或批量大小超限
        """
        if len(items) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量排序不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        updated_count = 0

        for item in items:
            department_code = item["department_code"]
            sort_order = item["sort_order"]

            # 更新排序
            updated = Department.objects.filter(department_code=department_code).update(sort_order=sort_order)

            if updated:
                updated_count += 1

        return updated_count

    @staticmethod
    def batch_create_department(dept_data_list: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量创建部门(逐条独立执行,返回详细结果)

        【P0-优化】错误码映射机制:
        - 单条创建方法(create_department)中的验证异常均携带 error_code 属性
        - 批量方法通过 e.error_code 直接读取,不再使用字符串匹配
        - 若单条方法未设置 error_code,则兜底使用 "VALIDATION_ERROR"

        复用 DepartmentService.create_department() 单条创建逻辑。
        使用 copy.deepcopy 避免原始数据被修改。
        """
        if len(dept_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_items: list[Department] = []
        fail_items: list[dict[str, Any]] = []

        for idx, dept_data in enumerate(dept_data_list):
            try:
                result = DepartmentService.create_department(dept_data=copy.deepcopy(dept_data))
                success_items.append(result)
            except AppValidationError as e:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": dept_data.get("row_number"),
                        "input_data": dept_data,
                        "error_code": e.error_code or "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                    }
                )
            except Exception:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": dept_data.get("row_number"),
                        "input_data": dept_data,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误,请稍后重试",
                    }
                )

        return {
            "total": len(dept_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items,
        }

    @staticmethod
    def batch_delete_department(department_codes: list[str]) -> dict[str, Any]:
        """
        批量删除部门(硬删除,逐条独立执行)

        前置校验:
        - 部门必须存在
        - 部门下不存在员工
        - 部门下不存在子部门
        """
        if len(department_codes) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_ids: list[str] = []
        fail_items: list[dict[str, Any]] = []

        for dept_code in department_codes:
            try:
                with transaction.atomic():
                    department = DepartmentSelector.get_department_by_code(dept_code)
                    if not department or department.is_deleted:
                        fail_items.append(
                            {
                                "id": dept_code,
                                "error_code": "NOT_FOUND",
                                "error_message": f"部门 {dept_code} 不存在或已删除",
                            }
                        )
                        continue

                    # 检查下属员工(SoftDeleteManager 自动排除已删除)
                    if Employee.objects.filter(employee_department=department).exists():
                        fail_items.append(
                            {
                                "id": dept_code,
                                "error_code": "DEPT_HAS_EMPLOYEES",  # 4002
                                "error_message": "部门下存在员工,不允许删除",
                            }
                        )
                        continue

                    # 检查子部门(使用 parent FK)
                    if Department.objects.filter(parent=department).exists():
                        fail_items.append(
                            {
                                "id": dept_code,
                                "error_code": "HAS_CHILD_DEPARTMENTS",
                                "error_message": "部门下存在子部门,不允许删除",
                            }
                        )
                        continue

                    department.delete()
                success_ids.append(dept_code)

            except Exception:
                fail_items.append(
                    {"id": dept_code, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误,请稍后重试"}
                )

        return {
            "total": len(department_codes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items,
        }
