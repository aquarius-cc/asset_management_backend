"""
结构化 JSON 日志格式化器

满足 OC-2 可观测性契约:日志必须结构化(JSON),至少包含 time、level、trace_id、message、module。
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any


# B1: 前端错误日志白名单。default-deny: 未登记 extra 字段一律不落盘。
_EXTRA_WHITELIST = frozenset(
    {
        "client_trace_id",
        "client_time",
        "frontend_module",
        "release",
        "env",
        "route",
        "frontend_context",
        "error_type",
        "error_message",
    }
)


class StructuredJSONFormatter(logging.Formatter):
    """
    将日志记录格式化为 JSON 结构。
    字段: time, level, logger, module, message, trace_id, extra
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "message": record.getMessage(),
        }

        # 透传 trace_id(从上下文变量或 extra 中获取)
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_entry["trace_id"] = trace_id

        for extra_key in _EXTRA_WHITELIST:
            if hasattr(record, extra_key):
                log_entry[extra_key] = getattr(record, extra_key)

        # 附加异常信息
        # 【A5/OC-3/BF-208】只留异常类型；message/traceback 一律不落盘（凭据/业务值泄露面）
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {"type": type(record.exc_info[1]).__name__}

        return json.dumps(log_entry, ensure_ascii=False, default=str)
