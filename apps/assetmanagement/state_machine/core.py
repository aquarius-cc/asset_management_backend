"""
资产状态机核心实现
【AGENTS 规范 - 状态机解耦】
集中管理资产状态流转规则,每个状态转换是独立方法。
状态流转图详见 constants.py 模块文档。
职责边界:
- 【状态机负责】只修改 asset.asset_current_status 字段
- 【Service负责】事务控制、并发锁、其他字段更新、日志记录

【文件结构 - DR-5 规模拆分】
- transitions.py: 状态转换规则表(VALID_TRANSITIONS,纯数据)
- out_recycle.py / scrapping.py / unregistered.py / broken_lost_repair.py:
  各业务域的转换方法(Mixin,仅供本类组合,禁止单独调用)
- core.py: AssetFSM 组合类与内部校验/执行方法(_validate_transition/_transition)
"""

from typing import TYPE_CHECKING

from apps.assetmanagement.state_machine.broken_lost_repair import BrokenLostRepairTransitionsMixin
from apps.assetmanagement.state_machine.constants import AssetState, InvalidTransitionError
from apps.assetmanagement.state_machine.out_recycle import OutRecycleTransitionsMixin
from apps.assetmanagement.state_machine.scrapping import ScrappingTransitionsMixin
from apps.assetmanagement.state_machine.transitions import VALID_TRANSITIONS
from apps.assetmanagement.state_machine.unregistered import UnregisteredTransitionsMixin


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


class AssetFSM(
    OutRecycleTransitionsMixin,
    ScrappingTransitionsMixin,
    UnregisteredTransitionsMixin,
    BrokenLostRepairTransitionsMixin,
):
    """
    资产有限状态机
    【设计原则 - AGENTS规范】
    - 单一职责: 只负责状态字段(asset_current_status)变更,不处理其他字段
    - 显式调用: 每个状态转换是独立方法,调用意图清晰可见
    - 契约驱动: 通过类型注解和文档明确接口契约
    - 事务边界: 状态机不处理事务和并发锁,由调用方(Service)控制
    【使用方式】
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            AssetFSM.outasset(asset)
            asset.save()
    【注意】
    - 所有方法只修改 asset.asset_current_status,不调用 save()
    - 所有方法不处理事务,由调用方通过 @transaction.atomic 控制
    - 所有方法不处理并发锁,由调用方通过 select_for_update() 控制
    - 转换方法由各 Mixin 提供(见模块文档"文件结构"),经 MRO 组合到本类;
      必须通过 AssetFSM 调用,Mixin 类不可单独使用
    """

    # ===================================================================
    # 内部方法
    # ===================================================================

    @classmethod
    def _validate_transition(cls, asset: "Asset", target_state: AssetState) -> None:
        """
        验证状态转换合法性(不修改状态)
        """
        current = AssetState.from_string(asset.asset_current_status)
        if target_state not in VALID_TRANSITIONS.get(current, {}):
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
