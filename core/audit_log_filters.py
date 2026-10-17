"""通用审计日志查询参数解析与校验。

【为什么要独立模块】
审计日志的**列表**与**导出**两个端点共用同一套过滤参数(app_label /
operation_type / operator_jobcode / record_code / start_date / end_date /
days)。若各自解析即构成重复实现(DR-1),故抽取为
:func:`parse_audit_log_filters` 单一入口。

放在独立模块而非 ``audit_log_views.py``,也是为了控制后者文件规模
(DR-5 <= 500 行)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from core.models_audit import AuditLog


__all__ = [
    "AUDIT_OPERATION_TYPE_DISPLAY_MAP",
    "AuditLogFilters",
    "InvalidAuditLogFilters",
    "parse_audit_log_filters",
]

DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_ERROR = "格式错误,应为 YYYY-MM-DD"

#: 操作类型取值 -> 中文标签，用于导出列的 display_map（单一事实来源）
AUDIT_OPERATION_TYPE_DISPLAY_MAP = dict(AuditLog.OPERATION_TYPE_CHOICES)


@dataclass(frozen=True)
class AuditLogFilters:
    """审计日志过滤条件（列表与导出共用）。"""

    app_label: str | None = None
    operation_type: str | None = None
    operator_jobcode: str | None = None
    record_code: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    def as_service_kwargs(self) -> dict[str, Any]:
        """转为 ``AuditLogQueryService.query_logs`` 的关键字参数。"""
        return {
            "app_label": self.app_label,
            "operation_type": self.operation_type,
            "operator_jobcode": self.operator_jobcode,
            "record_code": self.record_code,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class InvalidAuditLogFilters(ValueError):
    """查询参数非法。``str(exc)`` 即面向用户的中文错误文案。"""


def _parse_date(raw: str | None, field: str) -> tuple[datetime | None, str | None]:
    """解析单个 ``YYYY-MM-DD`` 参数。返回 ``(值, 错误信息)``。"""
    if not raw:
        return None, None
    try:
        return timezone.make_aware(datetime.strptime(raw, DATE_FORMAT)), None
    except ValueError:
        return None, f"{field} {DATE_FORMAT_ERROR}"


def _parse_time_range(days: str | None, start_date: str | None, end_date: str | None) -> tuple[datetime | None, datetime | None]:
    """解析时间条件：``days`` 与日期范围互斥。非法时抛 InvalidAuditLogFilters。"""
    if days:
        try:
            return timezone.now() - timedelta(days=int(days)), None
        except ValueError:
            raise InvalidAuditLogFilters("days 参数必须是整数") from None
    start_time, error = _parse_date(start_date, "start_date")
    if error:
        raise InvalidAuditLogFilters(error)
    end_time, error = _parse_date(end_date, "end_date")
    if error:
        raise InvalidAuditLogFilters(error)
    if end_time is not None:
        end_time = end_time.replace(hour=23, minute=59, second=59)
    return start_time, end_time


def _validate_operation_type(operation_type: str | None) -> None:
    """校验操作类型合法性，非法时抛 InvalidAuditLogFilters。"""
    if not operation_type:
        return
    valid_types = [choice[0] for choice in AuditLog.OPERATION_TYPE_CHOICES]
    if operation_type not in valid_types:
        raise InvalidAuditLogFilters(f"无效的操作类型: {operation_type}. 必须是以下之一: {valid_types}")


def parse_audit_log_filters(params: Mapping[str, Any]) -> AuditLogFilters:
    """解析并校验审计日志查询参数。

    Args:
        params: ``request.query_params`` 或等价映射。

    Returns:
        校验通过的 :class:`AuditLogFilters`。

    Raises:
        InvalidAuditLogFilters: 任一参数非法，异常消息为用户可读文案。
    """
    operation_type = params.get("operation_type")
    _validate_operation_type(operation_type)
    start_time, end_time = _parse_time_range(params.get("days"), params.get("start_date"), params.get("end_date"))
    return AuditLogFilters(
        app_label=params.get("app_label"),
        operation_type=operation_type,
        operator_jobcode=params.get("operator_jobcode"),
        record_code=params.get("record_code"),
        start_time=start_time,
        end_time=end_time,
    )
