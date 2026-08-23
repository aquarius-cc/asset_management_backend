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
        current = ContractState(current_status)
        target = ContractState(target_status)
        if target not in _CONTRACT_TRANSITIONS.get(current, {}):
            raise ContractInvalidTransitionError(f"合同状态转换不合法: {current.value} → {target.value}")

    @classmethod
    def transition(cls, contract: "Contract", target_status: str) -> None:
        cls._validate_transition(contract.contract_status, target_status)
        contract.contract_status = target_status
