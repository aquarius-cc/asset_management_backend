# signals.py
"""
资产信号处理模块

【AGENTS 规范 - P0-02 修复】
本模块原包含 post_save/post_delete 信号处理器，用于在出库/回收/待报废/已报废
记录创建或删除时自动触发 AssetStateManager 的状态变更逻辑。

【已移除原因】
1. Signal 与 Service 层存在双重触发：Service 层已显式调用 AssetStateManager，
   Signal 又会隐式触发同一逻辑，导致每次创建记录时状态变更被执行两次。
2. 信号是隐式调用，调试困难，难以追踪状态变更来源。
3. 项目规范要求：Service 层显式调用 > Signal 隐式触发。

【当前状态】
所有状态变更逻辑统一由 Service 层显式调用 AssetStateManager 处理。
本文件保留作为历史记录，不再注册任何信号处理器。
"""
