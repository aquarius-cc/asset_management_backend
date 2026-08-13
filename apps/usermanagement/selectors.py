"""
用户管理查询层
"""

from typing import Any, cast

from django.db.models import Count, Q, QuerySet

from apps.usermanagement.models import Department, Employee


class EmployeeSelector:
    """
    员工查询选择器
    """

    @staticmethod
    def get_employee_by_jobcode(jobcode: str) -> Employee | None:
        """
        通过工号获取员工

        【P1-6 修复】使用 filter().first() 替代 get():
        - 消除软删除重复工号场景下 get() 抛 MultipleObjectsReturned → 500 的风险
        - 统一预加载 employee_department,供权限等场景直接访问
        - jobcode 为 None 时 filter 不匹配,返回 None(与原 get() 捕获 DoesNotExist 等价)

        Args:
            jobcode: 工号

        Returns:
            员工实例或None
        """
        employee = (
            Employee.objects.filter(employee_jobcode=jobcode)
            .select_related("employee_department")
            .first()
        )
        return cast("Employee | None", employee)

    @staticmethod
    def get_employees_by_department(department_code: str) -> QuerySet:
        """
        获取部门下的所有员工

        Args:
            department_code: 部门编码

        Returns:
            员工查询集
        """
        # 【P0-26 修复】跨表 JOIN 过滤关联表 is_deleted=False,防止返回已删除部门下的员工
        return Employee.objects.filter(
            employee_department__department_code=department_code, employee_department__is_deleted=False
        )

    @staticmethod
    def search_employees(keyword: str | None = None) -> QuerySet:
        """
        搜索员工(支持文本字段模糊匹配 + 状态别名映射)

        【AGENTS 规范 - P3-29】将视图层 global_search 中的搜索逻辑
        (含状态别名映射)合并到 Selector 层,避免视图层手写 Q 条件。

        状态别名映射说明:
        - 输入 "在职"、"活动"、"激活" 等中文关键词可匹配 employee_status='active'
        - 输入 "离职"、"离开" 等可匹配 employee_status='left'
        - 输入 "退休" 等可匹配 employee_status='retirement'

        Args:
            keyword: 搜索关键词

        Returns:
            员工查询集(已 select_related employee_department,已 distinct)
        """
        queryset = Employee.objects.select_related("employee_department")

        if keyword:
            search_conditions = Q()

            # 文本字段模糊匹配
            text_fields = ["employee_name", "employee_jobcode", "employee_phone", "employee_description"]
            for field in text_fields:
                search_conditions |= Q(**{f"{field}__icontains": keyword})

            # 关联部门名称模糊匹配
            search_conditions |= Q(employee_department__department_name__icontains=keyword)

            # 【AGENTS 规范 - P3-29】状态别名映射:将中文状态关键词映射为英文状态码
            status_mapping = {
                "active": ["在职", "活动", "激活", "活跃", "在职员工"],
                "left": ["离职", "离开", "已离职"],
                "retirement": ["退休", "已退休"],
            }
            matched_codes = {
                code for code, aliases in status_mapping.items() if any(alias in keyword for alias in aliases)
            }
            if matched_codes:
                search_conditions |= Q(employee_status__in=list(matched_codes))

            queryset = queryset.filter(search_conditions).distinct()

        return queryset

    # 【AGENTS 规范 - P1-10/P1-11】以下方法为视图层直接 ORM 调用重构而添加

    @staticmethod
    def get_queryset_with_bind_status() -> QuerySet:
        """
        获取带认证账号绑定状态的员工查询集

        【EmployeeViewSet】queryset 使用,预加载 auth_user 与部门,
        供列表接口展示绑定状态,避免 N+1 查询。

        Returns:
            员工查询集(已 select_related employee_department、auth_user)
        """
        return Employee.objects.select_related("employee_department", "auth_user")

    @staticmethod
    def get_employees_by_department_instance(department: Department) -> QuerySet:
        """
        根据部门实例获取该部门下的所有员工

        【AGENTS 规范 - P1-11】供 DepartmentViewSet.employees 使用,
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

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.active_employees 使用,
        避免视图层直接调用 self.queryset.filter(employee_status='active')

        Returns:
            在职员工查询集
        """
        return Employee.objects.filter(employee_status="active").select_related("employee_department")

    @staticmethod
    def get_employee_statistics() -> dict[str, Any]:
        """
        获取员工统计信息

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.statistics 使用,
        将统计查询逻辑从视图层迁移到 Selector 层,避免视图层直接 ORM 调用

        【性能优化】使用 aggregate + annotate 替代循环逐条查询,避免 N+1 问题

        Returns:
            dict: 包含以下键:
                - total_employees: 员工总数
                - active_employees: 在职员工数
                - by_status: 按状态分组的统计 {status_code: {'name': status_name, 'count': count}}
                - by_department: 按部门分组的统计 {department_name: count}
        """
        from django.db.models import Q

        # 使用 aggregate 一次查询获取总数和在职数
        stats = Employee.objects.aggregate(total=Count("id"), active=Count("id", filter=Q(employee_status="active")))

        # 使用 annotate 按状态分组,一次查询完成
        status_stats = {}
        status_counts = (
            Employee.objects.values("employee_status").annotate(count=Count("id")).order_by("employee_status")
        )
        status_name_map = dict(Employee.EMPLOYEE_STATUS_CHOICES)
        for item in status_counts:
            code = item["employee_status"]
            status_stats[code] = {"name": status_name_map.get(code, code), "count": item["count"]}

        # 使用 annotate 按部门分组,一次查询完成
        department_stats = {}
        dept_counts = (
            Employee.objects.filter(employee_department__isnull=False)
            .values("employee_department__department_name")
            .annotate(count=Count("id"))
            .order_by("employee_department__department_name")
        )
        for item in dept_counts:
            dept_name = item["employee_department__department_name"]
            department_stats[dept_name] = item["count"]

        return {
            "total_employees": stats["total"],
            "active_employees": stats["active"],
            "by_status": status_stats,
            "by_department": department_stats,
        }

    @staticmethod
    def batch_update_sort(sort_data_list: list[dict[str, Any]]) -> QuerySet:
        """
        批量更新员工排序字段

        Args:
            sort_data_list: list of dict [{"employee_jobcode": "J001", "sort_order": 1}, ...]

        Returns:
            更新后的 Employee QuerySet(按 sort_order 升序)
        """
        from django.db import transaction

        from apps.usermanagement.models import Employee

        # 收集需要更新的员工对象
        employees_to_update = []
        jobcode_list = [item["employee_jobcode"] for item in sort_data_list]

        # 一次查询出所有相关员工(减少数据库交互)
        existing_employees = {
            emp.employee_jobcode: emp for emp in Employee.objects.filter(employee_jobcode__in=jobcode_list)
        }

        with transaction.atomic():
            for item in sort_data_list:
                jobcode = item["employee_jobcode"]
                sort_order = item["sort_order"]
                emp = existing_employees.get(jobcode)
                if emp:
                    emp.sort_order = sort_order
                    employees_to_update.append(emp)
                # 如果 jobcode 不存在,可以忽略或抛异常(根据业务决定)

            # 批量更新(只更新 sort_order 字段)
            Employee.objects.bulk_update(employees_to_update, ["sort_order"])

        # 返回更新后的员工列表(按 sort_order 排序)
        return Employee.objects.filter(employee_jobcode__in=jobcode_list).order_by("sort_order")


