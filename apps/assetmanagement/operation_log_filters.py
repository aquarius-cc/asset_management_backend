"""资产操作日志查询参数解析与校验。

【为什么要独立模块】
操作日志的**列表**与**导出**两个端点共用同一套过滤参数（资产编码、
操作类型、操作人、日期范围、days）。若各自解析即构成重复实现（DR-1），
故抽取为 :func:`parse_operation_log_filters` 单一入口。

放在独立模块而非 ``operation_log_views.py``，也是为了控制后者文件规模
（DR-5 <= 500 行）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.assetmanagement.models import AssetOperationLog


__all__ = [
    "OPERATION_TYPE_DISPLAY_MAP",
    "InvalidOperationLogFilters",
    "OperationLogFilters",
    "parse_operation_log_filters",
]

DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_ERROR = "格式错误,应为 YYYY-MM-DD"

#: 操作类型取值 -> 中文标签，用于导出列的 display_map（单一事实来源）
OPERATION_TYPE_DISPLAY_MAP = dict(AssetOperationLog.OperationType.choices)


@dataclass(frozen=True)
class OperationLogFilters:
    """操作日志过滤条件（列表与导出共用）。"""

    asset_code: str | None = None
    operation_type: str | None = None
    operator_jobcode: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    def as_selector_kwargs(self) -> dict[str, Any]:
        """转为 ``OperationLogSelector`` 的关键字参数。"""
        return {
            "asset_code": self.asset_code,
            "operation_type": self.operation_type,
            "operator_jobcode": self.operator_jobcode,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


def _parse_date(raw: str | None, field: str) -> tuple[datetime | None, str | None]:
    """解析单个 ``YYYY-MM-DD`` 参数。返回 ``(值, 错误信息)``。"""
    if not raw:
        return None, None
    try:
        return timezone.make_aware(datetime.strptime(raw, DATE_FORMAT)), None
    except ValueError:
        return None, f"{field} {DATE_FORMAT_ERROR}"


def parse_time_range(
    days: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime | None, datetime | None, str | None]:
    """解析时间条件：``days`` 与日期范围互斥。返回 ``(start, end, 错误信息)``。

    ``end_date`` 取当天 23:59:59，使闭区间覆盖完整当日。
    """
    if days:
        try:
            return timezone.now() - timedelta(days=int(days)), None, None
        except ValueError:
            return None, None, "days 参数必须是整数"

    start_time, error = _parse_date(start_date, "start_date")
    if error:
        return None, None, error
    end_time, error = _parse_date(end_date, "end_date")
    if error:
        return None, None, error
    if end_time is not None:
        end_time = end_time.replace(hour=23, minute=59, second=59)
    return start_time, end_time, None


def _validate_operation_type(operation_type: str | None) -> str | None:
    """校验操作类型合法性，返回错误信息（合法时返回 None）。"""
    if not operation_type:
        return None
    valid_types = [choice[0] for choice in AssetOperationLog.OPERATION_TYPE_CHOICES]
    if operation_type not in valid_types:
        return f"无效的操作类型: {operation_type}. 必须是以下之一: {valid_types}"
    return None


class InvalidOperationLogFilters(ValueError):
    """查询参数非法。``str(exc)`` 即面向用户的中文错误文案。"""


def parse_operation_log_filters(params: Mapping[str, Any]) -> OperationLogFilters:
    """解析并校验操作日志查询参数。

    Args:
        params: ``request.query_params`` 或等价映射。

    Returns:
        校验通过的 :class:`OperationLogFilters`。

    Raises:
        InvalidOperationLogFilters: 任一参数非法，异常消息为用户可读文案。

    【为何用异常而非 ``(filters, error)`` 二元组】
    二元组形式无法在类型层表达"有 error 则 filters 必为 None"的关联
    不变量，调用方 ``filters.as_selector_kwargs()`` 必然触发 mypy
    ``union-attr``（CI ``mypy . --strict`` 门禁）。异常使成功路径的返回
    类型精确为非 Optional，无需断言或 cast。
    """
    error = _validate_operation_type(params.get("operation_type"))
    if error:
        raise InvalidOperationLogFilters(error)

    start_time, end_time, error = parse_time_range(
        params.get("days"), params.get("start_date"), params.get("end_date")
    )
    if error:
        raise InvalidOperationLogFilters(error)

    return OperationLogFilters(
        asset_code=params.get("asset_code"),
        operation_type=params.get("operation_type"),
        operator_jobcode=params.get("operator_jobcode"),
        start_time=start_time,
        end_time=end_time,
    )
