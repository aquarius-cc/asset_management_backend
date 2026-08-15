"""
权限查询服务层(只读,无写操作),提供用户有效权限码查询

类:
  - PermissionService: 权限查询服务(所有方法均为静态方法)

函数/方法:
  - get_effective_permissions_for_user: 获取用户有效权限码(部门级角色无部门最严兜底 + 多角色并集 + G6 回退 + superuser 全量)
  - _fallback_role_permissions: 无 UserRole 权限时按 Employee.role 回退种子角色权限(G6)

调用链:
  本模块被 authusermanagement/views.py(MyPermissionsAPIView)与
  views/employee_view.py(get_employee_permissions)调用
  本模块依赖 models(UserRole, RolePermission, Role, Permission, EmployeeRole)与
  core.department_scope.get_employee_for_user

废弃记录(2026-08-14): get_user_permissions / get_merged_data_scope / _merge_data_scopes /
user_has_permission 因 G1-B 收敛已删除,查询路径统一走 get_effective_permissions_for_user。
"""

from apps.usermanagement.models import (
    EmployeeRole,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from core.department_scope import get_employee_for_user, is_no_department_dept_scoped


class PermissionService:
    """
    权限查询服务(只读,无写操作)

    提供用户有效权限码查询。所有方法均为静态方法,无需实例化。
    """

    @staticmethod
    def get_effective_permissions_for_user(user) -> list[str]:
        """
        获取用户有效权限码列表。

        优先级:
        1. superuser → 全量权限码(后端 IsSystemAdmin 同语义)
        2. 部门级角色(asset_admin/dept_manager/regular_user)但无部门 → 最严兜底,仅保留查看(read)权限
        3. UserRole → RolePermission → Permission 多角色并集
        4. 并集为空时 → Employee.role 回退种子角色权限(G6,兼容遗留数据)

        Args:
            user: AuthUser 实例(request.user)

        Returns:
            权限码列表,如 ["asset:read", "asset:create", ...]
        """
        # 1. superuser:全量权限码
        if getattr(user, "is_superuser", False):
            return list(
                Permission.objects.filter(is_deleted=False).values_list("permission_code", flat=True)
            )

        # 2. 部门级角色无部门:最严兜底,仅保留查看(read)权限(全局角色不触发)
        if is_no_department_dept_scoped(user):
            return PermissionService._view_only_permission_codes()

        # 3. UserRole 多角色并集
        role_ids = list(
            UserRole.objects.filter(
                auth_user_id=user.auth_id,
                is_deleted=False,
            ).values_list("role_id", flat=True)
        )

        if role_ids:
            permission_ids = list(
                RolePermission.objects.filter(
                    role_id__in=role_ids,
                    is_deleted=False,
                ).values_list("permission_id", flat=True)
            )
            if permission_ids:
                perm_codes = list(
                    Permission.objects.filter(
                        id__in=permission_ids,
                        is_deleted=False,
                    ).values_list("permission_code", flat=True)
                )
                if perm_codes:
                    return list(set(perm_codes))

        # 4. G6 回退:无 UserRole 权限时按 Employee.role 回退种子角色权限
        return PermissionService._fallback_role_permissions(user)

    @staticmethod
    def _view_only_permission_codes() -> list[str]:
        """无部门兜底:全库 action=read 的查看权限码(无任何操作权限)。"""
        return list(
            Permission.objects.filter(action="read", is_deleted=False).values_list("permission_code", flat=True)
        )

    @staticmethod
    def _fallback_role_permissions(user) -> list[str]:
        """
        按 Employee.role 回退到种子角色权限(G6)。

        覆盖场景:遗留数据中 Employee.role 已设置但无 UserRole 记录(或角色无权限),
        此时按角色码查 Role → RolePermission → Permission,避免 my-permissions 误报空权限。

        回退规则:
        - 无 Employee 或 role 为空 → []
        - role == regular_user → [](普通用户无种子权限)
        - 角色不存在或已软删除 → [](DoesNotExist 兜底,不抛错)

        Args:
            user: AuthUser 实例

        Returns:
            权限码列表(可为空)
        """
        employee = get_employee_for_user(user)
        if not employee or not employee.role:
            return []

        if employee.role == EmployeeRole.REGULAR_USER:
            return []

        try:
            role = Role.objects.get(role_code=employee.role, is_deleted=False)
        except Role.DoesNotExist:
            return []

        permission_ids = list(
            RolePermission.objects.filter(
                role_id=role.id,
                is_deleted=False,
            ).values_list("permission_id", flat=True)
        )
        if not permission_ids:
            return []

        return list(
            set(
                Permission.objects.filter(
                    id__in=permission_ids,
                    is_deleted=False,
                ).values_list("permission_code", flat=True)
            )
        )
