"""
资产状态机核心实现
【AGENTS 规范 - 状态机解耦】
集中管理资产状态流转规则，每个状态转换是独立方法。
核心设计:
- AssetState: 状态枚举定义
- AssetFSM: 状态转换方法集合
- InvalidTransitionError: 非法转换异常
状态流转图:
```
in_store ──outasset──→ in_use ──recycle──→ recycled_pending ──damaged──→ damaged ──approve──→ scrapped
                          ↑                      │                      │
                          │                      │                      │
                          └──────outasset────────┘                      │
                                                 │                      │
                                                 └──── reject/cancel────┘

终态: scrapped（已报废，无转出）
```

职责边界:
- 【状态机负责】只修改 asset.asset_current_status 字段
- 【Service负责】事务控制、并发锁、其他字段更新、日志记录
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class AssetState(Enum):
    """
    资产状态枚举
    定义资产全生命周期中的所有状态。
    与 Asset.asset_current_status 字段值一一对应。

    Attributes:
        IN_STORE: 在库 - 资产在仓库中，未分配使用
        IN_USE: 在用 - 资产已被领用/出库，正在使用中
        RECYCLED_PENDING: 已回收待发放 - 资产已回收，等待下次分配
        DAMAGED: 待报废 - 资产损坏，等待报废审批
        SCRAPPED: 已报废 - 审批通过，资产报废（终态）
    """
    IN_STORE = 'in_store'
    IN_USE = 'in_use'
    RECYCLED_PENDING = 'recycled_pending'
    DAMAGED = 'damaged'
    SCRAPPED = 'scrapped'

    @classmethod
    def from_string(cls, value: str) -> 'AssetState':
        """
        从字符串转换为枚举值
        Args:
            value: 状态字符串（如 'in_store'）

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


