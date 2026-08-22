"""
资产状态机转换规则表

定义资产有限状态机允许的状态转换集合(纯数据,不含行为)。
状态流转图详见 constants.py 模块文档。
转换方法的实现见同目录各 Mixin(out_recycle/scrapping/unregistered/broken_lost_repair)
与核心组合类 core.py。
"""

from apps.assetmanagement.state_machine.constants import AssetState

# 定义允许的转换: {当前状态: {目标状态: 转换名称}}
#
# 【业务规则】
# - reject(审批拒绝)回退到申请前状态(由 original_status 决定,见 reject_to_original)
# - cancel(用户取消)回到 recycled_pending
# - scrapped 为终态,不允许任何转出
# - 维修完成/找回入池:已使用过的资产(维修/找回)统一回到 recycled_pending,
#   in_store 仅表示首次入库的新资产
#
VALID_TRANSITIONS: dict = {
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
