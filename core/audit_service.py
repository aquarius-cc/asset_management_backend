"""
通用审计日志服务

提供非资产操作的审计日志记录功能(部门、员工、用户、未登记资产等)。
"""

import logging
from typing import Any

from django.db import transaction

from core.audit_sanitizer import mask_sensitive_snapshot
from core.metrics import AUDIT_WRITE_FAILED
from core.models_audit import AuditLog
from core.request_context import get_current_ip


logger = logging.getLogger(__name__)


class GenericAuditService:
    """
    通用审计日志服务

    记录非资产操作的审计信息,所有方法容错处理。
    """

    @staticmethod
    def log_operation(
        record_code: str,
        app_label: str,
        operation_type: str,
        description: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """
        记录通用审计日志

        【M-13】写入经 transaction.on_commit 延迟到主事务提交后执行:审计 DB 失败不再落在
        业务 atomic 内(PG 下事务已 aborted, DatabaseError 反向放大为
        TransactionManagementError/500)。回调体兜底 + robust=True 双保险,失败仅 logger.error
        留痕不传播;延迟后无法返回实例,恒返回 None(既有调用方均未消费返回值)。
        """
        # 【OP-05 / OC-3】审计快照入库前脱敏, 唯一收口点(DR-1)。BF-165 的明文口径仅限
        # API 响应体; 落库快照的消费方只有 IsAuditorOrAdmin, 且手机号仍可经员工端点取得,
        # 故此处脱敏不推翻 BF-165, 也不减少任何既有能力。
        before_data = mask_sensitive_snapshot(before_data)
        after_data = mask_sensitive_snapshot(after_data)

        def _write_audit() -> None:
            try:
                AuditLog.objects.create(  # type: ignore[attr-defined]
                    record_code=record_code,
                    app_label=app_label,
                    operation_type=operation_type,
                    description=description,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                    before_data=before_data,
                    after_data=after_data,
                    ip_address=ip_address or get_current_ip(),
                )
            except Exception as e:
                # 【M-19】审计写入失败属合规事件, 计入指标供告警, 保留 error 日志不上抛
                AUDIT_WRITE_FAILED.labels(channel="generic_audit_log").inc()
                logger.error(f"通用审计日志记录失败: {e}", exc_info=True)

        transaction.on_commit(_write_audit, robust=True)
        return None

    @staticmethod
    def log_create(
        record_code: str,
        app_label: str,
        description: str,
        after_data: dict[str, Any] | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录创建操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="create",
            description=description,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )

    @staticmethod
    def log_update(
        record_code: str,
        app_label: str,
        description: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录更新操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="update",
            description=description,
            before_data=before_data,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )

    @staticmethod
    def log_delete(
        record_code: str,
        app_label: str,
        description: str,
        before_data: dict[str, Any] | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录删除操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="delete",
            description=description,
            before_data=before_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )

    @staticmethod
    def log_approve(
        record_code: str,
        app_label: str,
        description: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录审批操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="approve",
            description=description,
            before_data=before_data,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )

    @staticmethod
    def log_login(
        record_code: str,
        app_label: str,
        description: str,
        after_data: dict[str, Any] | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录登录操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="login",
            description=description,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )

    @staticmethod
    def log_state_change(
        record_code: str,
        app_label: str,
        from_state: str,
        to_state: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog | None:
        """记录状态变更操作"""
        return GenericAuditService.log_operation(
            record_code=record_code,
            app_label=app_label,
            operation_type="state_change",
            description=f"状态从 {from_state} 变更为 {to_state}",
            before_data={"status": from_state},
            after_data={"status": to_state},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address,
        )
