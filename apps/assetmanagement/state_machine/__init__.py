"""
资产状态机模块

【AGENTS 规范 - 状态机解耦】
该模块提供有限状态机(FSM)实现，集中管理资产状态流转规则。

设计原则:
1. 单一职责 - 状态机只负责状态字段变更，其他字段更新在Service层
2. 显式调用 - 每个状态转换是独立方法，调用意图清晰
3. 契约驱动 - 通过类型注解和文档明确接口契约
4. 事务边界 - 状态机不处理事务，由调用方(Service)控制

使用方式:
    from apps.assetmanagement.state_machine import AssetFSM
    
    # 在Service层调用
    with transaction.atomic():
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        AssetFSM.outasset(asset)  # 状态: in_store → in_use
        asset.save()
"""

from .core import AssetFSM, AssetState, InvalidTransitionError

__all__ = ['AssetFSM', 'AssetState', 'InvalidTransitionError']
