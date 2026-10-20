"""
合同状态机

管理合同 8 种状态的合法流转规则。
"""

from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from apps.assetmanagement.models import Contract


class ContractState(Enum):
    PURCHASING = "purchasing"
    PURCHASE_FINISHED = "purchase_finished"
    RECEIVE_CHECK = "receive_check"
    INITIAL_CHECK = "initial_check"
    PROJECT_SETTLEMENT = "project_settlement"
    SETTLEMENT_DONE = "settlement_done"
    FINAL_CHECK = "final_check"
    PROJECT_FINISHED = "project_finished"


class ContractInvalidTransitionError(Exception):
    pass


# 合法流转路径: {当前状态: {目标状态: 转换名称}}
_CONTRACT_TRANSITIONS: dict[ContractState, dict[ContractState, str]] = {
    ContractState.PURCHASING: {
        ContractState.PURCHASE_FINISHED: "purchase_finished",
    },
    ContractState.PURCHASE_FINISHED: {
        ContractState.RECEIVE_CHECK: "receive_check",
    },
    ContractState.RECEIVE_CHECK: {
        ContractState.INITIAL_CHECK: "initial_check",
    },
    ContractState.INITIAL_CHECK: {
        ContractState.PROJECT_SETTLEMENT: "project_settlement",
    },
    ContractState.PROJECT_SETTLEMENT: {
        ContractState.SETTLEMENT_DONE: "settlement_done",
    },
    ContractState.SETTLEMENT_DONE: {
        ContractState.FINAL_CHECK: "final_check",
    },
    ContractState.FINAL_CHECK: {
        ContractState.PROJECT_FINISHED: "project_finished",
    },
    ContractState.PROJECT_FINISHED: {},
}


class ContractFSM:
    """
    合同有限状态机
    只负责状态字段变更,不处理其他字段。
    """

    @classmethod
    def _validate_transition(cls, current_status: str, target_status: str) -> None:
        try:
            current = ContractState(current_status)
            target = ContractState(target_status)
        except ValueError:
            # AUD-15: 非法态收敛为本域异常(与读路径 allowed_next_states 的 ValueError 防御同口径), 不再裸抛 500
            raise ContractInvalidTransitionError(
                f"合同状态不合法: current={current_status!r} target={target_status!r}"
            ) from None
        if target not in _CONTRACT_TRANSITIONS.get(current, {}):
            raise ContractInvalidTransitionError(f"合同状态转换不合法: {current.value} → {target.value}")

    @classmethod
    def transition(cls, contract: "Contract", target_status: str) -> None:
        cls._validate_transition(contract.contract_status, target_status)
        contract.contract_status = target_status

    @classmethod
    def allowed_next_states(cls, current_status: str | ContractState) -> list[str]:
        """返回当前状态的全部合法下一状态值(展示用,DR-1 唯一实现)。

        读路径专用:未知/非法状态值防御性返回 []——详情序列化不应因脏数据 500,
        终态(project_finished)同样返回 [],前端据此禁用状态下拉。
        """
        try:
            current = current_status if isinstance(current_status, ContractState) else ContractState(current_status)
        except ValueError:
            return []
        return [target.value for target in _CONTRACT_TRANSITIONS.get(current, {})]
