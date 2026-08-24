"""
员工审计适配器

封装对 GenericAuditService 的调用,为 employee 模块提供统一的审计日志记录接口。
"""

from typing import Any

from apps.usermanagement.audit_helper import safe_audit_log


class EmployeeAuditAdapter:
    """员工审计适配器"""

    @staticmethod
    def log_create(employee: Any, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_create,
            error_context="记录员工创建日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            description=f"创建员工: {employee.employee_name}",
            after_data={
                "employee_jobcode": employee.employee_jobcode,
                "employee_name": employee.employee_name,
                "employee_status": employee.employee_status,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_update(
        employee: Any,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_update,
            error_context="记录员工更新日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            description=f"更新员工: {employee.employee_name}",
            before_data=before_data,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_delete(
        employee_jobcode: str, employee_name: str, operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_delete,
            error_context="记录员工删除日志",
            record_code=employee_jobcode,
            app_label="employee",
            description=f"删除员工: {employee_name}",
            before_data={"employee_jobcode": employee_jobcode, "employee_name": employee_name},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_state_change(
        employee: Any,
        from_status: str,
        to_status: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_state_change,
            error_context="记录员工状态变更日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            from_state=from_status,
            to_state=to_status,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_bind_auth_user(
        employee: Any,
        auth_username: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录员工绑定认证账号日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            operation_type="bind_auth_user",
            description=f"绑定认证账号: {auth_username}",
            after_data={"auth_username": auth_username},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_unbind_auth_user(
        employee: Any,
        old_auth_username: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录员工解绑认证账号日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            operation_type="unbind_auth_user",
            description=f"解绑认证账号: {old_auth_username}",
            before_data={"auth_username": old_auth_username},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_replace_auth_user(
        employee: Any,
        old_auth_username: str,
        new_auth_username: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_operation,
            error_context="记录员工替换认证账号日志",
            record_code=employee.employee_jobcode,
            app_label="employee",
            operation_type="replace_auth_user",
            description=f"替换认证账号: {old_auth_username} -> {new_auth_username}",
            before_data={"auth_username": old_auth_username},
            after_data={"auth_username": new_auth_username},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
