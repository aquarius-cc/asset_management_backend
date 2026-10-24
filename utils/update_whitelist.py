"""字段白名单更新辅助(DR-1/DR-4: 白名单过滤块唯一实现, 报告 M-31)

同形面(5 处, 严格/宽松两形态):
- 严格形态(白名单内 setattr, 首个非白名单字段即拒 "不允许修改字段: {key}"):
  out_asset_service.update_outasset / recycle_asset_service.update_recycle_asset /
  unregistered services._apply_whitelist_edits
- 宽松形态(非白名单静默跳过, 不抛错):
  damaged_asset_service.update_damaged_asset(skip_none=True 软更新口径) /
  unregistered services.update_unregistered 的 before_data 审计快照
"""

from collections.abc import Collection, Mapping
from typing import Any

from core.exceptions import AppValidationError


def apply_whitelisted_updates(
    obj: Any,
    update_data: Mapping[str, Any],
    allowed_fields: Collection[str],
    *,
    error_code: str | None = None,
) -> None:
    """严格形态: 按白名单逐字段 setattr(原地更新), 非法字段即拒

    行为与原三处同形循环逐字等价: 保持 dict 插入序遍历、合法字段先 setattr、
    遇首个非法字段即抛、异常文案 "不允许修改字段: {key}" 不变。

    Args:
        obj: 目标模型实例(原地 setattr)
        update_data: 已校验的待更新字段
        allowed_fields: 字段白名单
        error_code: 拒绝时业务错误码; None 表示不传
            (AppValidationError 默认 error_code=None, unregistered 路径
            原实现即无 error_code, 行为零变更)

    Raises:
        AppValidationError: 存在非白名单字段时抛出
    """
    allowed = set(allowed_fields)
    for key, value in update_data.items():
        if key in allowed:
            setattr(obj, key, value)
        elif error_code is None:
            raise AppValidationError(detail=f"不允许修改字段: {key}")
        else:
            raise AppValidationError(detail=f"不允许修改字段: {key}", error_code=error_code)


def filter_whitelisted_fields(
    update_data: Mapping[str, Any],
    allowed_fields: Collection[str],
    *,
    skip_none: bool = False,
) -> dict[str, Any]:
    """宽松形态: 按白名单过滤字段(非白名单静默跳过), 返回新 dict(保持插入序)

    Args:
        update_data: 待过滤的更新字段
        allowed_fields: 字段白名单
        skip_none: True 时一并跳过 None 值(damaged 软更新口径)
    """
    allowed = set(allowed_fields)
    if skip_none:
        return {key: value for key, value in update_data.items() if key in allowed and value is not None}
    return {key: value for key, value in update_data.items() if key in allowed}
