"""
自定义权限类

提供项目统一的权限控制:
- IsOwnerOrReadOnly: 资源所有者才能修改,其他用户只读
- IsAdminUser: 仅管理员才能访问(兼容旧代码)
- IsAuthenticatedUser: 仅登录才能访问
- IsSystemAdmin: 系统管理员(RBAC)
- IsDeptManagerOrAbove: 部门经理及以上(RBAC)
- IsAssetAdminOrAbove: 资产管理员及以上(RBAC)
- IsSystemAdminOrAssetAdmin: 系统管理员或资产管理员(RBAC, 4.5 矩阵提交/编辑/删除角色面)
- IsAuditorOrAdmin: 审计员或管理员(RBAC,只读全量数据)
- CanExportExcel: 导出 Excel(矩阵 :148: 四角色可导,regular ❌)
- get_user_role / is_system_admin: 角色解析公开入口(代录白名单等 View 层复用, DR-1)
- resolve_viewset_permissions: ViewSet get_permissions 统一解析入口(DR-1)

注意:使用延迟导入避免循环依赖(core → usermanagement → core)。
"""

from collections.abc import Collection, Mapping
from typing import Any

from rest_framework import permissions
from rest_framework.permissions import BasePermission


class IsOwnerOrReadOnly(permissions.BasePermission):
    """只有资源所有者才能修改,其他用户只能读取"""

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        if hasattr(obj, "owner"):
            return obj.owner == request.user  # type: ignore[no-any-return]
        if hasattr(obj, "user"):
            return obj.user == request.user  # type: ignore[no-any-return]
        return False


class IsAdminUser(permissions.BasePermission):
    """
    只有管理员才能访问(兼容旧代码,检查 is_staff)

    新代码应使用 IsSystemAdmin / IsAssetAdminOrAbove 等 RBAC 权限类。
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsAuthenticatedUser(permissions.BasePermission):
    """需要登录才能访问"""

    def has_permission(self, request: Any, view: Any) -> bool:
        return bool(request.user and request.user.is_authenticated)


# =====================================================================
# RBAC 权限类(P1-4 / P2-11 实施)
# 使用字符串常量避免循环导入,权限检查时才查 Employee
# =====================================================================

_ROLE_SYSTEM_ADMIN = "system_admin"
_ROLE_DEPT_MANAGER = "dept_manager"
_ROLE_ASSET_ADMIN = "asset_admin"
_ROLE_AUDITOR = "auditor"


def get_user_role(user: Any) -> str | None:
    """
    获取用户角色(公开入口,供 View 层代录白名单等场景复用, DR-1)。

    延迟导入避免循环依赖。
    is_superuser 直接返回 system_admin,不查数据库。
    部门级角色但无部门 → 返回 None:写权限判定降级为无角色权限,
    与权限码(read-only)与数据范围(空)语义一致(最严兜底)。
    专项测试见 TestNoDepartmentWriteDegradation(core/tests/test_rbac_edge_cases.py)。
    """
    if getattr(user, "is_superuser", False):
        return _ROLE_SYSTEM_ADMIN

    from core.department_scope import get_employee_for_user, is_no_department_dept_scoped

    employee = get_employee_for_user(user)
    if is_no_department_dept_scoped(user):
        return None
    return employee.role if employee else None


def is_system_admin(user: Any) -> bool:
    """当前用户是否系统管理员(is_superuser 或 role=system_admin)。"""
    if not (getattr(user, "is_authenticated", False)):
        return False
    return get_user_role(user) == _ROLE_SYSTEM_ADMIN


class IsSystemAdmin(permissions.BasePermission):
    """
    系统管理员:is_superuser 或 role=system_admin

    适用场景:系统配置(类型/仓库/合同/员工/部门/用户管理)
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        return get_user_role(request.user) == _ROLE_SYSTEM_ADMIN


class IsDeptManagerOrAbove(permissions.BasePermission):
    """
    部门经理及以上:system_admin / dept_manager

    适用场景:报废审批、未登记资产处理
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        role = get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_DEPT_MANAGER)


class IsAssetAdminOrAbove(permissions.BasePermission):
    """
    资产管理员及以上:system_admin / dept_manager / asset_admin

    适用场景:资产增删改、出库/回收、损坏/遗失登记、未登记资产查看(4.5 矩阵 :190)
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        role = get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_DEPT_MANAGER, _ROLE_ASSET_ADMIN)


class IsSystemAdminOrAssetAdmin(permissions.BasePermission):
    """
    系统管理员或资产管理员:system_admin / asset_admin

    适用场景:未登记资产提交/编辑/删除/批量删除(4.5 矩阵 :189/:191 role 面,
    dept_manager 编辑删除 ❌ 只读故不纳入)
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        role = get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_ASSET_ADMIN)


class IsAuditorOrAdmin(permissions.BasePermission):
    """
    审计员或管理员:system_admin / auditor

    适用场景:审计日志查看(全部数据)
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        role = get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_AUDITOR)


# 矩阵 :148「导出 Excel」行: system / dept_manager / asset_admin / auditor ✅, regular ❌
_EXPORT_EXCEL_ROLES = (
    _ROLE_SYSTEM_ADMIN,
    _ROLE_DEPT_MANAGER,
    _ROLE_ASSET_ADMIN,
    _ROLE_AUDITOR,
)


class CanExportExcel(permissions.BasePermission):
    """
    导出 Excel 权限(矩阵 :148): 四角色可导,regular_user 禁止。

    适用场景: ExportExcelMixin.export_excel 及所有带导出能力的 ViewSet。
    """

    message = "无导出权限: 仅资产管理员及以上或审计员可导出"

    def has_permission(self, request: Any, view: Any) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        role = get_user_role(request.user)
        return role in _EXPORT_EXCEL_ROLES


def resolve_viewset_permissions(
    action: str | None,
    admin_actions: Collection[str],
    admin_permission: type[BasePermission],
    *,
    action_overrides: Mapping[str, type[BasePermission]] | None = None,
) -> list[BasePermission]:
    """
    ViewSet.get_permissions 统一解析(DR-1: 权限分支唯一实现)。

    优先级: export_excel → action_overrides → admin_actions → 默认 IsAuthenticated。
    """
    if action == "export_excel":
        return [CanExportExcel()]
    if action_overrides is not None and action is not None and action in action_overrides:
        return [action_overrides[action]()]
    if action is not None and action in admin_actions:
        return [admin_permission()]
    return [permissions.IsAuthenticated()]
