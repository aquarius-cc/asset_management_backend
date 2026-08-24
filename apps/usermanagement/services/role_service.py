"""
角色管理服务层,封装角色分配、撤销、权限同步等核心业务逻辑

类:
  - RoleService: 角色管理服务(所有写操作 @transaction.atomic)

函数/方法:
  - assign_role: 为用户分配角色(D1 继承部门 / D2 同步 Employee.role / M3 自定义角色禁止分配)
  - remove_role: 撤销用户角色(幂等,同步重算 Employee.role)
  - get_user_roles: 获取用户所有角色列表
  - sync_role_permissions: 同步角色的权限码列表(全量替换)
  - _recompute_employee_role: D2 重算 Employee.role(最高 role_level 胜出,instance.save 触发黑名单)
  - _resolve_operator: 解析审计操作者(优先显式传入,其次 request 上下文)

调用链:
  本模块被 views/role_view.py 调用
  本模块依赖 models(Role, UserRole, RolePermission, Permission, EmployeeRole)与
  role_audit_adapter.RoleAuditAdapter、core.department_scope、core.request_context
"""

import logging
from typing import Any

from django.db import transaction

from apps.usermanagement.models import EmployeeRole, Permission, Role, RolePermission, UserRole
from apps.usermanagement.role_audit_adapter import RoleAuditAdapter
from core.department_scope import get_effective_data_scope_for_user, get_employee_for_user
from core.exceptions import AppValidationError
from core.request_context import get_current_request


logger = logging.getLogger(__name__)


