"""
报废申请与审批相关状态转换(Mixin)

仅供 AssetFSM 组合使用,禁止单独实例化或直接调用。
依赖 core.AssetFSM 提供的内部方法:_transition。
"""

from typing import TYPE_CHECKING

from apps.assetmanagement.state_machine.constants import AssetState, InvalidTransitionError


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class ScrappingTransitionsMixin:
    """报废流程转换: damaged、cancel_damaged、approve 及各 reject_to_*"""

    # 审批拒绝的合法回退目标(对应各 reject_to_* 方法)
    # 【注意】scrapped(approve)虽然也在 VALID_TRANSITIONS[DAMAGED] 中,但不可作为拒绝目标
    # 【防误报】按 original_status 经 reject_to_original 回退,5 个目标状态已全量测试锚定
    # (test_damaged_asset_service.py: test_reject_to_broken / test_reject_to_lost /
    #  test_reject_returns_to_original_status 参数化 in_use/recycled_pending/repairing)；
    # reject_to_* 方法为 VALID_TRANSITIONS[DAMAGED] 的具名转换实现面(core._transition 与
    # reject_to_original 直接赋值、无方法名分派),保留为状态机转换表面,勿判死代码删除
    _REJECT_TARGETS: set[AssetState] = {
        AssetState.BROKEN,
        AssetState.LOST,
        AssetState.IN_USE,
        AssetState.RECYCLED_PENDING,
        AssetState.REPAIRING,
    }

    # ===================================================================
    # 报废相关状态转换
    # ===================================================================

    @classmethod
    def to_damaged(cls, asset: "Asset") -> None:
        """
        申请报废(to_damaged): (recycled_pending | broken | repairing | lost) → damaged
        资产转为待报废状态。
        【业务决策】in_use 不允许直接申请报废,须先回收再申请。
        触发时机: 创建待报废记录(DamagedAsset)后,由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许申请报废时抛出
        """
        cls._transition(asset, AssetState.DAMAGED)  # type: ignore[attr-defined]

    @classmethod
    def cancel_damaged(cls, asset: "Asset", original_status: str | None = None) -> None:
        """
        取消报废申请: damaged → original_status(缺失/非法时兜底 recycled_pending)
        用户主动取消待报废申请,资产回到申请前的状态(与 reject 回退目标一致)。
        【业务语义】与 reject 不同:cancel 是用户主动取消,reject 是审批人拒绝;
        但回退目标相同:均按申请前状态(original_status)回退。
        触发时机: 删除待报废记录后(用户主动操作)。
        Args:
            asset: 资产实例
            original_status: 进入 damaged 前的状态(从 DamagedAsset.original_status 获取)

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.DAMAGED:
            raise InvalidTransitionError(f"只有'待报废'状态的资产才能取消申请,当前状态: {current.value}")

        try:
            target = AssetState(original_status) if original_status else None
        except ValueError:
            target = None

        # 兜底: original_status 缺失或非法时,回退到 recycled_pending(可回收再分配)
        if target is None or target not in cls._REJECT_TARGETS:
            target = AssetState.RECYCLED_PENDING

        asset.asset_current_status = target.value

    # ===================================================================
    # 审批相关状态转换
    # ===================================================================

    @classmethod
    def approve(cls, asset: "Asset") -> None:
        """
        审批通过报废: damaged → scrapped
        待报废审批通过后,资产转为已报废状态(终态)。
        触发时机: 审批人通过待报废申请后,由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.SCRAPPED)  # type: ignore[attr-defined]

    @classmethod
    def reject_to_original(cls, asset: "Asset", original_status: str | None) -> None:
        """
        审批拒绝(按申请前状态回退): damaged → original_status

        【业务规则】审批拒绝后资产必须回退到申请前的状态(由 original_status 决定)。
        - 支持目标: broken / lost / in_use / recycled_pending / repairing
        - original_status 缺失或非法时,兜底回退到 recycled_pending(可回收再分配)
        - in_store 不可能成为原状态(无 in_store→damaged 路径),若出现按非法值兜底处理

        触发时机: 审批人拒绝待报废申请,由 DamagedAssetService 调用。

        Args:
            asset: 资产实例
            original_status: 进入 damaged 前的状态(DamagedAsset.original_status 字段值)

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.DAMAGED:
            raise InvalidTransitionError(f"只有'待报废'状态的资产才能审批拒绝,当前状态: {current.value}")

        try:
            target = AssetState(original_status) if original_status else None
        except ValueError:
            target = None

        if target is None or target not in cls._REJECT_TARGETS:
            target = AssetState.RECYCLED_PENDING

        asset.asset_current_status = target.value

    # 防御性方法: 业务不可达(damaged 入边不含 in_use), 详见下方 docstring
    @classmethod
    def reject_to_in_use(cls, asset: "Asset") -> None:
        """
        审批拒绝(在用): damaged → in_use

        【防御性方法】业务流程不可达:DAMAGED 的入边仅来自
        (recycled_pending|broken|repairing|lost),in_use 永不进入待报废状态,
        故 DamagedAsset.original_status 永不为 in_use(service 端权威记录,
        damaged_asset_service.create_damaged :46-49)。
        注意:transitions.py:63 中 damaged→in_use 仍是合法转换(转换表语义),
        仅是业务不可达;保留此方法以备未来放开"in_use 直接申请报废"。
        其余 reject_to_broken/lost/recycled_pending/repairing 虽同样不直接被
        service 调用,但其目标状态经 reject_to_original 统一入口可达,仅本方法需
        标记防御。

        触发时机: 审批人拒绝待报废申请,且原状态为 in_use 时(当前不可达)。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.IN_USE)  # type: ignore[attr-defined]

    @classmethod
    def reject_to_recycled_pending(cls, asset: "Asset") -> None:
        """
        审批拒绝(待发放): damaged → recycled_pending

        待报废审批被拒绝后,资产回到待发放状态。
        触发时机: 审批人拒绝待报废申请,且原状态为 recycled_pending 时。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)  # type: ignore[attr-defined]

    @classmethod
    def reject_to_repairing(cls, asset: "Asset") -> None:
        """
        审批拒绝(维修中): damaged → repairing

        待报废审批被拒绝后,资产回到维修中状态。
        触发时机: 审批人拒绝待报废申请,且原状态为 repairing 时。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.REPAIRING)  # type: ignore[attr-defined]
