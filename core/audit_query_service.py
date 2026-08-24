"""
通用审计日志查询服务

提供 AuditLog 的只读查询接口,支持多种维度的组合查询。

【AGENTS 规范 - P1-09】View 层查询逻辑下沉到 Service 层,
View 仅负责参数解析(含校验)和响应格式化。
"""

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from core.models_audit import AuditLog


logger = logging.getLogger(__name__)


class AuditLogQueryService:
    """
    通用审计日志查询服务

    提供只读查询接口,支持按应用标识、操作类型、操作人、时间范围等维度查询。
    """

    @staticmethod
    def get_by_pk(pk: int) -> AuditLog | None:
        """
        根据主键查询单条审计记录

        Args:
            pk: 审计记录主键ID

        Returns:
            Optional[AuditLog]: 审计记录实例或 None
        """
        try:
            return AuditLog.objects.get(pk=pk)  # type: ignore[no-any-return,attr-defined]
        except AuditLog.DoesNotExist:
            return None

    @staticmethod
    def get_by_logging_id(logging_id: str) -> AuditLog | None:
        """
        根据 logging_id 查询单条审计记录

        Args:
            logging_id: 日志记录唯一标识

        Returns:
            Optional[AuditLog]: 审计记录实例或 None
        """
        try:
            return AuditLog.objects.get(logging_id=logging_id)  # type: ignore[no-any-return,attr-defined]
        except AuditLog.DoesNotExist:
            return None

    @staticmethod
    def query_logs(
        app_label: str | None = None,
        operation_type: str | None = None,
        operator_jobcode: str | None = None,
        record_code: str | None = None,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> list[AuditLog]:
        """
        多条件组合查询审计记录

        Args:
            app_label: 应用标识(department / employee / authuser)
            operation_type: 操作类型
            operator_jobcode: 操作人工号
            record_code: 被操作记录编码
            start_time: 起始时间(datetime 实例)
            end_time: 截止时间(datetime 实例)

        Returns:
            List[AuditLog]: 按时间倒序排列的审计记录
        """
        queryset = AuditLog.objects.all()  # type: ignore[attr-defined]

        if app_label:
            queryset = queryset.filter(app_label=app_label)

        if operation_type:
            queryset = queryset.filter(operation_type=operation_type)

        if operator_jobcode:
            queryset = queryset.filter(operator_jobcode=operator_jobcode)

        if record_code:
            queryset = queryset.filter(record_code=record_code)

        if start_time:
            queryset = queryset.filter(operation_time__gte=start_time)

        if end_time:
            queryset = queryset.filter(operation_time__lte=end_time)

        return list(queryset.order_by("-operation_time"))

    @staticmethod
    def get_recent_logs(days: int = 7) -> list[AuditLog]:
        """
        获取最近 N 天的审计记录

        Args:
            days: 天数,默认 7 天

        Returns:
            List[AuditLog]: 最近的审计记录
        """
        start_time = timezone.now() - timedelta(days=days)
        return list(AuditLog.objects.filter(operation_time__gte=start_time).order_by("-operation_time"))  # type: ignore[attr-defined]

    @staticmethod
    def get_logs_by_app_label(app_label: str) -> list[AuditLog]:
        """
        按应用标识查询审计记录

        Args:
            app_label: 应用标识

        Returns:
            List[AuditLog]: 指定应用的审计记录
        """
        return list(AuditLog.objects.filter(app_label=app_label).order_by("-operation_time"))  # type: ignore[attr-defined]

    @staticmethod
    def get_logs_by_operator(operator_jobcode: str) -> list[AuditLog]:
        """
        按操作人查询审计记录

        Args:
            operator_jobcode: 操作人工号

        Returns:
            List[AuditLog]: 该操作人的审计记录
        """
        return list(AuditLog.objects.filter(operator_jobcode=operator_jobcode).order_by("-operation_time"))  # type: ignore[attr-defined]
