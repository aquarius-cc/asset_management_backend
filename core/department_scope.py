"""
部门范围查询工具（RBAC 行级数据隔离）

提供共享的部门范围查询函数，所有 Selector 层的
get_queryset_for_user() 统一调用此模块。

核心函数：
- get_employee_for_user(user): 获取用户对应的 Employee（带请求级缓存）
- get_department_codes_for_user(user): 返回用户可访问的部门编码列表
- resolve_asset_department_codes(asset): 动态解析资产归属部门
"""

from functools import lru_cache

from django.db.models import Q

from apps.usermanagement.models import Employee, EmployeeRole


def get_employee_for_user(user) -> Employee | None:
    """
    获取用户对应的 Employee 记录（带请求级缓存）。

    关联方式：AuthUser.auth_username = Employee.employee_jobcode（隐式，无 FK）
    """
    if hasattr(user, "_rbac_employee"):
        return user._rbac_employee

    employee = (
        Employee.objects.select_related("employee_department")
        .filter(employee_jobcode=user.auth_username)
        .first()
    )
    user._rbac_employee = employee  # 缓存到 request cycle
    return employee


def get_department_codes_for_user(user) -> list[str] | None:
    """
    返回用户可访问的部门编码列表。

    返回值语义：
    - None: 无限制（system_admin / auditor / 无 Employee / is_superuser）
    - 空列表: 无权限（不应出现）
    - 非空列表: 限定的部门范围
    """
    # 超级管理员：无限制
    if getattr(user, "is_superuser", False):
        return None

    employee = get_employee_for_user(user)

    # 无 Employee 记录或无部门：默认无限制（最小权限兜底为 regular_user，但此处放行由 View 层权限类控制）
    if not employee or not employee.employee_department:
        return None

    role = employee.role

    # 系统管理员 / 审计员：无限制
    if role in (EmployeeRole.SYSTEM_ADMIN, EmployeeRole.AUDITOR):
        return None

    department = employee.employee_department

    if role == EmployeeRole.DEPT_MANAGER:
        # 本部门 + 所有下级部门
        descendant_codes = department.get_all_descendants()
        return [department.department_code] + descendant_codes

    # asset_admin / regular_user：仅本部门
    return [department.department_code]


def resolve_asset_department_codes(asset) -> list[str] | None:
    """
    动态解析资产当前归属部门编码（无冗余字段，运行时计算）。

    回退链：
    1. asset_manager_recordcode.employee_department — 保管人/使用人部门
    2. asset_entry_person_recordcode.employee_department — 入库人部门
    3. asset_storage_recordcode.storage_manager.employee_department — 仓库管理员部门
    4. None — 仅 system_admin 和 auditor 可见
    """
    # 路径1：保管人部门
    if asset.asset_manager_recordcode:
        dept = asset.asset_manager_recordcode.employee_department
        if dept:
            return [dept.department_code]

    # 路径2：入库人部门
    if asset.asset_entry_person_recordcode:
        dept = asset.asset_entry_person_recordcode.employee_department
        if dept:
            return [dept.department_code]

    # 路径3：仓库管理员部门
    storage = asset.asset_storage_recordcode
    if storage and storage.storage_manager:
        dept = storage.storage_manager.employee_department
        if dept:
            return [dept.department_code]

    # 路径4：无法归属
    return None


def filter_queryset_by_department(queryset, dept_codes: list[str] | None, department_field: str = "department"):
    """
    通用行级过滤：根据部门编码列表过滤 QuerySet。

    dept_codes 为 None 时不过滤（无限制）。
    dept_codes 为空列表时返回空 QuerySet（无权限）。
    """
    if dept_codes is None:
        return queryset  # 无限制

    if not dept_codes:
        return queryset.none()  # 无权限

    # 按 department_field 路径过滤
    filter_kwargs = {f"{department_field}__department_code__in": dept_codes}
    return queryset.filter(**filter_kwargs)


def build_asset_department_q(dept_codes: list[str]) -> Q:
    """
    构建资产部门归属的 Q 对象，用于通过 asset_recordcode FK 过滤关联记录。

    适用于所有通过 asset_recordcode 关联到 Asset 的模型：
    OutAsset, RecycleAsset, DamagedAsset, WasteAsset, BrokenAsset, LostAsset, FoundAsset, RepairAsset, HardDiskSN

    用法:
        qs = OutAsset.objects.for_list().filter(build_asset_department_q(dept_codes))
    """
    return (
        Q(asset_recordcode__asset_manager_recordcode__employee_department__department_code__in=dept_codes)
        | Q(asset_recordcode__asset_entry_person_recordcode__employee_department__department_code__in=dept_codes)
        | Q(asset_recordcode__asset_storage_recordcode__storage_manager__employee_department__department_code__in=dept_codes)
    )


def get_asset_linked_queryset_for_user(user, queryset):
    """
    通用行级过滤：对通过 asset_recordcode 关联到 Asset 的模型 QuerySet 进行过滤。

    dept_codes 为 None 时不过滤（无限制）。
    """
    dept_codes = get_department_codes_for_user(user)
    if dept_codes is None:
        return queryset
    return queryset.filter(build_asset_department_q(dept_codes))
