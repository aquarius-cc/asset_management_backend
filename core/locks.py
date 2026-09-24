"""
行锁超时统一收敛助手 (DR-1)

将对已 select_for_update 的行"锁超时 → 409"的错误映射收敛为单一实现,
消除 repair/out_asset 等 Service 中重复的 try/except OperationalError 块。

约束:
- 本模块位于 core/,禁止 import apps 模型(防 core→apps 循环依赖)。
  guard_lock_conflict / lock_row_or_409 只接收调用方预先构造好的(已 select_for_update)queryset。
- 常量 ASSET_LOCKED 为"资产锁定/锁超时"业务码的唯一事实来源。
"""

from collections.abc import Callable

from django.db import OperationalError
from django.db.models import Model, QuerySet

from core.exceptions import ResourceConflictError


# 资产行锁冲突业务码(409) 的唯一事实来源
ASSET_LOCKED = "ASSET_LOCKED"


def guard_lock_conflict[T](fn: Callable[[], T]) -> T:
    """执行 fn,将行锁超时统一映射为 409(唯一映射实现,DR-1)

    fn 通常为包着 `select_for_update().get/first` 的 lambda;
    返回 fn 的结果(保型返回 T,可适配 get 的 T 与 first 的 T | None)。

    Raises:
        ResourceConflictError: 数据库行锁超时(错误消息含 lock,如 "database is locked")
    """
    try:
        return fn()
    except OperationalError as e:
        if "lock" in str(e).lower():
            raise ResourceConflictError(
                detail="资产被其他用户锁定,请稍后重试",
                error_code=ASSET_LOCKED,
            ) from e
        raise


def lock_row_or_409[T: Model](qs: QuerySet[T], **filters: object) -> T:
    """对预先 select_for_update() 的查询执行 get(),锁超时统一映射为 409

    Args:
        qs: 已施加 select_for_update() 的查询集(由调用方构造,本函数不负责加锁)
        **filters: 传给 queryset.get() 的过滤条件(如 asset_code=asset_code)

    Raises:
        ResourceConflictError: 数据库行锁超时(错误消息含 lock,如 "database is locked")
    """
    return guard_lock_conflict(lambda: qs.get(**filters))
