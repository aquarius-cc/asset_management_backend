"""批量长度预检 helper 单元测试(M-31 / BF-142)

全仓 11 处同形 `if len > MAX_BATCH_SIZE: raise ...BATCH_SIZE_EXCEEDED`
收敛至 core.batch_mixins.ensure_batch_size 唯一实现(DR-1):
- mixin 双预检(batch_execute/batch_delete_execute)
- service 七预检(employee×2 / department×3 / storage / asset_type / contract /
  hard_disk 保存)
文案契约经 action 参数逐字沿用;行为等价由既有 20+ 条
BATCH_SIZE_EXCEEDED 集成锚(各 service 超限用例)回归护住。
"""

import pytest

from core.batch_mixins import ensure_batch_size
from core.exceptions import AppValidationError


class TestEnsureBatchSize:
    """ensure_batch_size 唯一实现的文案与阈值契约"""

    @pytest.mark.parametrize(
        ("action", "expected_detail"),
        [
            ("批量操作", "单次批量操作不能超过 3 条"),
            ("批量创建", "单次批量创建不能超过 3 条"),
            ("批量删除", "单次批量删除不能超过 3 条"),
            ("批量排序", "单次批量排序不能超过 3 条"),
            ("批量保存", "单次批量保存不能超过 3 条"),
        ],
    )
    def test_over_limit_raises_action_specific_message(self, action: str, expected_detail: str) -> None:
        """超限即拒,文案 = 单次{action}不能超过 {max_size} 条(原格式逐字保留)"""
        with pytest.raises(AppValidationError) as exc_info:
            ensure_batch_size(4, 3, action)
        assert exc_info.value.detail == expected_detail
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    @pytest.mark.parametrize("count", [0, 1, 3])
    def test_at_or_under_limit_passes(self, count: int) -> None:
        """恰等上限/低于上限放行(边界不含 >)"""
        ensure_batch_size(count, 3, "批量创建")

    def test_one_over_limit_rejects(self) -> None:
        """上限 +1 即拒(原 if len > MAX 口径)"""
        with pytest.raises(AppValidationError) as exc_info:
            ensure_batch_size(4, 3, "批量删除")
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"
