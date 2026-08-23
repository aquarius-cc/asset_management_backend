"""
结构化 JSON 日志格式化器

满足 OC-2 可观测性契约:日志必须结构化(JSON),至少包含 time、level、trace_id、message、module。
"""

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any


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

        # 附加异常信息
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)
