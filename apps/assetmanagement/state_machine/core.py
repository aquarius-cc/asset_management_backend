# TECHNICAL_DEBT: >500 lines
"""
资产状态机核心实现
【AGENTS 规范 - 状态机解耦】
集中管理资产状态流转规则,每个状态转换是独立方法。
核心设计:
- AssetState: 状态枚举定义
- AssetFSM: 状态转换方法集合
- InvalidTransitionError: 非法转换异常
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


class AssetFSM:
    """
    资产有限状态机
    【设计原则 - AGENTS规范】
    - 单一职责: 只负责状态字段(asset_current_status)变更,不处理其他字段
    - 显式调用: 每个状态转换是独立方法,调用意图清晰可见
    - 契约驱动: 通过类型注解和文档明确接口契约
    - 事务边界: 状态机不处理事务和并发锁,由调用方(Service)控制
    【使用方式】
        # Service层控制事务和并发
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            AssetFSM.outasset(asset)  # 执行状态转换(只修改内存中的值)
            asset.save()              # 持久化到数据库

    【注意】
    - 所有方法只修改 asset.asset_current_status,不调用 save()
    - 所有方法不处理事务,由调用方通过 @transaction.atomic 控制
    - 所有方法不处理并发锁,由调用方通过 select_for_update() 控制
    """

    # ===================================================================
    # 状态转换规则定义
    # ===================================================================

    # 定义允许的转换: {当前状态: {目标状态: 转换名称}}
    #
    # 【完整状态流转图】
    #
    #   主路径: in_store ──outasset──→ in_use ──recycle──→ recycled_pending ──to_damaged──→ damaged ──approve──→ scrapped(终态)
    #           recycled_pending ──outasset──→ in_use(再次出库)
    #           damaged ──reject──→ broken/lost/in_use/recycled_pending/repairing (审批拒绝,按original_status回退)
    #           damaged ──cancel──→ recycled_pending(用户取消)
    #
    #   损坏/遗失/维修路径:
    #           in_store / in_use / recycled_pending ──mark_broken──→ broken
    #           in_store / in_use / recycled_pending ──mark_lost──→ lost
    #           broken ──repair──→ repairing ──repair_done──→ recycled_pending
    #           repairing ──repair_failed──→ damaged
    #           lost ──found_and_return──→ recycled_pending
    #           lost ──to_damaged──→ damaged
    #
    # 【业务规则】
    # - reject(审批拒绝)回退到申请前状态(由 original_status 决定,见 reject_to_original)
    # - cancel(用户取消)回到 recycled_pending
    # - scrapped 为终态,不允许任何转出
    # - 维修完成/找回入池:已使用过的资产(维修/找回)统一回到 recycled_pending,
    #   in_store 仅表示首次入库的新资产
    #
    _TRANSITIONS: dict = {
        # 在库 → 在用(首次出库)、已损坏、已遗失
        AssetState.IN_STORE: {
            AssetState.IN_USE: "outasset",
            AssetState.BROKEN: "mark_broken",
            AssetState.LOST: "mark_lost",
        },
        # 在用 → 待发放(回收)、已损坏、已遗失
        # 【业务决策】in_use 不允许直接申请报废,须先回收(recycle → recycled_pending)再申请报废
        AssetState.IN_USE: {
            AssetState.RECYCLED_PENDING: "recycle",
            AssetState.BROKEN: "mark_broken",
            AssetState.LOST: "mark_lost",
        },
        # 待发放 → 在用(再次出库)、已损坏、已遗失、待报废
        AssetState.RECYCLED_PENDING: {
            AssetState.IN_USE: "outasset",
            AssetState.BROKEN: "mark_broken",
            AssetState.LOST: "mark_lost",
            AssetState.DAMAGED: "to_damaged",
        },
        # 已损坏 → 待报废(提交报废)或 → 维修中(送修)
        AssetState.BROKEN: {
            AssetState.DAMAGED: "to_damaged",
            AssetState.REPAIRING: "repair",
        },
        # 维修中 → 待发放(维修完成,已使用资产修好后重新入待发放池)或 → 待报废(维修失败)
        AssetState.REPAIRING: {
            AssetState.RECYCLED_PENDING: "repair_done",
            AssetState.DAMAGED: "repair_failed",
        },
        # 已遗失 → 待报废(提交报废)或 → 待发放(找回,重新进入发放池)
        AssetState.LOST: {
            AssetState.DAMAGED: "to_damaged",
            AssetState.RECYCLED_PENDING: "found_and_return",
        },
        # 待报废 → 已报废(审批通过)、回退申请前状态(审批拒绝)
        AssetState.DAMAGED: {
            AssetState.SCRAPPED: "approve",
            AssetState.BROKEN: "reject_to_broken",
            AssetState.LOST: "reject_to_lost",
            AssetState.IN_USE: "reject_to_in_use",
            AssetState.RECYCLED_PENDING: "reject_to_recycled_pending",
            AssetState.REPAIRING: "reject_to_repairing",
        },
        # 已报废 - 终态,无转出
        AssetState.SCRAPPED: {},
    }

    # ===================================================================
    # 内部方法
    # ===================================================================

    # 审批拒绝的合法回退目标(对应各 reject_to_* 方法)
    # 【注意】scrapped(approve)虽然也在 _TRANSITIONS[DAMAGED] 中,但不可作为拒绝目标
    _REJECT_TARGETS: set[AssetState] = {
        AssetState.BROKEN,
        AssetState.LOST,
        AssetState.IN_USE,
        AssetState.RECYCLED_PENDING,
        AssetState.REPAIRING,
    }

    @classmethod
    def _validate_transition(cls, asset: "Asset", target_state: AssetState) -> None:
        """
        验证状态转换合法性(不修改状态)
        """
        current = AssetState.from_string(asset.asset_current_status)
        if target_state not in cls._TRANSITIONS.get(current, {}):
            raise InvalidTransitionError(f"状态转换不合法: {current.value} → {target_state.value}")

    @classmethod
    def _transition(cls, asset: "Asset", target_state: AssetState) -> None:
        """
        执行状态转换(内部方法)
        验证合法性后修改 asset.asset_current_status。
        【注意】不调用 save(),由调用方控制持久化时机。

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
        【注意】此为特殊回退操作,不在 _TRANSITIONS 中定义。

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
        【注意】此为特殊回退操作,不在 _TRANSITIONS 中定义。
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

    # ===================================================================
    # 报废相关状态转换
    # ===================================================================

    @classmethod
    def damaged(cls, asset: "Asset") -> None:
        """
        申请报废: (recycled_pending | broken | repairing | lost) → damaged
        资产转为待报废状态。
        【业务决策】in_use 不允许直接申请报废,须先回收再申请。
        触发时机: 创建待报废记录(DamagedAsset)后,由 DamagedAssetService 调用。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不允许申请报废时抛出
        """
        cls._transition(asset, AssetState.DAMAGED)

    @classmethod
    def cancel_damaged(cls, asset: "Asset") -> None:
        """
        取消报废申请: damaged → recycled_pending
        用户主动取消待报废申请,资产回到待发放状态。
        【业务语义】与 reject 不同:cancel 是用户主动取消,reject 是审批人拒绝。
        触发时机: 删除待报废记录后(用户主动操作)。
        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        current = AssetState.from_string(asset.asset_current_status)
        if current != AssetState.DAMAGED:
            raise InvalidTransitionError(f"只有'待报废'状态的资产才能取消申请,当前状态: {current.value}")
        asset.asset_current_status = AssetState.RECYCLED_PENDING.value

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
        cls._transition(asset, AssetState.SCRAPPED)

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

    @classmethod
    def reject_to_in_use(cls, asset: "Asset") -> None:
        """
        审批拒绝(在用): damaged → in_use

        待报废审批被拒绝后,资产回到在用状态。
        触发时机: 审批人拒绝待报废申请,且原状态为 in_use 时。

        Args:
            asset: 资产实例

        Raises:
            InvalidTransitionError: 当前状态不是 damaged 时抛出
        """
        cls._transition(asset, AssetState.IN_USE)

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
        cls._transition(asset, AssetState.RECYCLED_PENDING)

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
        cls._transition(asset, AssetState.REPAIRING)

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
        cls._transition(asset, AssetState.BROKEN)

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
        cls._transition(asset, AssetState.LOST)

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
        cls._transition(asset, AssetState.RECYCLED_PENDING)

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
        cls._transition(asset, AssetState.BROKEN)

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
        cls._transition(asset, AssetState.LOST)

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
        cls._transition(asset, AssetState.REPAIRING)

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
        cls._transition(asset, AssetState.RECYCLED_PENDING)

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
        cls._transition(asset, AssetState.DAMAGED)
