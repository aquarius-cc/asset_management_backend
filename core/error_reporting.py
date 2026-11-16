"""异常日志口径统一出口（OC-3 / M-19「只记类型」）

core/audit_failure.py 明文：formatter 会把 exc_info 的 traceback 完整落盘，
DB/Redis 凭据可随连接串泄露；IntegrityError 文本常带 `DETAIL: Key (col)=(value)`
业务字段值。故日志口径统一为：只记 exception_type，不落 exc_info / str(exc)。

三级处置口径（本模块为唯一收敛点）：
- 一级（审计写失败/通知失败/异常出口/凭证近邻）：去 exc_info，只记 exception_type
- 二级（业务异常含业务值风险：批量/CRUD 通用层 str(e)）：同上
- 三级（原样保留）：仅限无敏感面且堆栈必要的调试路径——当前生产路径零命中
"""

from __future__ import annotations

import logging


def exception_type(exc: BaseException) -> str:
    """[OC-3] 日志安全口径：只取异常类型名，禁止 str(exc)/traceback 落盘"""
    return type(exc).__name__


def capture_exception_safe(exc: BaseException) -> None:
    """吞异常路径的 Sentry 捕获唯一出口（替代日志侧 exc_info 堆栈落盘）。

    懒加载 sentry_sdk：未安装/未初始化时静默 no-op（DSN 未配置属合法部署形态）；
    遥测自身故障不得放大为主流程异常。生产排障链 = Sentry 事件 + 日志 exception_type
    + X-Request-ID↔trace_id 双端互查（M-RC-11）。
    """
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def log_channel_failure(
    logger: logging.Logger,
    channel: str,
    exc: BaseException,
    *,
    message: str,
    level: int = logging.ERROR,
    **context: object,
) -> None:
    """审计/通知失败类日志唯一出口。

    固定写法：message + context（调用方提供的无敏感字段）+ exception_type；
    禁止 exc_info / str(exc)。用法::

        log_channel_failure(logger, "generic_audit_log", e,
                             message="通用审计日志记录失败", operator=jobcode)
    """
    logger.log(
        level,
        "%s (channel=%s, exception_type=%s%s)",
        message,
        channel,
        exception_type(exc),
        "".join(f", {k}={v}" for k, v in context.items()) if context else "",
    )
