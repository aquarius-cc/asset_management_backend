"""
未登记资产管理应用

该应用用于管理不在账资产的发现、核实、处理全流程。
作为独立应用，遵循与 assetmanagement 的清晰边界：
- 本应用负责：未登记资产的申请、审批流程管理
- assetmanagement 负责：核心资产状态机、资产生命周期

跨应用调用规范：
1. 模型外键使用字符串引用（'assetmanagement.Asset'）
2. Service 层方法内部延迟导入依赖
3. 状态机调用通过适配器封装

Author: System
Date: 2026-05-26
"""

default_app_config = 'apps.unregisteredasset.apps.UnregisteredAssetConfig'
