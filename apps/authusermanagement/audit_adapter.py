"""
认证审计适配器

封装对 GenericAuditService 的调用,为 authusermanagement 模块提供统一的审计日志记录接口。
失败经 core.audit_failure.safe_audit_call 收口: 分渠道计数 + 脱敏日志(批次 2 / M-02)。
"""

from typing import Any

from core.audit_failure import safe_audit_call


class AuthAuditAdapter:
    """认证审计适配器"""

    @staticmethod
    def log_register(user: Any, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        from core.audit_service import GenericAuditService  # 延迟导入: 保持既有装配次序

        safe_audit_call(
            GenericAuditService.log_create,
            channel="generic_audit_dispatch",
            context="认证域-记录用户注册日志",
            record_code=user.auth_username,
            app_label="authuser",
            description=f"用户注册: {user.auth_username}",
            after_data={
                "auth_username": user.auth_username,
                "email": user.email,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_login(user: Any, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        from core.audit_service import GenericAuditService  # 延迟导入: 保持既有装配次序

        safe_audit_call(
            GenericAuditService.log_login,
            channel="generic_audit_dispatch",
            context="认证域-记录用户登录日志",
            record_code=user.auth_username,
            app_label="authuser",
            description=f"用户登录: {user.auth_username}",
            after_data={"auth_username": user.auth_username},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_logout(username: str, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        from core.audit_service import GenericAuditService  # 延迟导入: 保持既有装配次序

        safe_audit_call(
            GenericAuditService.log_operation,
            channel="generic_audit_dispatch",
            context="认证域-记录用户登出日志",
            record_code=username,
            app_label="authuser",
            operation_type="logout",
            description=f"用户登出: {username}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
