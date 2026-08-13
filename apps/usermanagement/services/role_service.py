"""
角色管理服务层,封装角色分配、撤销、权限同步等核心业务逻辑

类:
  - RoleService: 角色管理服务(所有写操作 @transaction.atomic)

函数/方法:
  - assign_role: 为用户分配角色(含 data_scope 验证、Token 黑名单)
  - remove_role: 撤销用户角色(幂等操作)
  - get_user_roles: 获取用户所有角色列表
  - sync_role_permissions: 同步角色的权限码列表(全量替换)
  - _validate_data_scope: 验证并规范化 data_scope 结构
  - _blacklist_user_tokens: 黑名单用户所有 Refresh Token

调用链:
  本模块被 views/role_view.py 调用
  本模块依赖 models(Role, UserRole, RolePermission, Permission)
  本模块依赖 role_audit_adapter.RoleAuditAdapter
"""

import logging

from django.db import transaction

from apps.usermanagement.models import Department, Permission, Role, RolePermission, UserRole
from apps.usermanagement.role_audit_adapter import RoleAuditAdapter
from core.exceptions import AppValidationError


logger = logging.getLogger(__name__)


class RoleService:
    """
    角色管理服务(所有写操作 @transaction.atomic)

    提供角色分配、撤销、同步等功能。
    所有写操作均使用事务保护,确保数据一致性。
    """

    @staticmethod
    @transaction.atomic
    def assign_role(user_id: int, role_id: int, data_scope: dict | None = None) -> UserRole:
        """
        为用户分配角色。

        创建 UserRole 记录,若已存在则更新 data_scope。
        创建后触发该用户所有 Refresh Token 黑名单(强制重新登录)。

        Args:
            user_id: AuthUser 的 auth_id
            role_id: Role 的 id
            data_scope: 数据范围字典,如 {"scope_type": "all"}

        Returns:
            创建或更新的 UserRole 实例

        Raises:
            AppValidationError: 用户或角色不存在
        """
        from apps.authusermanagement.models import AuthUser

        # 校验用户存在
        try:
            auth_user = AuthUser.objects.get(auth_id=user_id)
        except AuthUser.DoesNotExist:
            raise AppValidationError(detail="用户不存在", error_code="USER_NOT_FOUND")

        # 校验角色存在
        try:
            role = Role.objects.get(pk=role_id, is_deleted=False)
        except Role.DoesNotExist:
            raise AppValidationError(detail="角色不存在", error_code="ROLE_NOT_FOUND")

        # 验证 data_scope
        # H2 修复:data_scope 未提供时使用最严格限制
        if data_scope:
            data_scope = RoleService._validate_data_scope(data_scope)
        else:
            data_scope = {"scope_type": "departments", "department_codes": [], "include_children": False}

        # 创建或更新 UserRole
        user_role, _ = UserRole.objects.update_or_create(
            auth_user=auth_user,
            role=role,
            defaults={"data_scope": data_scope},
        )

        # 触发 Token 黑名单
        RoleService._blacklist_user_tokens(user_id)

        # 记录审计日志
        RoleAuditAdapter.log_assign_role(
            user_id=user_id,
            role_id=role_id,
            role_name=role.role_name,
            data_scope=data_scope,
            operator_jobcode=auth_user.auth_username,
            operator_name=auth_user.auth_username,
        )

        return user_role

    @staticmethod
    @transaction.atomic
    def remove_role(user_id: int, role_id: int) -> None:
        """
        撤销用户角色(幂等操作)。

        删除 UserRole 记录。
        删除后触发该用户所有 Refresh Token 黑名单。
        如果角色已被撤销,静默返回(幂等)。

        Args:
            user_id: AuthUser 的 auth_id
            role_id: Role 的 id
        """
        # 获取角色信息用于审计日志
        try:
            role = Role.objects.get(pk=role_id, is_deleted=False)
            role_name = role.role_name
        except Role.DoesNotExist:
            role_name = f"role_{role_id}"

        deleted, _ = UserRole.objects.filter(
            auth_user_id=user_id,
            role_id=role_id,
            is_deleted=False,
        ).delete()

        # H2 修复:仅在实际删除时触发 Token 黑名单
        if deleted:
            RoleService._blacklist_user_tokens(user_id)

            # 记录审计日志
            RoleAuditAdapter.log_remove_role(
                user_id=user_id,
                role_id=role_id,
                role_name=role_name,
                operator_jobcode=f"user_{user_id}",
                operator_name=f"user_{user_id}",
            )

    @staticmethod
    def get_user_roles(user_id: int) -> list[Role]:
        """
        获取用户所有角色列表。

        Args:
            user_id: AuthUser 的 auth_id

        Returns:
            角色列表
        """
        return list(
            Role.objects.filter(
                user_roles__auth_user_id=user_id,
                user_roles__is_deleted=False,
                is_deleted=False,
            ).distinct()
        )

    @staticmethod
    @transaction.atomic
    def sync_role_permissions(role_id: int, perm_codes: list[str]) -> None:
        """
        同步角色的权限码列表(全量替换)。

        删除旧记录 → 批量创建新记录。

        Args:
            role_id: Role 的 id
            perm_codes: 权限码列表,如 ["asset:read", "asset:create"]
        """
        # [HALT] C1 修复:硬删除旧记录(唯一约束作用于所有行含软删除,soft-delete + ignore_conflicts 会导致重复调用时权限被清零)
        RolePermission.all_objects.filter(role_id=role_id).delete()

        # 批量创建新记录
        if perm_codes:
            permissions = Permission.objects.filter(
                permission_code__in=perm_codes,
                is_deleted=False,
            )
            role_perms = [RolePermission(role_id=role_id, permission=perm) for perm in permissions]
            RolePermission.objects.bulk_create(role_perms, ignore_conflicts=True)

    @staticmethod
    def _validate_data_scope(scope: dict) -> dict:
        """
        验证并规范化 data_scope 结构。

        Args:
            scope: data_scope 字典

        Returns:
            验证后的 data_scope 字典

        Raises:
            AppValidationError: 结构不合法或部门不存在
        """
        VALID_SCOPE_TYPES = {"all", "department", "departments"}

        if not scope:
            return {"scope_type": "all"}

        scope_type = scope.get("scope_type")
        if scope_type not in VALID_SCOPE_TYPES:
            raise AppValidationError(
                detail=f"无效的 scope_type: {scope_type}",
                error_code="INVALID_SCOPE_TYPE",
            )

        if scope_type == "department":
            dept_code = scope.get("department_code")
            if not dept_code:
                raise AppValidationError(
                    detail="department 类型必须包含 department_code",
                    error_code="MISSING_DEPARTMENT_CODE",
                )
            # 验证部门存在
            if not Department.objects.filter(department_code=dept_code, is_deleted=False).exists():
                raise AppValidationError(
                    detail=f"部门 {dept_code} 不存在",
                    error_code="DEPARTMENT_NOT_FOUND",
                )

        if scope_type == "departments":
            codes = scope.get("department_codes", [])
            if not isinstance(codes, list) or len(codes) == 0:
                raise AppValidationError(
                    detail="departments 类型必须包含非空 department_codes 列表",
                    error_code="MISSING_DEPARTMENT_CODES",
                )
            # 验证所有部门存在
            existing = set(
                Department.objects.filter(department_code__in=codes, is_deleted=False).values_list(
                    "department_code", flat=True
                )
            )
            missing = set(codes) - existing
            if missing:
                raise AppValidationError(
                    detail=f"以下部门不存在: {', '.join(sorted(missing))}",
                    error_code="DEPARTMENT_NOT_FOUND",
                )

        return scope

    @staticmethod
    def _blacklist_user_tokens(user_id: int) -> None:
        """
        黑名单该用户的所有 Refresh Token,强制重新登录。

        Args:
            user_id: AuthUser 的 auth_id
        """
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken,
                OutstandingToken,
            )

            outstanding = OutstandingToken.objects.filter(user_id=user_id)
            blacklisted_count = 0
            for token in outstanding:
                _, created = BlacklistedToken.objects.get_or_create(token=token)
                if created:
                    blacklisted_count += 1

            if blacklisted_count > 0:
                logger.info(f"角色变更:已黑名单 {blacklisted_count} 个 Token (user_id={user_id})")
        except Exception as e:
            # H4 修复:记录异常而非静默吞没
            logger.warning(f"Token 黑名单操作失败 (user_id={user_id}): {e}")
