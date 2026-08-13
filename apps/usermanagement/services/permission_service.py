"""
权限查询服务层(只读,无写操作),提供用户权限和数据范围查询

类:
  - PermissionService: 权限查询服务(所有方法均为静态方法)

函数/方法:
  - get_user_permissions: 获取用户所有权限码(多角色取并集)
  - get_merged_data_scope: 获取用户合并后的 data_scope(多角色取最宽)
  - _merge_data_scopes: 合并多个角色的 data_scope
  - user_has_permission: 检查用户是否拥有指定权限码

调用链:
  本模块被 views/employee_view.py、authusermanagement/views.py 调用
  本模块依赖 models(UserRole, RolePermission, Permission)
"""

from apps.usermanagement.models import Permission, RolePermission, UserRole


class PermissionService:
    """
    权限查询服务(只读,无写操作)

    提供用户权限查询、数据范围合并等功能。
    所有方法均为静态方法,无需实例化。
    """

    @staticmethod
    def get_user_permissions(user_id: int) -> list[str]:
        """
        获取用户所有权限码列表(多角色取并集)。

        查询链:UserRole → RolePermission → Permission
        缓存:请求级别 _permissions_cache

        Args:
            user_id: AuthUser 的 auth_id

        Returns:
            权限码列表,如 ["asset:read", "asset:create", ...]
        """
        # 1. 查 UserRole 获取所有 role_id
        role_ids = list(
            UserRole.objects.filter(
                auth_user_id=user_id,
                is_deleted=False,
            ).values_list("role_id", flat=True)
        )

        if not role_ids:
            # Phase 7: Employee.role 已删除,无 UserRole 记录时返回空权限
            return []

        # 2. 批量查 RolePermission 获取所有 permission_id
        permission_ids = list(
            RolePermission.objects.filter(
                role_id__in=role_ids,
                is_deleted=False,
            ).values_list("permission_id", flat=True)
        )

        if not permission_ids:
            return []

        # 3. 批量查 Permission 获取所有 permission_code
        perm_codes = list(
            Permission.objects.filter(
                id__in=permission_ids,
                is_deleted=False,
            ).values_list("permission_code", flat=True)
        )

        # 4. 去重返回
        return list(set(perm_codes))

    @staticmethod
    def get_merged_data_scope(user_id: int) -> dict:
        """
        获取用户合并后的 data_scope(多角色取最宽)。

        合并逻辑:调用 merge_data_scopes()
        缓存:request 级别 user._rbac_data_scope

        Args:
            user_id: AuthUser 的 auth_id

        Returns:
            合并后的 data_scope 字典
        """
        # 1. 查 UserRole 获取所有 data_scope
        scopes = list(
            UserRole.objects.filter(
                auth_user_id=user_id,
                is_deleted=False,
            ).values_list("data_scope", flat=True)
        )

        # 2. 调用 merge_data_scopes() 合并
        return PermissionService._merge_data_scopes(scopes)

    @staticmethod
    def _merge_data_scopes(scopes: list[dict]) -> dict:
        """
        合并多个角色的 data_scope,取最宽范围。

        合并规则:
        - 任一角色有 "all" → 最终 = "all"
        - 收集所有部门编码,合并为 departments 类型
        - 无有效 scope 时返回最严格限制(无数据访问权限)
        """
        if not scopes:
            # C1 修复:无角色时返回最严格限制,而非全量
            return {"scope_type": "departments", "department_codes": [], "include_children": False}

        # 任一角色有 "all" → 最终 = "all"
        if any(s.get("scope_type") == "all" for s in scopes):
            return {"scope_type": "all"}

        # 收集所有部门编码
        all_dept_codes = set()
        include_children = False
        for s in scopes:
            if s.get("scope_type") == "department":
                dept_code = s.get("department_code")
                if dept_code:
                    all_dept_codes.add(dept_code)
                if s.get("include_children"):
                    include_children = True
            elif s.get("scope_type") == "departments":
                codes = s.get("department_codes", [])
                if isinstance(codes, list):
                    all_dept_codes.update(codes)

        # C3 修复:无有效部门编码时返回最严格限制,而非全量
        if not all_dept_codes:
            return {"scope_type": "departments", "department_codes": [], "include_children": False}

        return {
            "scope_type": "departments",
            "department_codes": sorted(all_dept_codes),
            "include_children": include_children,
        }

    @staticmethod
    def user_has_permission(user_id: int, permission_code: str) -> bool:
        """
        检查用户是否拥有指定权限码。

        Args:
            user_id: AuthUser 的 auth_id
            permission_code: 权限码,如 "asset:create"

        Returns:
            是否拥有该权限
        """
        perms = PermissionService.get_user_permissions(user_id)
        return permission_code in perms
