"""
审计日志辅助函数

为各模块审计适配器提供统一的 try/except + 日志包装,
消除重复的异常处理骨架代码（DR-1 收敛）。
"""

import logging
from collections.abc import Callable
from typing import Any


logger = logging.getLogger(__name__)


def safe_audit_log(fn: Callable[..., Any], *, error_context: str, **kwargs: Any) -> None:
    """
    安全执行审计日志记录函数,统一捕获异常并记录日志。

    Args:
        fn: 要执行的审计函数（通常是 GenericAuditService 的方法）
        error_context: 操作描述,用于错误日志（不传递给 fn）
        kwargs: 传递给 fn 的关键字参数
    """
    try:
        fn(**kwargs)
    except Exception as e:
        logger.error(f"{error_context}失败: {e}", exc_info=True)
