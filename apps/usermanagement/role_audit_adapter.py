"""
角色审计适配器

封装 GenericAuditService 调用,提供统一的审计日志记录接口。
"""

from typing import Any

from apps.usermanagement.audit_helper import safe_audit_log


class RoleAuditAdapter:
    """角色审计适配器"""

    @staticmethod
    def log_assign_role(
        user_id: int,
        role_id: int,
        role_name: str,
        data_scope: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """记录角色分配日志"""
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录角色分配日志",
            record_code=f"user_{user_id}_role_{role_id}",
            app_label="user_role",
            operation_type="assign",
            description=f"为用户 {user_id} 分配角色: {role_name}",
            after_data={
                "user_id": user_id,
                "role_id": role_id,
                "role_name": role_name,
                "data_scope": data_scope,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_remove_role(
        user_id: int,
        role_id: int,
        role_name: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """记录角色撤销日志"""
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录角色撤销日志",
            record_code=f"user_{user_id}_role_{role_id}",
            app_label="user_role",
            operation_type="remove",
            description=f"撤销用户 {user_id} 的角色: {role_name}",
            before_data={
                "user_id": user_id,
                "role_id": role_id,
                "role_name": role_name,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_sync_permissions(
        role_id: int,
        role_name: str,
        perm_codes: list[str],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """记录权限同步日志"""
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录权限同步日志",
            record_code=f"role_{role_id}_permissions",
            app_label="role_permission",
            operation_type="sync",
            description=f"同步角色 {role_name} 的权限",
            after_data={
                "role_id": role_id,
                "role_name": role_name,
                "permission_count": len(perm_codes),
                "permission_codes": perm_codes,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
