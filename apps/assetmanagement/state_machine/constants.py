"""
资产状态机常量定义

定义资产全生命周期的所有状态枚举和非法转换异常。
状态流转图:
```
主路径:  in_store ──outasset──→ in_use ──recycle──→ recycled_pending ──to_damaged──→ damaged ──approve──→ scrapped(终态)
         recycled_pending ──outasset──→ in_use(再次出库)
         damaged ──reject──→ broken/lost/in_use/recycled_pending/repairing (审批拒绝,按original_status回退)
         damaged ──cancel──→ recycled_pending(用户取消)

损坏/遗失/维修路径:
         in_store / in_use / recycled_pending ──mark_broken──→ broken
         in_store / in_use / recycled_pending ──mark_lost──→ lost
         broken ──repair──→ repairing ──repair_done──→ recycled_pending
         repairing ──repair_failed──→ damaged
         lost ──found_and_return──→ recycled_pending
         lost ──to_damaged──→ damaged
```

终态: scrapped(已报废,无转出)
"""

from enum import Enum


class AssetState(Enum):
    """
    资产状态枚举
    定义资产全生命周期中的所有状态。
    与 Asset.asset_current_status 字段值一一对应。

    Attributes:
        IN_STORE: 在库 - 资产在仓库中,未分配使用(首次入库的新资产)
        IN_USE: 在用 - 资产已被领用/出库,正在使用中
        RECYCLED_PENDING: 已回收待发放 - 资产已回收,等待下次分配
        BROKEN: 已损坏 - 资产存在但已损坏
        REPAIRING: 维修中 - 资产已送修,等待维修结果
        LOST: 已遗失 - 资产无法找到
        DAMAGED: 待报废 - 资产损坏,等待报废审批
        SCRAPPED: 已报废 - 审批通过,资产报废(终态)
    """

    IN_STORE = "in_store"
    IN_USE = "in_use"
    RECYCLED_PENDING = "recycled_pending"
    BROKEN = "broken"
    REPAIRING = "repairing"
    LOST = "lost"
    DAMAGED = "damaged"
    SCRAPPED = "scrapped"

    @classmethod
    def from_string(cls, value: str) -> "AssetState":
        """
        从字符串转换为枚举值
        Args:
            value: 状态字符串(如 'in_store')

        Returns:
            AssetState: 对应的枚举值

        Raises:
            InvalidTransitionError: 字符串不是合法的状态值时抛出
        """
        try:
            return cls(value)
        except ValueError:
            raise InvalidTransitionError(f"未知的状态值: {value}")


class InvalidTransitionError(Exception):
    """
    非法状态转换异常
    当尝试执行不允许的状态转换时抛出。
    Service层应捕获此异常并转换为 AppValidationError。
    """

    pass
