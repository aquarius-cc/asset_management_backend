"""
审计日志辅助函数

统一失败收口薄委托(批次 2 / M-02): 异常处理骨架收敛到
core.audit_failure.safe_audit_call(DR-1 唯一实现, 分渠道计数 + 脱敏日志),
本模块仅保留 error_context → context 映射; 调用点签名零改动。
"""

from collections.abc import Callable
from typing import Any

from core.audit_failure import safe_audit_call


def safe_audit_log(fn: Callable[..., Any], *, error_context: str, **kwargs: Any) -> None:
    """
    安全执行审计日志记录函数,失败计数 + 脱敏日志(core.audit_failure 单实现)。

    Args:
        fn: 要执行的审计函数（通常是 GenericAuditService 的方法）
        error_context: 操作描述,作为失败日志 context（不传递给 fn）
        kwargs: 传递给 fn 的关键字参数
    """
    safe_audit_call(fn, channel="generic_audit_dispatch", context=error_context, **kwargs)
