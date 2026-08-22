"""
出库/回收相关状态转换(Mixin)

仅供 AssetFSM 组合使用,禁止单独实例化或直接调用。
依赖 core.AssetFSM 提供的内部方法:_transition。
"""

from typing import TYPE_CHECKING

from apps.assetmanagement.state_machine.constants import AssetState, InvalidTransitionError

if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class OutRecycleTransitionsMixin:
    """出库/回冲类转换: outasset、cancel_outasset、recycle、cancel_recycle"""

    # ===================================================================
    # 出库相关状态转换
    # ===================================================================

    @classmethod
    def outasset(cls, asset: "Asset") -> None:
        """
        出库: (in_store | recycled_pending) → in_use
        资产从仓库或待发放状态转为在用状态。
        支持首次出库和再次出库两种场景。
        触发时机: 创建出库记录(OutAsset)后,由 OutAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许出库时抛出

        Example:
            >>> asset = Asset.objects.get(asset_code='A001')
            >>> AssetFSM.outasset(asset)
            >>> asset.asset_current_status
            'in_use'
        """
        cls._transition(asset, AssetState.IN_USE)

    @classmethod
    def cancel_outasset(cls, asset: "Asset", previous_status: str) -> None:
        """
        取消出库: in_use → previous_status

        删除出库记录后,根据出库前的来源状态回退资产状态。
        【业务规则】从 in_store 出库的回到 in_store,从 recycled_pending 出库的回到 recycled_pending。
        【注意】此为特殊回退操作,不在 VALID_TRANSITIONS 中定义。

        触发时机: 删除出库记录后,由 OutAssetService 调用。

        Args:
            asset: 资产实例
            previous_status: 出库前的资产状态字符串('in_store' 或 'recycled_pending')

        Raises:
            InvalidTransitionError: 当前状态不是 in_use 或 previous_status 不合法时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.IN_USE:
            raise InvalidTransitionError(f"只有'在用'状态的资产才能取消出库,当前状态: {current.value}")

        # 验证并设置目标状态
        target = AssetState.from_string(previous_status)
        if target not in (AssetState.IN_STORE, AssetState.RECYCLED_PENDING):
            raise InvalidTransitionError(
                f"取消出库的目标状态必须是'in_store'或'recycled_pending',收到: {previous_status}"
            )

        asset.asset_current_status = target.value

    # ===================================================================
    # 回收相关状态转换
    # ===================================================================

    @classmethod
    def recycle(cls, asset: "Asset") -> None:
        """
        回收: in_use → recycled_pending
        资产从在用状态转为已回收待发放状态。
        触发时机: 创建回收记录(RecycleAsset)后,由 RecycleAssetService 调用。
        Args:
            asset: 资产实例
        Raises:
            InvalidTransitionError: 当前状态不允许回收时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)

    @classmethod
    def cancel_recycle(cls, asset: "Asset") -> None:
        """
        取消回收: recycled_pending → in_use
        删除回收记录后,恢复资产到在用状态。
        【注意】此为特殊回退操作,不在 VALID_TRANSITIONS 中定义。
        触发时机: 删除回收记录后。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 recycled_pending 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.RECYCLED_PENDING:
            raise InvalidTransitionError(f"只有'已回收待发放'状态的资产才能取消回收,当前状态: {current.value}")
        asset.asset_current_status = AssetState.IN_USE.value
