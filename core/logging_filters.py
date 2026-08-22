"""
日志过滤器

将 RequestContextMiddleware 存储的 trace_id 注入到日志记录中,
实现 OC-1 可观测性契约:每个请求的 trace_id 在整个调用链透传到日志。
"""

import logging

from core.request_context import get_current_trace_id


class TraceIDFilter(logging.Filter):
    """
    自动注入 trace_id 到日志记录

    从 thread-local 获取当前请求的 trace_id,
    注入到 logrecord 的 trace_id 字段,
    供 StructuredJSONFormatter 输出到 JSON 日志。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_current_trace_id() or "-"
        return True
