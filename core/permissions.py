"""
自定义权限类

提供项目统一的权限控制：
- IsOwnerOrReadOnly: 资源所有者可修改，其他用户只读
- IsAdminUser: 仅管理员可访问（兼容旧代码）
- IsAuthenticatedUser: 仅登录用户可访问
- IsSystemAdmin: 系统管理员（RBAC）
- IsDeptManagerOrAbove: 部门经理及以上（RBAC）
- IsAssetAdminOrAbove: 资产管理员及以上（RBAC）
- IsAuditorOrAdmin: 审计员或管理员（RBAC，只读全量数据）

注意：使用延迟导入避免循环依赖（core → usermanagement → core）。
"""

from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """只有资源所有者才能修改，其他用户只能读取"""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if hasattr(obj, "owner"):
            return obj.owner == request.user
        if hasattr(obj, "user"):
            return obj.user == request.user
        return False


class IsAdminUser(permissions.BasePermission):
    """
    只有管理员才能访问（兼容旧代码，检查 is_staff）

    新代码应使用 IsSystemAdmin / IsAssetAdminOrAbove 等 RBAC 权限类。
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsAuthenticatedUser(permissions.BasePermission):
    """需要登录才能访问"""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


# =====================================================================
# RBAC 权限类（P1-4 / P2-11 实施）
# 使用字符串常量避免循环导入，权限检查时才查 Employee
# =====================================================================

_ROLE_SYSTEM_ADMIN = "system_admin"
_ROLE_DEPT_MANAGER = "dept_manager"
_ROLE_ASSET_ADMIN = "asset_admin"
_ROLE_AUDITOR = "auditor"


def _get_user_role(user) -> str | None:
    """
    获取用户角色。

    延迟导入 Employee 和 get_employee_for_user 避免循环依赖。
    is_superuser 直接返回 system_admin，不查数据库。
    """
    if getattr(user, "is_superuser", False):
        return _ROLE_SYSTEM_ADMIN
    from apps.usermanagement.models import Employee

    employee = Employee.objects.filter(
        employee_jobcode=user.auth_username
    ).select_related("employee_department").first()
    # 缓存到 request cycle
    if not hasattr(user, "_rbac_employee"):
        user._rbac_employee = employee
    return employee.role if employee else None


class IsSystemAdmin(permissions.BasePermission):
    """
    系统管理员：is_superuser 或 role=system_admin

    适用场景：系统配置（类型/仓库/合同/员工/部门/用户管理）
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return _get_user_role(request.user) == _ROLE_SYSTEM_ADMIN


class IsDeptManagerOrAbove(permissions.BasePermission):
    """
    部门经理及以上：system_admin / dept_manager

    适用场景：报废审批、未登记资产处理
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = _get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_DEPT_MANAGER)


class IsAssetAdminOrAbove(permissions.BasePermission):
    """
    资产管理员及以上：system_admin / dept_manager / asset_admin

    适用场景：资产增删改、出库/回收、损坏/遗失登记
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = _get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_DEPT_MANAGER, _ROLE_ASSET_ADMIN)


class IsAuditorOrAdmin(permissions.BasePermission):
    """
    审计员或管理员：system_admin / auditor

    适用场景：审计日志查看（全部数据）
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = _get_user_role(request.user)
        return role in (_ROLE_SYSTEM_ADMIN, _ROLE_AUDITOR)
