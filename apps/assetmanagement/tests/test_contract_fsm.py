"""
ContractFSM.allowed_next_states 单元测试(P3-04)

纯逻辑测试,不触库:
- 合法状态返回唯一出边(线性 8 态)
- 终态 project_finished 返回 []
- 未知/非法状态值防御性返回 [](读路径不抛,防详情端点 500)
- 入参兼容 str 与 ContractState 两种形态
"""

import pytest

from apps.assetmanagement.state_machine.contract_fsm import (
    _CONTRACT_TRANSITIONS,
    ContractFSM,
    ContractState,
)


class TestAllowedNextStates:
    """allowed_next_states 返回口径测试"""

    @pytest.mark.parametrize(
        ("current", "expected"),
        [
            ("purchasing", ["purchase_finished"]),
            ("purchase_finished", ["receive_check"]),
            ("receive_check", ["initial_check"]),
            ("initial_check", ["project_settlement"]),
            ("project_settlement", ["settlement_done"]),
            ("settlement_done", ["final_check"]),
            ("final_check", ["project_finished"]),
        ],
    )
    def test_linear_chain_returns_single_edge(self, current: str, expected: list[str]) -> None:
        """线性 8 态:每个非终态恰有唯一合法下一状态"""
        assert ContractFSM.allowed_next_states(current) == expected

    def test_terminal_state_returns_empty(self) -> None:
        """终态 project_finished 无出边,返回 []"""
        assert ContractFSM.allowed_next_states("project_finished") == []

    @pytest.mark.parametrize("bogus", ["unknown_status", "", "PURCHASING", "in_store", "purchasing "])
    def test_invalid_value_returns_empty_not_raise(self, bogus: str) -> None:
        """【防御口径】未知/非法状态值返回 [] 而非抛 ValueError(读路径不 500)"""
        assert ContractFSM.allowed_next_states(bogus) == []

    def test_accepts_contract_state_enum(self) -> None:
        """入参兼容 ContractState 枚举形态"""
        assert ContractFSM.allowed_next_states(ContractState.PURCHASING) == ["purchase_finished"]
        assert ContractFSM.allowed_next_states(ContractState.PROJECT_FINISHED) == []

    def test_edges_match_transition_table(self) -> None:
        """【回归屏障】返回值与 _CONTRACT_TRANSITIONS 键集一致,防两处实现漂移"""
        for state in ContractState:
            expected = [t.value for t in _CONTRACT_TRANSITIONS.get(state, {})]
            assert ContractFSM.allowed_next_states(state) == expected
