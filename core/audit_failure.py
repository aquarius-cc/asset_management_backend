"""审计失败可观测事件唯一收口(DR-1): 指标 + 脱敏结构化日志。

渠道表(批次 2 / M-01+M-02, 与 core/metrics.py 注释、backend-business-rules.md §3 约束 8 同步):
- asset_operation_log   AuditLogger._safe_log 写失败(渠道/指标语义不动；非 strict 新增 capture_exception_safe 报 Sentry，strict 上抛由全局出口捕获，避免双报；单次失败仍只计一处)
- generic_audit_log     GenericAuditService on_commit 写库失败(既有, 不动)
- unregistered_adapter / unregistered_safe_call  未登记资产域(既有, 本批不动)
- asset_audit_decorator audit_operation 装饰器调度失败(新增, 与 asset_operation_log 互斥)
- generic_audit_dispatch  safe_audit_call 调度层失败, auth+usermanagement 共用(新增,
  与 generic_audit_log 互斥——写库异常在 _write_audit 内已吞并计数, 外层仅接闭包外异常)

口径: 单次失败只计一处(§3 约束 8); 同渠道多来源靠日志 context 区分
(认证域三处 context 带「认证域-」前缀, usermanagement 保持既有 error_context)。
"""

import logging
from collections.abc import Callable
from typing import Any

from core.metrics import AUDIT_WRITE_FAILED


logger = logging.getLogger("audit.failure")


def record_audit_failure(*, channel: str, context: str, exc: Exception) -> None:
    """计数 + ERROR 日志; 任何情况下不得向调用方抛异常(保住容错契约)。

    不取 str(exc)、不传 exc_info: StructuredJSONFormatter 会把异常对象与
    traceback 完整落盘, DB/Redis 连接串与凭据由此泄露(OC-3/SC-1)。
    """
    try:
        AUDIT_WRITE_FAILED.labels(channel=channel).inc()
    except Exception:
        # 指标自身失败不得放大为主流程 500
        logger.error("审计失败指标自增异常(context=%s)", context)
    logger.error("审计记录失败(context=%s, exception_type=%s)", context, type(exc).__name__)


def safe_audit_call(fn: Callable[..., Any], *, channel: str, context: str, **kwargs: Any) -> None:
    """执行 fn 并在失败时走 record_audit_failure 收口; 不向调用方传播异常。"""
    try:
        fn(**kwargs)
    except Exception as exc:
        record_audit_failure(channel=channel, context=context, exc=exc)
