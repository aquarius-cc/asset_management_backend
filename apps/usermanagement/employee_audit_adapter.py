"""
员工审计适配器

封装对 GenericAuditService 的调用，为 employee 模块提供统一的审计日志记录接口。
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class EmployeeAuditAdapter:
    """员工审计适配器"""

    @staticmethod
    def log_create(employee, operator_jobcode: str | None = None, operator_name: str | None = None):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_create(
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
        except Exception as e:
            logger.error(f"记录员工创建日志失败: {e}", exc_info=True)

    @staticmethod
    def log_update(
        employee,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_update(
                record_code=employee.employee_jobcode,
                app_label="employee",
                description=f"更新员工: {employee.employee_name}",
                before_data=before_data,
                after_data=after_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录员工更新日志失败: {e}", exc_info=True)

    @staticmethod
    def log_delete(
        employee_jobcode: str, employee_name: str, operator_jobcode: str | None = None, operator_name: str | None = None
    ):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_delete(
                record_code=employee_jobcode,
                app_label="employee",
                description=f"删除员工: {employee_name}",
                before_data={"employee_jobcode": employee_jobcode, "employee_name": employee_name},
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录员工删除日志失败: {e}", exc_info=True)

    @staticmethod
    def log_state_change(
        employee,
        from_status: str,
        to_status: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ):
        try:
            from core.audit_service import GenericAuditService

            GenericAuditService.log_state_change(
                record_code=employee.employee_jobcode,
                app_label="employee",
                from_state=from_status,
                to_state=to_status,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            logger.error(f"记录员工状态变更日志失败: {e}", exc_info=True)
