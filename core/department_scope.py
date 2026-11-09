"""
部门范围查询工具(RBAC 行级数据隔离)

提供共享的部门范围查询函数,所有 Selector 层的
get_queryset_for_user() 统一调用此模块。

核心函数:
- get_employee_for_user(user): 获取用户对应的 Employee(带请求级缓存)
- get_department_codes_for_user(user): 返回用户可访问的部门编码列表
- resolve_asset_department_codes(asset): 动态解析资产归属部门
"""

from collections.abc import Iterable
from typing import Any

from django.db.models import Q, QuerySet

from apps.usermanagement.models import Employee, EmployeeRole


# 资产归属三路径唯一事实源(DR-1:读面 Q 过滤与写面校验共用,禁止第二份路径字面量)。
# 每条路径为属性跳转链,末段 "department_code" 为目标编码字段:
# manager 保管人 → entry_person 入库人 → storage.storage_manager 仓库管理员。
_ASSET_ATTRIBUTION_CHAIN: tuple[tuple[str, ...], ...] = (
    ("asset_manager_recordcode", "employee_department", "department_code"),
    ("asset_entry_person_recordcode", "employee_department", "department_code"),
    ("asset_storage_recordcode", "storage_manager", "employee_department", "department_code"),
)


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
    - None: 无限制(system_admin / auditor / is_superuser)
    - 空列表: 无权限(无 Employee 记录,或部门级角色但无部门;最严兜底,仅保留查看权限)
    - 非空列表: 限定的部门范围

    【AUD-21】无 Employee 记录原先返回 None(不限制),但自注册账号天然无 Employee 绑定,
    叠加 AllowAny 注册端点即构成"自注册→全量可见"授权缺口。现反转为空列表(拒绝),
    与 unregisteredasset/selectors.py 对无 Employee 的既有拒绝语义对齐(DR-1)。
    """
    # 超级管理员:无限制
    if getattr(user, "is_superuser", False):
        return None

    employee = get_employee_for_user(user)

    # 无 Employee 记录:最严兜底,无数据访问(AUD-21 授权可见性缺口修复)
    if not employee:
        return []

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


def is_department_visible(department_code: str | None, user: Any) -> bool:
    """
    判断用户是否可见指定部门(BF-170 OP-01:员工域行级隔离旁路修复)。

    三态语义与 get_department_codes_for_user 完全同源(DR-1:唯一实现于本文件):
    - None(superuser / system_admin / auditor):不限,恒可见
    - 空列表(无 Employee / 部门级角色无部门,AUD-21 最严兜底):恒不可见
    - 非空列表:DEPT_MANAGER 已含 get_all_descendants 下级,成员判断即达
    """
    codes = get_department_codes_for_user(user)
    if codes is None:
        return True
    if not department_code:
        return False
    return department_code in codes


def get_effective_data_scope_for_user(user: Any) -> dict[str, Any]:
    """
    计算用户的有效数据范围(G1-B flavor a:直接派生自 Employee,零漂移)。

    与 get_department_codes_for_user 保持单一事实来源,供 my-permissions 端点
    与 employee_view.get_employee_permissions 统一调用。

    映射关系:
    - 无限制(superuser / system_admin / auditor) → {"scope_type": "all"}
    - 无 Employee 记录(最严兜底) → {departments, [], include_children: False}
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
    - 写权限: 所有 RBAC 写权限类一律拒绝(core.permissions.get_user_role 降级为 None)

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


def _resolve_attribution_codes_from_instances(owner: Any) -> set[str] | None:
    """按 _ASSET_ATTRIBUTION_CHAIN 对"持有归属属性的实例"解析候选部门码。

    返回语义与 asset_attribution_codes 一致:None = 无任何归属路径键(无从判定),
    set() = 路径键存在但全部为空(三路全空)。
    """
    seen_any_key = False
    codes: set[str] = set()
    for hops in _ASSET_ATTRIBUTION_CHAIN:
        current = owner
        ok = True
        for hop in hops[:-1]:
            if current is None:
                ok = False
                break
            if not hasattr(current, hop):
                ok = False
                break
            current = getattr(current, hop)
        if not ok:
            continue
        seen_any_key = True
        if current is not None:
            code = getattr(current, hops[-1], None)
            if code:
                codes.add(code)
    return codes if seen_any_key else None


def asset_attribution_codes(asset_data: Any) -> set[str] | None:
    """
    按三路径解析"待写入资产数据"的候选归属部门码(BF-170 M-01 写侧越权兜底)。

    asset_data 为 validated_data(Mapping):归属字段携带 Employee/Storage 模型实例。
    取码走实例属性遍历,任一环为 None/缺失即跳过该路径;禁止为取码再发 ORM filter
    (N+1 + 第二条实现路径)。返回语义:
    - None: asset_data 无任何归属路径键(无从判定,放行语义,与读面
      resolve_asset_department_codes 三态对齐)
    - set(): 路径键存在但全部为空(三路全空,D2 fail-closed 交由调用方定 400)
    - 非空 set: 候选归属部门码集合(OR 判定,与读面 _build_department_scope_q 一致)
    """
    seen_any_key = False
    codes: set[str] = set()
    for hops in _ASSET_ATTRIBUTION_CHAIN:
        if hops[0] not in asset_data:
            continue
        seen_any_key = True
        current = asset_data[hops[0]]
        for hop in hops[1:-1]:
            if current is None:
                break
            current = getattr(current, hop, None)
        if current is not None:
            code = getattr(current, hops[-1], None)
            if code:
                codes.add(code)
    return codes if seen_any_key else None


