"""
部门审计适配器

封装对 GenericAuditService 的调用,为 department 模块提供统一的审计日志记录接口。
"""

from typing import Any

from apps.usermanagement.audit_helper import safe_audit_log


class DepartmentAuditAdapter:
    """部门审计适配器"""

    @staticmethod
    def log_create(department: Any, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_create,
            error_context="记录部门创建日志",
            record_code=department.department_code,
            app_label="department",
            description=f"创建部门: {department.department_name}",
            after_data={
                "department_code": department.department_code,
                "department_name": department.department_name,
                "level": department.level,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_update(
        department: Any,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_update,
            error_context="记录部门更新日志",
            record_code=department.department_code,
            app_label="department",
            description=f"更新部门: {department.department_name}",
            before_data=before_data,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @staticmethod
    def log_delete(
        department_code: str,
        department_name: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        from core.audit_service import GenericAuditService

        safe_audit_log(
            GenericAuditService.log_delete,
            error_context="记录部门删除日志",
            record_code=department_code,
            app_label="department",
            description=f"删除部门: {department_name}",
            before_data={"department_code": department_code, "department_name": department_name},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
