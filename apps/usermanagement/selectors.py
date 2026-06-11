"""
用户管理查询层
"""
from typing import Optional, List, Dict, Any
from django.db.models import Q, QuerySet, Count
from .models import Employee, Department


class EmployeeSelector:
    """
    员工查询选择器
    """

    @staticmethod
    def get_employee_by_jobcode(jobcode: str) -> Optional[Employee]:
        """
        通过工号获取员工

        Args:
            jobcode: 工号

        Returns:
            员工实例或None
        """
        try:
            return Employee.objects.get(employee_jobcode=jobcode)
        except Employee.DoesNotExist:
            return None

    @staticmethod
    def get_employees_by_department(department_code: str) -> QuerySet:
        """
        获取部门下的所有员工

        Args:
            department_code: 部门编码

        Returns:
            员工查询集
        """
        return Employee.objects.filter(
            employee_department__department_code=department_code
        )

    @staticmethod
    def search_employees(keyword: Optional[str] = None) -> QuerySet:
        """
        搜索员工（支持文本字段模糊匹配 + 状态别名映射）

        【AGENTS 规范 - P3-29】将视图层 global_search 中的搜索逻辑
        （含状态别名映射）合并到 Selector 层，避免视图层手写 Q 条件。

        状态别名映射说明：
        - 输入 "在职"、"活动"、"激活" 等中文关键词可匹配 employee_status='active'
        - 输入 "离职"、"离开" 等可匹配 employee_status='left'
        - 输入 "退休" 等可匹配 employee_status='retirement'

        Args:
            keyword: 搜索关键词

        Returns:
            员工查询集（已 select_related employee_department，已 distinct）
        """
        queryset = Employee.objects.select_related('employee_department')

        if keyword:
            search_conditions = Q()

            # 文本字段模糊匹配
            text_fields = [
                'employee_name', 'employee_jobcode',
                'employee_phone', 'employee_description'
            ]
            for field in text_fields:
                search_conditions |= Q(**{f'{field}__icontains': keyword})

            # 关联部门名称模糊匹配
            search_conditions |= Q(employee_department__department_name__icontains=keyword)

            # 【AGENTS 规范 - P3-29】状态别名映射：将中文状态关键词映射为英文状态码
            status_mapping = {
                'active': ['在职', '活动', '激活', '活跃', '在职员工'],
                'left': ['离职', '离开', '已离职'],
                'retirement': ['退休', '已退休'],
            }
            matched_codes = {
                code for code, aliases in status_mapping.items()
                if any(alias in keyword for alias in aliases)
            }
            if matched_codes:
                search_conditions |= Q(employee_status__in=list(matched_codes))

            queryset = queryset.filter(search_conditions).distinct()

        return queryset

    # 【AGENTS 规范 - P1-10/P1-11】以下方法为视图层直接 ORM 调用重构而添加

    @staticmethod
    def get_employees_by_department_instance(department: Department) -> QuerySet:
        """
        根据部门实例获取该部门下的所有员工

        【AGENTS 规范 - P1-11】供 DepartmentViewSet.employees 使用，
        避免视图层直接调用 Employee.objects.filter()

        Args:
            department: 部门模型实例

        Returns:
            员工查询集
        """
        return Employee.objects.filter(employee_department=department)

    @staticmethod
    def get_active_employees() -> QuerySet:
        """
        获取所有在职员工

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.active_employees 使用，
        避免视图层直接调用 self.queryset.filter(employee_status='active')

        Returns:
            在职员工查询集
        """
        return Employee.objects.filter(
            employee_status='active'
        ).select_related('employee_department')

    @staticmethod
    def get_employee_statistics() -> Dict[str, Any]:
        """
        获取员工统计信息

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.statistics 使用，
        将统计查询逻辑从视图层迁移到 Selector 层，避免视图层直接 ORM 调用

        Returns:
            dict: 包含以下键：
                - total_employees: 员工总数
                - active_employees: 在职员工数
                - by_status: 按状态分组的统计 {status_code: {'name': status_name, 'count': count}}
                - by_department: 按部门分组的统计 {department_name: count}
        """
        total_employees = Employee.objects.count()
        active_employees = Employee.objects.filter(employee_status='active').count()

        # 按状态分组统计
        status_stats = {}
        for status_code, status_name in Employee.EMPLOYEE_STATUS_CHOICES:
            count = Employee.objects.filter(employee_status=status_code).count()
            status_stats[status_code] = {'name': status_name, 'count': count}

        # 按部门分组统计
        department_stats = {
            dept.department_name: Employee.objects.filter(employee_department=dept).count()
            for dept in Department.objects.all()
        }

        return {
            'total_employees': total_employees,
            'active_employees': active_employees,
            'by_status': status_stats,
            'by_department': department_stats
        }

    @staticmethod
    def batch_update_sort(sort_data_list: List[Dict[str, Any]]) -> QuerySet:
        """
        批量更新员工排序字段

        Args:
            sort_data_list: list of dict [{"employee_jobcode": "J001", "sort_order": 1}, ...]

        Returns:
            更新后的 Employee QuerySet（按 sort_order 升序）
        """
        from django.db import transaction
        from .models import Employee

        # 收集需要更新的员工对象
        employees_to_update = []
        jobcode_list = [item['employee_jobcode'] for item in sort_data_list]

        # 一次查询出所有相关员工（减少数据库交互）
        existing_employees = {
            emp.employee_jobcode: emp
            for emp in Employee.objects.filter(employee_jobcode__in=jobcode_list)
        }

        with transaction.atomic():
            for item in sort_data_list:
                jobcode = item['employee_jobcode']
                sort_order = item['sort_order']
                emp = existing_employees.get(jobcode)
                if emp:
                    emp.sort_order = sort_order
                    employees_to_update.append(emp)
                # 如果 jobcode 不存在，可以忽略或抛异常（根据业务决定）

            # 批量更新（只更新 sort_order 字段）
            Employee.objects.bulk_update(employees_to_update, ['sort_order'])

        # 返回更新后的员工列表（按 sort_order 排序）
        return Employee.objects.filter(employee_jobcode__in=jobcode_list).order_by('sort_order')