def ensure_asset_attribution_in_scope(user: Any, asset_data: Any) -> None:
    """
    写侧越权兜底(BF-170 M-01,D1/D2 拍板口径):
    - codes is None → 放行(如仅挂 asset_type,无任何归属路径)
    - codes == set()(三路全空)→ NO_DEPARTMENT_SCOPE(400,D2 fail-closed;
      system_admin 不受限,codes=None 分支在前)
    - codes 非空但与用户范围无交集 → ASSET_ATTRIBUTION_OUT_OF_SCOPE(400,D1)

    判定用 OR(交集非空即过),与读面 _build_department_scope_q 一致;
    禁止用 AND——会把存量跨部门资产的任何编辑打成 400(回归面爆炸)。
    """
    from core.exceptions import AppValidationError

    codes = asset_attribution_codes(asset_data)
    if codes is None:
        return
    user_codes = get_department_codes_for_user(user)
    if user_codes is None:
        return  # superuser / system_admin / auditor:不限
    if not codes:
        raise AppValidationError(
            detail="资产归属三路径(保管人/入库人/仓库)全为空,请至少指定一项归属",
            error_code="NO_DEPARTMENT_SCOPE",
        )
    if codes.isdisjoint(user_codes):
        raise AppValidationError(detail="资产归属部门不在您的管理范围内", error_code="ASSET_ATTRIBUTION_OUT_OF_SCOPE")


def ensure_employees_in_scope(user: Any, employees: Iterable[Any]) -> None:
    """
    出库使用人/保管人写侧归属校验(D-5;口径 2026-11-02:禁止跨部门借用)。

    - user 必填(M-07: create_outasset/update_outasset 均为 kw-only 必填,无 None 放行分支)
    - employees 中某项为 None → 跳过(本次未指定该人员,不构成写入;
      update 的 partial_update 未提交人员字段即此情形,不会误拦「只改使用地点」)
    - 员工无部门 → is_department_visible 返回 False(部门级角色);与 EmployeeSelector
      的部门过滤同源(无部门员工本就不在候选列表内),故不设单独分支(DR-1)
    """
    from core.exceptions import AppValidationError

    for emp in employees:
        if emp is None:
            continue
        dept = getattr(emp, "employee_department", None)
        if not is_department_visible(dept.department_code if dept else None, user):
            raise AppValidationError(
                detail=f"人员 {emp.employee_jobcode} 所属部门不在您的管理范围内",
                error_code="OUTASSET_PERSON_OUT_OF_SCOPE",
            )


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

    路径清单唯一事实源为 _ASSET_ATTRIBUTION_CHAIN(读面 Q 与写面校验共用)。

    field_prefix 用于区分查询主体:
    - "asset_recordcode": 通过 asset_recordcode FK 关联 Asset 的模型(HardDiskSN/OutAsset 等)
    - "": 直接查询 Asset 自身(字段本身即归属路径)
    """

    def path(fields: str) -> str:
        return f"{field_prefix}__{fields}" if field_prefix else fields

    q = Q()
    for hops in _ASSET_ATTRIBUTION_CHAIN:
        q |= Q(**{f"{path('__'.join(hops))}__in": dept_codes})
    return q


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


def get_employee_scoped_queryset_for_user(user: Any, queryset: QuerySet[Any, Any]) -> QuerySet[Any, Any]:
    """
    通用行级过滤:员工域按调用者部门范围收窄(BF-048)。

    完全委托 get_department_codes_for_user + filter_queryset_by_department,
    不新增任何范围规则(DR-1),语义与 OperationLogSelector._scope_by_user 一致:
    - None(无限制): superuser / system_admin / auditor
    - 空列表(无数据): 无 Employee 记录,或部门级角色但无部门,最严兜底(AUD-21)
    - 非空列表: dept_manager = 本部门 + 所有下级部门; asset_admin/regular_user = 仅本部门

    Employee 的部门归属字段是 employee_department(部门挂在员工上,与资产的三路径
    归属不同),故直接用 filter_queryset_by_department 的通用实现。

    用法(EmployeeViewSet.get_queryset —— list/retrieve/search/statistics/export 统一入口):
        qs = get_employee_scoped_queryset_for_user(request.user, Employee.objects.all())
    """
    return filter_queryset_by_department(queryset, get_department_codes_for_user(user), "employee_department")
