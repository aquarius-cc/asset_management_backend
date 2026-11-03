"""审计快照敏感字段脱敏(OC-3 唯一实现, DR-1/DR-4)。

【为什么在写入收口】AuditLog 的唯一生产写入点是 GenericAuditService.log_operation。
在 view / adapter 各自脱敏会给同一规则造出第二实现, 且未来新增调用方必漏。
【为什么用字段名映射】快照是扁平业务字典, 字段名即语义; 用表驱动新增 PII 字段只改一处。
【与 BF-165 的关系】BF-165 的 WAI 判词仅限 API 响应体(三读路径); 落库快照的消费方只有
IsAuditorOrAdmin, 且手机号仍可经员工端点取得, 此处脱敏不推翻 BF-165 也不减少既有能力。
"""

from collections.abc import Callable, Mapping
from typing import Any

from utils.string_utils import mask_phone_number


#: 字段名 → 脱敏函数。新增 PII 字段只在此登记(DR-4: 复用 utils 既有实现)。
AUDIT_SENSITIVE_FIELD_MASKERS: dict[str, Callable[[str], str]] = {
    "employee_phone": mask_phone_number,
}


def mask_sensitive_snapshot(data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """递归脱敏审计快照中的敏感字段(幂等: 已脱敏值再脱敏结果不变)。

    仅按字段名精确匹配登记表; 未登记字段原样透传, 非 str 值不处理。
    """
    if not data:
        return dict(data) if data is not None else None
    masked: dict[str, Any] = {}
    for key, value in data.items():
        masker = AUDIT_SENSITIVE_FIELD_MASKERS.get(key)
        if masker is not None and isinstance(value, str) and value:
            masked[key] = masker(value)
        elif isinstance(value, Mapping):
            masked[key] = mask_sensitive_snapshot(value)
        else:
            masked[key] = value
    return masked
