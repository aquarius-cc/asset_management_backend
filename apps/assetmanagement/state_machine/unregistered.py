"""
不在账资产专用状态转换(Mixin)

供 unregisteredasset 应用的 S1/S2/S3 场景使用。
仅供 AssetFSM 组合使用,禁止单独实例化或直接调用。
依赖 core.AssetFSM 提供的内部方法:_transition(本组方法多为特殊回退,部分绕过常规校验)。
"""

from typing import TYPE_CHECKING

from apps.assetmanagement.state_machine.constants import AssetState, InvalidTransitionError


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class UnregisteredTransitionsMixin:
    """不在账资产专用转换: unregistered_create_and_*、force_recycle_from_any"""

    # ===================================================================
    # 不在账资产专用状态转换(unregisteredasset 应用使用)
    # ===================================================================

    @classmethod
    def unregistered_create_and_recycle(cls, asset: "Asset") -> None:
        """
        未登记资产创建并回收: 无状态 → recycled_pending

        【业务场景】S1场景(实物有系统无)审批通过后,直接创建资产并入库待发放。
        此操作跳过常规的入库流程,直接设置状态为 recycled_pending。

        【使用方式】
            # 在 UnregisteredAssetService 中调用
            asset = Asset.objects.create(**asset_data)  # 状态默认为 in_store
            AssetFSM.unregistered_create_and_recycle(asset)  # 改为 recycled_pending
            asset.save()

        Args:
            asset: 新创建的资产实例(当前状态应为 in_store 或空)

        Raises:
            InvalidTransitionError: 资产已有非初始状态时抛出

        Example:
            >>> asset = Asset.objects.create(asset_code='AST001', asset_name='笔记本')
            >>> AssetFSM.unregistered_create_and_recycle(asset)
            >>> asset.asset_current_status
            'recycled_pending'
        """
        # 验证当前状态是否允许此操作
        current_status = asset.asset_current_status
        if current_status and current_status != AssetState.IN_STORE.value:
            raise InvalidTransitionError(f"未登记资产创建时状态必须为空白或'in_store',当前: {current_status}")
        # 直接设置为目标状态(跳过常规状态流转)
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value

    @classmethod
    def unregistered_create_and_damaged(cls, asset: "Asset") -> None:
        """
        未登记资产创建并待报废: 无状态 → damaged

        【业务场景】S1场景(实物有系统无)审批通过后,创建资产并直接进入待报废流程。
        此操作用于发现实物资产但决定报废的场景。

        【使用方式】
            # 在 UnregisteredAssetService 中调用
            asset = Asset.objects.create(**asset_data)
            AssetFSM.unregistered_create_and_damaged(asset)
            asset.save()
            # 然后创建 DamagedAsset 记录

        Args:
            asset: 新创建的资产实例(当前状态应为 in_store 或空)

        Raises:
            InvalidTransitionError: 资产已有非初始状态时抛出

        Example:
            >>> asset = Asset.objects.create(asset_code='AST001', asset_name='损坏设备')
            >>> AssetFSM.unregistered_create_and_damaged(asset)
            >>> asset.asset_current_status
            'damaged'
        """
        current_status = asset.asset_current_status
        if current_status and current_status != AssetState.IN_STORE.value:
            raise InvalidTransitionError(f"未登记资产创建时状态必须为空白或'in_store',当前: {current_status}")
        asset.asset_current_status = AssetState.DAMAGED.value

    @classmethod
    def force_recycle_from_any(cls, asset: "Asset") -> None:
        """
        强制回收: (任意非终态) → recycled_pending

        【业务场景】S2/S3场景使用,用于处理系统中有记录但流程异常的资产。
        - S2: 系统有资产记录但无出库记录,补建出库后直接回收
        - S3: 资产状态与实际不符,强制修正后回收

        【警告】此方法绕过常规状态流转校验,仅用于管理员审批授权后的特殊操作。
        禁止从终态(scrapped)转换。

        【使用方式】
            # 在 UnregisteredAssetService 中调用(需已审批授权)
            asset = Asset.objects.select_for_update().get(asset_code='AST001')
            AssetFSM.force_recycle_from_any(asset)
            asset.save()

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态为终态(scrapped)时抛出

        Example:
            >>> asset = Asset.objects.get(asset_code='AST001')
            >>> asset.asset_current_status
            'in_use'
            >>> AssetFSM.force_recycle_from_any(asset)
            >>> asset.asset_current_status
            'recycled_pending'
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current == AssetState.SCRAPPED:
            raise InvalidTransitionError("已报废资产无法强制回收,当前状态: scrapped")
        # 直接设置状态,跳过常规流转校验
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value
