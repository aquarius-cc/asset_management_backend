"""
部门范围查询工具(RBAC 行级数据隔离)

提供共享的部门范围查询函数,所有 Selector 层的
get_queryset_for_user() 统一调用此模块。

核心函数:
- get_employee_for_user(user): 获取用户对应的 Employee(带请求级缓存)
- get_department_codes_for_user(user): 返回用户可访问的部门编码列表
- resolve_asset_department_codes(asset): 动态解析资产归属部门
"""

from typing import Any

from django.db.models import Q, QuerySet

from apps.usermanagement.models import Employee, EmployeeRole


def get_employee_for_user(user: Any) -> Employee | None:
    """
    获取用户对应的 Employee 记录(带请求级缓存)。

    关联方式:AuthUser.auth_username = Employee.employee_jobcode(隐式,无 FK)
    """
    if hasattr(user, "_rbac_employee"):
        return user._rbac_employee  # type: ignore[no-any-return]

    employee = (
        Employee.objects.select_related("employee_department").filter(employee_jobcode=user.auth_username).first()
    )
    user._rbac_employee = employee  # 缓存到 request cycle
    return employee


def get_department_codes_for_user(user: Any) -> list[str] | None:
    """
    返回用户可访问的部门编码列表。

    返回值语义:
    - None: 无限制(system_admin / auditor / is_superuser / 无 Employee 记录)
    - 空列表: 无权限(部门级角色但无部门,最严兜底,仅保留查看权限)
    - 非空列表: 限定的部门范围
    """
    # 超级管理员:无限制
    if getattr(user, "is_superuser", False):
        return None

    employee = get_employee_for_user(user)

    # 无 Employee 记录:默认无限制(最小权限兜底为 regular_user,此处放行由 View 层权限类控制)
    if not employee:
        return None

    role = employee.role

    # 全局角色(system_admin / auditor):无限制,不因部门字段缺失而收权
    if role in (EmployeeRole.SYSTEM_ADMIN, EmployeeRole.AUDITOR):
        return None

    # 部门级角色但无部门:最严兜底,无数据访问(仅保留最低查看权限)
    if not employee.employee_department:
        return []

    department = employee.employee_department

    if role == EmployeeRole.DEPT_MANAGER:
        # 本部门 + 所有下级部门
        descendant_codes = department.get_all_descendants()
        return [department.department_code, *descendant_codes]

    # asset_admin / regular_user:仅本部门
    return [department.department_code]


def get_effective_data_scope_for_user(user: Any) -> dict[str, Any]:
    """
    计算用户的有效数据范围(G1-B flavor a:直接派生自 Employee,零漂移)。

    与 get_department_codes_for_user 保持单一事实来源,供 my-permissions 端点
    与 employee_view.get_employee_permissions 统一调用。

    映射关系:
    - 无限制(superuser / system_admin / auditor / 无 Employee) → {"scope_type": "all"}
    - 部门级角色但无部门(最严兜底) → {departments, [], include_children: False}
    - dept_manager → {departments, [本部门, *下级], include_children: True}
    - 其余角色(asset_admin / regular_user) → {departments, [本部门], include_children: False}
    """
    codes = get_department_codes_for_user(user)
    if codes is None:
        return {"scope_type": "all"}

    if not codes:
        # 部门级角色无部门最严兜底:空部门范围,仅保留查看(read)权限
        return {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }

    employee = get_employee_for_user(user)
    include_children = bool(employee and employee.role == EmployeeRole.DEPT_MANAGER)

    return {
        "scope_type": "departments",
        "department_codes": codes,
        "include_children": include_children,
    }


def is_no_department_dept_scoped(user: Any) -> bool:
    """
    部门级角色但无部门(最严兜底判定)。

    返回 True 时,该用户仅保留查看权限与空数据范围:
    - 权限码: read-only(PermissionService 最严兜底)
    - 数据范围: 空部门范围
    - 写权限: 所有 RBAC 写权限类一律拒绝(core.permissions._get_user_role 降级为 None)

    全局角色(system_admin / auditor)不受部门字段缺失影响,返回 False。
    """
    employee = get_employee_for_user(user)
    if not employee or employee.employee_department:
        return False
    return employee.role not in (EmployeeRole.SYSTEM_ADMIN, EmployeeRole.AUDITOR)