class DepartmentSelector:
    """
    部门查询选择器

    提供部门数据的查询方法,支持树形结构查询。

    树形关联设计(方案 D):
    - 使用 parent FK 查询父子关系
    - 使用 path 字段加速子孙查询和面包屑导航
    """

    @staticmethod
    def get_department_by_code(code: str) -> Department | None:
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
    def get_all_departments() -> list[Department]:
        """
        获取所有部门(按排序字段排序)

        Returns:
            部门列表
        """
        return list(Department.objects.all())

    @staticmethod
    def get_departments_ordered() -> QuerySet:
        """
        获取按排序字段排序的部门列表

        【AGENTS规范】支持前端按sort_order字段自定义显示顺序

        Returns:
            按sort_order排序的部门查询集
        """
        return Department.objects.order_by("sort_order", "department_code")

    @staticmethod
    def get_root_departments() -> QuerySet:
        """
        获取所有根部门(parent FK 为 null 的部门)

        Returns:
            根部门查询集
        """
        return Department.objects.filter(parent__isnull=True).order_by("sort_order", "department_code")

    @staticmethod
    def get_children(department_code: str) -> QuerySet:
        """
        获取指定部门的直接子部门

        Args:
            department_code: 部门编码

        Returns:
            子部门查询集
        """
        parent = DepartmentSelector.get_department_by_code(department_code)
        if not parent:
            return Department.objects.none()
        return Department.objects.filter(parent=parent).order_by("sort_order", "department_code")

    @staticmethod
    def get_departments_by_level(level: int) -> QuerySet:
        """
        获取指定层级的所有部门

        Args:
            level: 部门层级(0=根部门)

        Returns:
            该层级的部门查询集
        """
        return Department.objects.filter(level=level).order_by("sort_order", "department_code")

    @staticmethod
    def build_department_tree() -> list[dict[str, Any]]:
        """
        构建完整的部门树形结构

        从根部门开始递归构建树形结构,每个节点包含:
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
    def _build_tree_node(department: Department) -> dict[str, Any]:
        """
        递归构建树节点

        Args:
            department: 部门实例

        Returns:
            dict: 包含子部门和员工数量的节点数据
        """
        # 获取子部门(使用 parent FK)
        children = Department.objects.filter(parent=department).order_by("sort_order", "department_code")

        # 构建子节点
        children_data = []
        for child in children:
            children_data.append(DepartmentSelector._build_tree_node(child))

        # 构建当前节点
        return {
            "recordcode": department.recordcode,
            "department_code": department.department_code,
            "department_name": department.department_name,
            "department_information": department.department_information,
            "parent": department.parent_id,
            "parent_department_code": department.parent.department_code if department.parent else None,
            "path": department.path,
            "level": department.level,
            "sort_order": department.sort_order,
            "children": children_data,
            "employee_count": department.get_employee_count(),
        }

    @staticmethod
    def get_department_path(department_code: str) -> list[Department]:
        """
        获取从根部门到指定部门的路径(用于面包屑导航)

        【性能优化】使用 path 字段一次性查询所有祖先,避免递归 N+1 问题。

        Args:
            department_code: 部门编码

        Returns:
            list: 部门路径列表,从根部门开始
        """
        dept = DepartmentSelector.get_department_by_code(department_code)
        if not dept or not dept.path:
            return []

        # 从 path 中提取所有祖先的 department_code
        # path 格式: /ROOT/IT/DEV,拆分后取非空部分
        codes = [c for c in dept.path.split("/") if c]

        # 一次查询获取所有路径上的部门
        departments = {
            d.department_code: d for d in Department.objects.filter(department_code__in=codes, is_deleted=False)
        }

        # 按 path 顺序组装结果
        path = []
        for code in codes:
            if code in departments:
                path.append(departments[code])

        return path

    @staticmethod
    def get_all_descendants(department_code: str) -> list[Department]:
        """
        获取指定部门的所有后代部门

        【性能优化】使用 path 字段一次性查询,替代递归。

        Args:
            department_code: 部门编码

        Returns:
            list: 所有后代部门列表
        """
        dept = DepartmentSelector.get_department_by_code(department_code)
        if not dept or not dept.path:
            return []

        return list(
            Department.objects.filter(path__startswith=f"{dept.path}/").order_by(
                "level", "sort_order", "department_code"
            )
        )

    @staticmethod
    def count_employees_in_department(department_code: str) -> int:
        """
        统计指定部门的员工数量(仅直接关联)

        Args:
            department_code: 部门编码

        Returns:
            int: 员工数量
        """
        return Employee.objects.filter(
            employee_department__department_code=department_code, employee_department__is_deleted=False
        ).count()