class DepartmentSelector:
    """
    部门查询选择器

    提供部门数据的查询方法，支持树形结构查询。
    """

    @staticmethod
    def get_department_by_code(code: str) -> Optional[Department]:
        """
        通过编码获取部门

        Args:
            code: 部门编码

        Returns:
            部门实例或None
        """
        try:
            return Department.objects.get(department_code=code)
        except Department.DoesNotExist:
            return None

    @staticmethod
    def get_all_departments() -> List[Department]:
        """
        获取所有部门（按排序字段排序）

        Returns:
            部门列表
        """
        return list(Department.objects.filter(is_deleted=False))

    @staticmethod
    def get_departments_ordered() -> QuerySet:
        """
        获取按排序字段排序的部门列表

        【AGENTS规范】支持前端按sort_order字段自定义显示顺序

        Returns:
            按sort_order排序的部门查询集
        """
        return Department.objects.filter(is_deleted=False).order_by('sort_order', 'department_code')

    @staticmethod
    def get_root_departments() -> QuerySet:
        """
        获取所有根部门（parent_code 为 null 的部门）

        Returns:
            根部门查询集
        """
        return Department.objects.filter(
            parent_code__isnull=True,is_deleted=False
        ).order_by('sort_order', 'department_code')

    @staticmethod
    def get_children(department_code: str) -> QuerySet:
        """
        获取指定部门的直接子部门

        Args:
            department_code: 部门编码

        Returns:
            子部门查询集
        """
        return Department.objects.filter(
            parent_code=department_code
        ).order_by('sort_order', 'department_code')

    @staticmethod
    def get_departments_by_level(level: int) -> QuerySet:
        """
        获取指定层级的所有部门

        Args:
            level: 部门层级（0=根部门）

        Returns:
            该层级的部门查询集
        """
        return Department.objects.filter(
            level=level
        ).order_by('sort_order', 'department_code')

    @staticmethod
    def build_department_tree() -> List[Dict[str, Any]]:
        """
        构建完整的部门树形结构

        从根部门开始递归构建树形结构，每个节点包含：
        - 部门基本信息
        - children: 子部门列表
        - employee_count: 当前部门员工数量

        Returns:
            list: 树形结构的部门列表
        """
        # 获取所有根部门
        root_departments = DepartmentSelector.get_root_departments()

        # 递归构建树
        tree = []
        for dept in root_departments:
            node = DepartmentSelector._build_tree_node(dept)
            tree.append(node)

        return tree

    @staticmethod
    def _build_tree_node(department: Department) -> Dict[str, Any]:
        """
        递归构建树节点

        Args:
            department: 部门实例

        Returns:
            dict: 包含子部门和员工数量的节点数据
        """
        # 获取子部门
        children = DepartmentSelector.get_children(department.department_code)

        # 构建子节点
        children_data = []
        for child in children:
            children_data.append(
                DepartmentSelector._build_tree_node(child)
            )

        # 构建当前节点
        return {
            'department_code': department.department_code,
            'department_name': department.department_name,
            'department_information': department.department_information,
            'parent_code': department.parent_code,
            'level': department.level,
            'sort_order': department.sort_order,
            'children': children_data,
            'employee_count': department.get_employee_count(),
        }

    @staticmethod
    def get_department_path(department_code: str) -> List[Department]:
        """
        获取从根部门到指定部门的路径

        用于面包屑导航。

        Args:
            department_code: 部门编码

        Returns:
            list: 部门路径列表，从根部门开始
        """
        path = []
        current = DepartmentSelector.get_department_by_code(department_code)

        while current:
            path.insert(0, current)
            if current.parent_code:
                current = DepartmentSelector.get_department_by_code(
                    current.parent_code
                )
            else:
                break

        return path

    @staticmethod
    def get_all_descendants(department_code: str) -> List[Department]:
        """
        获取指定部门的所有后代部门（递归）

        Args:
            department_code: 部门编码

        Returns:
            list: 所有后代部门列表
        """
        descendants = []
        children = DepartmentSelector.get_children(department_code)

        for child in children:
            descendants.append(child)
            descendants.extend(
                DepartmentSelector.get_all_descendants(child.department_code)
            )

        return descendants

    @staticmethod
    def count_employees_in_department(department_code: str) -> int:
        """
        统计指定部门的员工数量（仅直接关联）

        Args:
            department_code: 部门编码

        Returns:
            int: 员工数量
        """
        return Employee.objects.filter(
            employee_department__department_code=department_code
        ).count()
