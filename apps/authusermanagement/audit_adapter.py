"""
认证审计适配器

封装对 GenericAuditService 的调用，为 authusermanagement 模块提供统一的审计日志记录接口。
"""

import logging


logger = logging.getLogger(__name__)


class AuthAuditAdapter:
    """认证审计适配器"""

    @staticmethod
    def log_register(user, operator_jobcode: str | None = None, operator_name: str | None = None):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_create(
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
        except Exception as e:
            logger.error(f"记录用户注册日志失败: {e}", exc_info=True)

    @staticmethod
    def log_login(user, operator_jobcode: str | None = None, operator_name: str | None = None):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_login(
                record_code=user.auth_username,
                app_label="authuser",
                description=f"用户登录: {user.auth_username}",
                after_data={"auth_username": user.auth_username},
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录用户登录日志失败: {e}", exc_info=True)

    @staticmethod
    def log_logout(username: str, operator_jobcode: str | None = None, operator_name: str | None = None):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_operation(
                record_code=username,
                app_label="authuser",
                operation_type="logout",
                description=f"用户登出: {username}",
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录用户登出日志失败: {e}", exc_info=True)
