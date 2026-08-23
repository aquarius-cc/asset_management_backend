"""
不在账资产状态机适配器

该模块封装对 assetmanagement.state_machine.AssetFSM 的调用，
为 unregisteredasset 应用提供语义化的状态转换方法。

【设计目的】
1. 解耦：unregisteredasset 不直接依赖 AssetFSM 的具体实现
2. 语义化：提供符合不在账资产业务场景的方法名
3. 扩展性：可在适配层添加额外的业务校验或日志

【AGENTS 规范 - 适配器模式】
- 单一职责：仅封装状态机调用，不处理业务逻辑
- 延迟导入：方法内部导入 AssetFSM，避免模块级循环依赖
- 异常透传：保持 InvalidTransitionError 异常向上传递

【使用方式】
    from .state_machine_adapter import UnregisteredAssetStateAdapter

    # S1场景：创建资产并回收
    adapter = UnregisteredAssetStateAdapter()
    adapter.create_and_recycle(asset)

    # S2/S3场景：强制回收
    adapter.force_recycle(asset)
"""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class UnregisteredAssetStateAdapter:
    """
    不在账资产状态适配器

    封装对 AssetFSM 的调用，提供符合不在账资产业务语义的方法。
    所有方法都是静态方法，无需实例化即可使用。

    【方法映射】
    - create_and_recycle() → AssetFSM.unregistered_create_and_recycle()
    - create_and_damaged() → AssetFSM.unregistered_create_and_damaged()
    - force_recycle() → AssetFSM.force_recycle_from_any()

    【异常处理】
    所有方法保持 AssetFSM 的异常行为，非法状态转换时抛出 InvalidTransitionError。
    Service 层应捕获此异常并转换为 AppValidationError。

    Example:
        >>> from apps.assetmanagement.models import Asset
        >>> from apps.unregisteredasset.state_machine_adapter import UnregisteredAssetStateAdapter
        >>>
        >>> asset = Asset.objects.create(asset_code='AST001', asset_name='笔记本')
        >>> adapter = UnregisteredAssetStateAdapter()
        >>> adapter.create_and_recycle(asset)
        >>> asset.asset_current_status
        'recycled_pending'
    """

    @staticmethod
    def create_and_recycle(asset: 'Asset') -> None:
        """
        S1场景：创建资产并回收

        将新创建的资产状态设置为 recycled_pending（已回收待发放）。
        用于不在账资产审批通过后直接入库待发放的场景。

        【调用链】
        此方法 → AssetFSM.unregistered_create_and_recycle()

        Args:
            asset: 新创建的资产实例（状态应为 in_store 或空）

        Raises:
            InvalidTransitionError: 资产已有非初始状态时抛出

        Example:
            >>> asset = Asset.objects.create(asset_code='AST001', asset_name='笔记本')
            >>> UnregisteredAssetStateAdapter.create_and_recycle(asset)
            >>> asset.asset_current_status
            'recycled_pending'
        """
        # 延迟导入避免循环依赖
        from apps.assetmanagement.state_machine import AssetFSM
        AssetFSM.unregistered_create_and_recycle(asset)

    @staticmethod
    def create_and_damaged(asset: 'Asset') -> None:
        """
        S1场景：创建资产并待报废

        将新创建的资产状态设置为 damaged（待报废）。
        用于发现实物资产但决定报废的场景。

        【调用链】
        此方法 → AssetFSM.unregistered_create_and_damaged()

        Args:
            asset: 新创建的资产实例（状态应为 in_store 或空）

        Raises:
            InvalidTransitionError: 资产已有非初始状态时抛出

        Example:
            >>> asset = Asset.objects.create(asset_code='AST001', asset_name='损坏设备')
            >>> UnregisteredAssetStateAdapter.create_and_damaged(asset)
            >>> asset.asset_current_status
            'damaged'
        """
        from apps.assetmanagement.state_machine import AssetFSM
        AssetFSM.unregistered_create_and_damaged(asset)

    @staticmethod
    def force_recycle(asset: 'Asset') -> None:
        """
        S2/S3场景：强制回收

        将资产状态强制设置为 recycled_pending，跳过常规状态流转校验。
        仅用于管理员审批授权后的特殊操作。

        【适用场景】
        - S2: 系统有资产记录但无出库记录，补建出库后直接回收
        - S3: 资产状态与实际不符，强制修正后回收

        【调用链】
        此方法 → AssetFSM.force_recycle_from_any()

        【安全限制】
        禁止从终态（scrapped）强制回收。

        Args:
            asset: 资产实例（任意非终态）

        Raises:
            InvalidTransitionError: 当前状态为 scrapped 时抛出

        Example:
            >>> asset = Asset.objects.get(asset_code='AST001')
            >>> asset.asset_current_status
            'in_use'
            >>> UnregisteredAssetStateAdapter.force_recycle(asset)
            >>> asset.asset_current_status
            'recycled_pending'
        """
        from apps.assetmanagement.state_machine import AssetFSM
        AssetFSM.force_recycle_from_any(asset)