class RoleService:
    """
    角色管理服务(所有写操作 @transaction.atomic)

    提供角色分配、撤销、同步等功能。
    所有写操作均使用事务保护,确保数据一致性。
    """

    @staticmethod
    @transaction.atomic
    def assign_role(
        user_id: int,
        role_id: int,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> UserRole:
        """
        为用户分配角色。

        D1: data_scope 继承 Employee 部门(单入口,零漂移),忽略客户端传入。
        D2: 分配后重算 Employee.role(当前角色 + 活跃 UserRole 最高 role_level),
            role 变化时由 Employee.save 钩子黑名单 Token(G3 去重)。
        M3: 自定义角色(role_code ∉ EmployeeRole.values)禁止分配。

        Args:
            user_id: AuthUser 的 auth_id
            role_id: Role 的 id
            operator_jobcode: 操作者工号(缺省时从请求上下文解析)
            operator_name: 操作者姓名

        Returns:
            创建或更新的 UserRole 实例

        Raises:
            AppValidationError: 用户/角色不存在,或角色为自定义角色
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

        # M3:禁止分配自定义角色(仅 EmployeeRole 内置角色可分配)
        if role.role_code not in EmployeeRole.values:
            raise AppValidationError(
                detail=f"角色 {role.role_name} 为自定义角色,不可分配给用户",
                error_code="CUSTOM_ROLE_NOT_ASSIGNABLE",
            )

        # D1:数据范围继承 Employee 部门(无部门→最严兜底,全局角色→all)
        data_scope = get_effective_data_scope_for_user(auth_user)

        # 创建或更新 UserRole
        user_role, _ = UserRole.objects.update_or_create(
            auth_user=auth_user,
            role=role,
            defaults={"data_scope": data_scope},
        )

        # D2:重算 Employee.role(role 变化时由 Employee.save 钩子黑名单 Token)
        RoleService._recompute_employee_role(auth_user)

        # 审计日志(操作者 = 实际请求操作者)
        op_jobcode, op_name = RoleService._resolve_operator(operator_jobcode, operator_name)
        RoleAuditAdapter.log_assign_role(
            user_id=user_id,
            role_id=role_id,
            role_name=role.role_name,
            data_scope=data_scope,
            operator_jobcode=op_jobcode,
            operator_name=op_name,
        )

        return user_role  # type: ignore[no-any-return]

    @staticmethod
    @transaction.atomic
    def remove_role(
        user_id: int,
        role_id: int,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        撤销用户角色(幂等操作)。

        删除 UserRole 记录后,同步重算 Employee.role(D2,可能降级,
        role 变化时由 Employee.save 钩子黑名单 Token)。

        Args:
            user_id: AuthUser 的 auth_id
            role_id: Role 的 id
            operator_jobcode: 操作者工号(缺省时从请求上下文解析)
            operator_name: 操作者姓名
        """
        # 获取角色信息用于审计日志与降级排除(含软删除角色,便于识别撤销目标)
        role = Role.objects.filter(pk=role_id).first()
        role_name = role.role_name if role else f"role_{role_id}"
        exclude_role_code = role.role_code if role else None

        deleted, _ = UserRole.objects.filter(
            auth_user_id=user_id,
            role_id=role_id,
            is_deleted=False,
        ).delete()

        # 仅在实际删除时同步 Employee.role 并记录审计日志
        if deleted:
            try:
                from apps.authusermanagement.models import AuthUser

                auth_user = AuthUser.objects.get(auth_id=user_id)
            except AuthUser.DoesNotExist:
                auth_user = None

            if auth_user is not None:
                RoleService._recompute_employee_role(auth_user, exclude_role_code=exclude_role_code)

            op_jobcode, op_name = RoleService._resolve_operator(operator_jobcode, operator_name)
            RoleAuditAdapter.log_remove_role(
                user_id=user_id,
                role_id=role_id,
                role_name=role_name,
                operator_jobcode=op_jobcode,
                operator_name=op_name,
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
    def _recompute_employee_role(auth_user: Any, exclude_role_code: str | None = None) -> None:
        """
        D2:重新计算 Employee.role。

        候选集 = 活跃 UserRole 的 role_code + {当前 Employee.role}(仅当未被任一活跃
        UserRole 表示且不等于 exclude_role_code —— 即遗留种子 G6 基线)。
        - exclude_role_code 由 remove_role 传入被撤销角色码,防止降级失效
          (写权限类 Is*OrAbove 直接读 Employee.role,撤销必须同步降级,否则撤销无效)
        - 仅保留 ∈ EmployeeRole.values 且存在未删除 Role 记录的码(M1,过滤自定义/幽灵角色)
        - role_level 最高者胜出(5/4/3/2/1),并列时按角色码字典序稳定排序
        - 无候选 → regular_user
        - 必须 instance.save(update_fields=["role"]) 触发 role_changed 黑名单钩子(G3 去重)

        Args:
            auth_user: AuthUser 实例
            exclude_role_code: 本次撤销的角色码(从候选中排除)
        """
        employee = get_employee_for_user(auth_user)
        if not employee:
            return

        active_codes = set(
            UserRole.objects.filter(
                auth_user=auth_user,
                is_deleted=False,
                role__is_deleted=False,
            ).values_list("role__role_code", flat=True)
        )

        candidate_codes = set(active_codes)
        if (
            employee.role
            and employee.role not in active_codes
            and employee.role != exclude_role_code
        ):
            candidate_codes.add(employee.role)

        valid_codes = [c for c in candidate_codes if c in EmployeeRole.values]
        new_role = EmployeeRole.REGULAR_USER
        if valid_codes:
            levels = {
                r.role_code: r.role_level
                for r in Role.objects.filter(role_code__in=valid_codes, is_deleted=False)
            }
            winners = [c for c in valid_codes if c in levels]
            if winners:
                new_role = sorted(winners, key=lambda c: (levels[c], c), reverse=True)[0]

        if employee.role != new_role:
            employee.role = new_role
            employee.save(update_fields=["role"])

    @staticmethod
    def _resolve_operator(operator_jobcode: str | None, operator_name: str | None) -> tuple[str | None, str | None]:
        """
        解析审计操作者:显式传入优先,其次从请求上下文取 request.user。

        Args:
            operator_jobcode: 显式传入的操作者工号
            operator_name: 显式传入的操作者姓名

        Returns:
            (operator_jobcode, operator_name)
        """
        if operator_jobcode is not None:
            return operator_jobcode, operator_name

        request = get_current_request()
        user = getattr(request, "user", None) if request else None
        if user is not None and getattr(user, "is_authenticated", False):
            from utils.user_utils import resolve_operator

            return resolve_operator(user)

        return None, None