class AssetFSM:
    """
    资产有限状态机
    【设计原则 - AGENTS规范】
    - 单一职责: 只负责状态字段(asset_current_status)变更，不处理其他字段
    - 显式调用: 每个状态转换是独立方法，调用意图清晰可见
    - 契约驱动: 通过类型注解和文档明确接口契约
    - 事务边界: 状态机不处理事务和并发锁，由调用方(Service)控制
    【使用方式】
        # Service层控制事务和并发
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            AssetFSM.outasset(asset)  # 执行状态转换（只修改内存中的值）
            asset.save()              # 持久化到数据库

    【注意】
    - 所有方法只修改 asset.asset_current_status，不调用 save()
    - 所有方法不处理事务，由调用方通过 @transaction.atomic 控制
    - 所有方法不处理并发锁，由调用方通过 select_for_update() 控制
    """

    # ===================================================================
    # 状态转换规则定义
    # ===================================================================

    # 定义允许的转换: {当前状态: {目标状态: 转换名称}}
    #
    # 【完整状态流转图】
    #
    #   in_store ──outasset──→ in_use ──recycle──→ recycled_pending ──damaged──→ damaged ──approve──→ scrapped(终态)
    #                             ↑                      │                      │
    #                             │                      │                      │
    #                             └──────outasset────────┘                      │
    #                                                    │                      │
    #                                                    └──── reject/cancel────┘
    #
    # 【业务规则】
    # - reject（审批拒绝）和 cancel（用户取消）都回到 recycled_pending
    # - 保留独立方法以区分业务语义，便于日志追踪
    # - scrapped 为终态，不允许任何转出
    #
    _TRANSITIONS: dict = {
        # 在库 → 在用（首次出库）
        AssetState.IN_STORE: {
            AssetState.IN_USE: 'outasset',
        },
        # 在用 → 待发放（回收）或 → 待报废（直接报废申请）
        AssetState.IN_USE: {
            AssetState.RECYCLED_PENDING: 'recycle',
            AssetState.DAMAGED: 'damaged',
        },
        # 待发放 → 在用（再次出库）或 → 待报废（报废申请）
        AssetState.RECYCLED_PENDING: {
            AssetState.IN_USE: 'outasset',
            AssetState.DAMAGED: 'damaged',
        },
        # 待报废 → 已报废（审批通过）或 → 待发放（审批拒绝）
        AssetState.DAMAGED: {
            AssetState.SCRAPPED: 'approve',
            AssetState.RECYCLED_PENDING: 'reject',
        },
        # 已报废 - 终态，无转出
        AssetState.SCRAPPED: {},
    }

    # ===================================================================
    # 内部方法
    # ===================================================================

    @classmethod
    def can_transition(cls, asset: 'Asset', target_state: AssetState) -> bool:
        """
        检查是否可以执行状态转换（不修改状态）
        Args:
            asset: 资产实例（通过 asset.asset_current_status 获取当前状态）
            target_state: 目标状态枚举值

        Returns:
            bool: 是否允许执行该转换
        """
        try:
            current = AssetState.from_string(asset.asset_current_status)
            return target_state in cls._TRANSITIONS.get(current, {})
        except InvalidTransitionError:
            return False

    @classmethod
    def _validate_transition(cls, asset: 'Asset', target_state: AssetState) -> None:
        """
        验证状态转换合法性（不修改状态）
        Args:
            asset: 资产实例
            target_state: 目标状态枚举值

        Raises:
            InvalidTransitionError: 转换不合法时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)

        if not cls.can_transition(asset, target_state):
            raise InvalidTransitionError(
                f"非法状态转换: {current.value} → {target_state.value}"
            )

    @classmethod
    def _transition(cls, asset: 'Asset', target_state: AssetState) -> None:
        """
        执行状态转换（内部方法）
        验证合法性后修改 asset.asset_current_status。
        【注意】不调用 save()，由调用方控制持久化时机。

        Args:
            asset: 资产实例
            target_state: 目标状态枚举值

        Raises:
            InvalidTransitionError: 转换不合法时抛出
        """
        cls._validate_transition(asset, target_state)
        asset.asset_current_status = target_state.value

    # ===================================================================
    # 出库相关状态转换
    # ===================================================================

    @classmethod
    def outasset(cls, asset: 'Asset') -> None:
        """
        出库: (in_store | recycled_pending) → in_use
        资产从仓库或待发放状态转为在用状态。
        支持首次出库和再次出库两种场景。
        触发时机: 创建出库记录(OutAsset)后，由 OutAssetService 调用。
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
    def cancel_outasset(cls, asset: 'Asset', previous_status: str) -> None:
        """
        取消出库: in_use → previous_status

        删除出库记录后，根据出库前的来源状态回退资产状态。
        【业务规则】从 in_store 出库的回到 in_store，从 recycled_pending 出库的回到 recycled_pending。
        【注意】此为特殊回退操作，不在 _TRANSITIONS 中定义。

        触发时机: 删除出库记录后，由 OutAssetService 调用。

        Args:
            asset: 资产实例
            previous_status: 出库前的资产状态字符串（'in_store' 或 'recycled_pending'）

        Raises:
            InvalidTransitionError: 当前状态不是 in_use 或 previous_status 不合法时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.IN_USE:
            raise InvalidTransitionError(
                f"只有'在用'状态的资产才能取消出库，当前状态: {current.value}"
            )

        # 验证并设置目标状态
        target = AssetState.from_string(previous_status)
        if target not in (AssetState.IN_STORE, AssetState.RECYCLED_PENDING):
            raise InvalidTransitionError(
                f"取消出库的目标状态必须是'in_store'或'recycled_pending'，收到: {previous_status}"
            )

        asset.asset_current_status = target.value

    # ===================================================================
    # 回收相关状态转换
    # ===================================================================

    @classmethod
    def recycle(cls, asset: 'Asset') -> None:
        """
        回收: in_use → recycled_pending
        资产从在用状态转为已回收待发放状态。
        触发时机: 创建回收记录(RecycleAsset)后，由 RecycleAssetService 调用。
        Args:
            asset: 资产实例
        Raises:
            InvalidTransitionError: 当前状态不允许回收时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)

    @classmethod
    def cancel_recycle(cls, asset: 'Asset') -> None:
        """
        取消回收: recycled_pending → in_use
        删除回收记录后，恢复资产到在用状态。
        【注意】此为特殊回退操作，不在 _TRANSITIONS 中定义。
        触发时机: 删除回收记录后。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 recycled_pending 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.RECYCLED_PENDING:
            raise InvalidTransitionError(
                f"只有'已回收待发放'状态的资产才能取消回收，当前状态: {current.value}"
            )
        asset.asset_current_status = AssetState.IN_USE.value

    @classmethod
    def restock(cls, asset: 'Asset') -> None:
        """
        重新入库: recycled_pending → in_store
        资产从待发放状态重新入库。
        【注意】当前状态流转图中未定义此转换，保留方法以备扩展。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许入库时抛出
        """
        cls._transition(asset, AssetState.IN_STORE)

    # ===================================================================
    # 报废相关状态转换
    # ===================================================================

    @classmethod
    def damaged(cls, asset: 'Asset') -> None:
        """
        申请报废: (in_use | recycled_pending) → damaged
        资产从在用或待发放状态转为待报废状态。
        支持使用中和待发放两种场景的报废申请。
        触发时机: 创建待报废记录(DamagedAsset)后，由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许申请报废时抛出
        """
        cls._transition(asset, AssetState.DAMAGED)

    @classmethod
    def cancel_damaged(cls, asset: 'Asset') -> None:
        """
        取消报废申请: damaged → recycled_pending
        用户主动取消待报废申请，资产回到待发放状态。
        【业务语义】与 reject 不同：cancel 是用户主动取消，reject 是审批人拒绝。
        触发时机: 删除待报废记录后（用户主动操作）。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.DAMAGED:
            raise InvalidTransitionError(
                f"只有'待报废'状态的资产才能取消申请，当前状态: {current.value}"
            )
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value

    @classmethod
    def approve(cls, asset: 'Asset') -> None:
        """
        审批通过报废: damaged → scrapped
        待报废审批通过后，资产转为已报废状态（终态）。
        触发时机: 审批人通过待报废申请后，由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.SCRAPPED)

    @classmethod
    def reject(cls, asset: 'Asset') -> None:
        """
        审批拒绝报废: damaged → recycled_pending
        待报废审批被拒绝后，资产回到待发放状态。
        【业务规则】审批拒绝后资产可回收再分配，而非直接恢复使用。
        触发时机: 审批人拒绝待报废申请后，由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.RECYCLED_PENDING)

    # ===================================================================
    # 不在账资产专用状态转换（unregisteredasset 应用使用）
    # ===================================================================

    @classmethod
    def unregistered_create_and_recycle(cls, asset: 'Asset') -> None:
        """
        未登记资产创建并回收: 无状态 → recycled_pending

        【业务场景】S1场景（实物有系统无）审批通过后，直接创建资产并入库待发放。
        此操作跳过常规的入库流程，直接设置状态为 recycled_pending。

        【使用方式】
            # 在 UnregisteredAssetService 中调用
            asset = Asset.objects.create(**asset_data)  # 状态默认为 in_store
            AssetFSM.unregistered_create_and_recycle(asset)  # 改为 recycled_pending
            asset.save()

        Args:
            asset: 新创建的资产实例（当前状态应为 in_store 或空）

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
            raise InvalidTransitionError(
                f"未登记资产创建时状态必须为空白或'in_store'，当前: {current_status}"
            )
        # 直接设置为目标状态（跳过常规状态流转）
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value

    @classmethod
    def unregistered_create_and_damaged(cls, asset: 'Asset') -> None:
        """
        未登记资产创建并待报废: 无状态 → damaged

        【业务场景】S1场景（实物有系统无）审批通过后，创建资产并直接进入待报废流程。
        此操作用于发现实物资产但决定报废的场景。

        【使用方式】
            # 在 UnregisteredAssetService 中调用
            asset = Asset.objects.create(**asset_data)
            AssetFSM.unregistered_create_and_damaged(asset)
            asset.save()
            # 然后创建 DamagedAsset 记录

        Args:
            asset: 新创建的资产实例（当前状态应为 in_store 或空）

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
            raise InvalidTransitionError(
                f"未登记资产创建时状态必须为空白或'in_store'，当前: {current_status}"
            )
        asset.asset_current_status = AssetState.DAMAGED.value

    @classmethod
    def force_recycle_from_any(cls, asset: 'Asset') -> None:
        """
        强制回收: (任意非终态) → recycled_pending

        【业务场景】S2/S3场景使用，用于处理系统中有记录但流程异常的资产。
        - S2: 系统有资产记录但无出库记录，补建出库后直接回收
        - S3: 资产状态与实际不符，强制修正后回收

        【警告】此方法绕过常规状态流转校验，仅用于管理员审批授权后的特殊操作。
        禁止从终态（scrapped）转换。

        【使用方式】
            # 在 UnregisteredAssetService 中调用（需已审批授权）
            asset = Asset.objects.select_for_update().get(asset_code='AST001')
            AssetFSM.force_recycle_from_any(asset)
            asset.save()

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态为终态（scrapped）时抛出

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
            raise InvalidTransitionError(
                "已报废资产无法强制回收，当前状态: scrapped"
            )
        # 直接设置状态，跳过常规流转校验
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value