def resolve_asset_department_codes(asset: Any) -> list[str] | None:
    """
    动态解析资产当前归属部门编码(无冗余字段,运行时计算)。

    回退链:
    1. asset_manager_recordcode.employee_department — 保管人/使用人部门
    2. asset_entry_person_recordcode.employee_department — 入库人部门
    3. asset_storage_recordcode.storage_manager.employee_department — 仓库管理员部门
    4. None — 仅 system_admin 和 auditor 可见
    """
    # 路径1:保管人部门
    if asset.asset_manager_recordcode:
        dept = asset.asset_manager_recordcode.employee_department
        if dept:
            return [dept.department_code]

    # 路径2:入库人部门
    if asset.asset_entry_person_recordcode:
        dept = asset.asset_entry_person_recordcode.employee_department
        if dept:
            return [dept.department_code]

    # 路径3:仓库管理员部门
    storage = asset.asset_storage_recordcode
    if storage and storage.storage_manager:
        dept = storage.storage_manager.employee_department
        if dept:
            return [dept.department_code]

    # 路径4:无法归属
    return None


def filter_queryset_by_department(
    queryset: QuerySet[Any, Any], dept_codes: list[str] | None, department_field: str = "department"
) -> QuerySet[Any, Any]:
    """
    通用行级过滤:根据部门编码列表过滤 QuerySet。

    dept_codes 为 None 时不过滤(无限制)。
    dept_codes 为空列表时返回空 QuerySet(无权限)。
    """
    if dept_codes is None:
        return queryset  # 无限制

    if not dept_codes:
        return queryset.none()  # 无权限

    # 按 department_field 路径过滤
    filter_kwargs = {f"{department_field}__department_code__in": dept_codes}
    return queryset.filter(**filter_kwargs)


def _build_department_scope_q(dept_codes: list[str], field_prefix: str) -> Q:
    """
    资产三路径部门归属过滤的唯一实现(DR-1):
    manager 保管人 → entry_person 入库人 → storage.storage_manager 仓库管理员。

    field_prefix 用于区分查询主体:
    - "asset_recordcode": 通过 asset_recordcode FK 关联 Asset 的模型(HardDiskSN/OutAsset 等)
    - "": 直接查询 Asset 自身(字段本身即归属路径)
    """

    def path(field: str) -> str:
        return f"{field_prefix}__{field}" if field_prefix else field

    return (
        Q(**{f"{path('asset_manager_recordcode')}__employee_department__department_code__in": dept_codes})
        | Q(**{f"{path('asset_entry_person_recordcode')}__employee_department__department_code__in": dept_codes})
        | Q(
            **{
                f"{path('asset_storage_recordcode')}__storage_manager__employee_department__department_code__in": dept_codes
            }
        )
    )


def build_asset_department_q(dept_codes: list[str]) -> Q:
    """
    构建资产部门归属的 Q 对象,用于通过 asset_recordcode FK 过滤关联记录。

    适用于所有通过 asset_recordcode 关联到 Asset 的模型:
    OutAsset, RecycleAsset, DamagedAsset, WasteAsset, BrokenAsset, LostAsset, FoundAsset, RepairAsset, HardDiskSN

    用法:
        qs = OutAsset.objects.for_list().filter(build_asset_department_q(dept_codes))
    """
    return _build_department_scope_q(dept_codes, "asset_recordcode")


def build_asset_owned_department_q(dept_codes: list[str]) -> Q:
    """
    构建 Asset 自身部门归属的 Q 对象,用于直接过滤 Asset 查询集。

    与 build_asset_department_q 的差异:Asset 的归属字段是自身的
    asset_manager_recordcode / asset_entry_person_recordcode / asset_storage_recordcode,
    无需经过 asset_recordcode 中间跳转。
    """
    return _build_department_scope_q(dept_codes, "")


def get_asset_linked_queryset_for_user(user: Any, queryset: QuerySet[Any, Any]) -> QuerySet[Any, Any]:
    """
    通用行级过滤:对通过 asset_recordcode 关联到 Asset 的模型 QuerySet 进行过滤。

    dept_codes 为 None 时不过滤(无限制)。
    """
    dept_codes = get_department_codes_for_user(user)
    if dept_codes is None:
        return queryset
    return queryset.filter(build_asset_department_q(dept_codes))
