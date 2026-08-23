"""
损坏/遗失/维修相关状态转换(Mixin)

仅供 AssetFSM 组合使用,禁止单独实例化或直接调用。
依赖 core.AssetFSM 提供的内部方法:_transition。
"""

from typing import TYPE_CHECKING

from apps.assetmanagement.state_machine.constants import AssetState


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class BrokenLostRepairTransitionsMixin:
    """损坏/遗失/维修转换: mark_broken、mark_lost、found_and_return、reject_to_broken/lost、repair*"""

    # ===================================================================
    # 损坏/遗失相关状态转换
    # ===================================================================

    @classmethod
    def mark_broken(cls, asset: "Asset") -> None:
        """
        标记损坏: (in_store|recycled_pending) → broken

        将资产标记为已损坏状态,直接生效无需审批。
        支持从在库或待发放状态直接标记。
        触发时机: 用户主动标记资产损坏。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许标记损坏时抛出
        """
        cls._transition(asset, AssetState.BROKEN)  # type: ignore[attr-defined]

    @classmethod
    def mark_lost(cls, asset: "Asset") -> None:
        """
        标记遗失: (in_store|recycled_pending) → lost

        将资产标记为已遗失状态,直接生效无需审批。
        支持从在库或待发放状态直接标记。
        触发时机: 用户主动标记资产遗失。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许标记遗失时抛出
        """
        cls._transition(asset, AssetState.LOST)  # type: ignore[attr-defined]

    @classmethod
    def found_and_return(cls, asset: "Asset") -> None:
        """
        找回入库: lost → recycled_pending

        遗失资产被找回后,转入待发放状态,等待再次分配。
        触发时机: 资产找回后,由 AssetService 调用。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 lost 时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)  # type: ignore[attr-defined]

    @classmethod
    def reject_to_broken(cls, asset: "Asset") -> None:
        """
        审批拒绝(损坏): damaged → broken

        待报废审批被拒绝后,资产回到损坏状态。
        触发时机: 审批人拒绝待报废申请,且原状态为 broken 时。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.BROKEN)  # type: ignore[attr-defined]

    @classmethod
    def reject_to_lost(cls, asset: "Asset") -> None:
        """
        审批拒绝(遗失): damaged → lost

        待报废审批被拒绝后,资产回到遗失状态。
        触发时机: 审批人拒绝待报废申请,且原状态为 lost 时。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.LOST)  # type: ignore[attr-defined]

    # ===================================================================
    # 维修相关状态转换
    # ===================================================================

    @classmethod
    def repair(cls, asset: "Asset") -> None:
        """
        送修: broken → repairing

        将损坏资产送修,进入维修中状态。
        触发时机: 用户提交送修申请。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 broken 时抛出
        """
        cls._transition(asset, AssetState.REPAIRING)  # type: ignore[attr-defined]

    @classmethod
    def repair_done(cls, asset: "Asset") -> None:
        """
        维修完成: repairing → recycled_pending

        维修完成后,资产转入待发放状态(已使用过的设备修好后再次投入发放)。
        触发时机: 维修完成确认。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 repairing 时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)  # type: ignore[attr-defined]

    @classmethod
    def repair_failed(cls, asset: "Asset") -> None:
        """
        维修失败: repairing → damaged

        维修失败后资产进入待报废状态。
        触发时机: 维修失败确认。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 repairing 时抛出
        """
        cls._transition(asset, AssetState.DAMAGED)  # type: ignore[attr-defined]
