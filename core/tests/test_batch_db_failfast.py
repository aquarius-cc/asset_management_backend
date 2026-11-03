"""M-11 DatabaseError fail-fast 行为测试

【M-11】batch_execute / batch_delete_execute 的宽 except Exception 会把 DatabaseError
(连接中断/死锁/事务中止, 含 TransactionManagementError)降级为逐条 INTERNAL_ERROR:
无 savepoint 时后续条目连锁抛错, 有 savepoint 时"已成功"条目同样不可信 —— 一律整体
抛出, 绝不返回"部分成功"。对照组: AppValidationError 仍走 fail_items 软失败。
"""

import pytest
from django.db import DatabaseError, OperationalError, connection

from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError


def _raise_db_error(idx: int, item: str) -> str:
    raise OperationalError("connection reset")


class TestBatchDbFailFast:
    def test_batch_execute_propagates_database_error(self):
        """DatabaseError 整体抛出, 不返回 result"""
        with pytest.raises(DatabaseError):
            BatchOperationMixin.batch_execute(items=["a"], process_fn=_raise_db_error)

    def test_batch_execute_stops_at_first_database_error(self):
        """第 2 条抛 DatabaseError 即中止: 第 3 条不再执行"""
        seen: list[str] = []

        def process(idx: int, item: str) -> str:
            seen.append(item)
            if item == "b":
                raise OperationalError("deadlock detected")
            return item

        with pytest.raises(DatabaseError):
            BatchOperationMixin.batch_execute(items=["a", "b", "c"], process_fn=process)

        assert seen == ["a", "b"]

    def test_batch_execute_validation_error_still_soft_fails(self):
        """对照组: AppValidationError 仍进 fail_items(防一刀切全抛回归)"""

        def process(idx: int, item: str) -> str:
            if item == "b":
                raise AppValidationError(detail="重复编码", error_code="DUPLICATE_CODE")
            return item

        result = BatchOperationMixin.batch_execute(items=["a", "b"], process_fn=process)

        assert result["success_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DUPLICATE_CODE"

    @pytest.mark.django_db
    def test_batch_delete_execute_propagates_database_error(self):
        """batch_delete_execute 同型: DatabaseError 整体抛出"""

        def _delete_one(item_id: str) -> None:
            raise OperationalError("connection reset")

        with pytest.raises(DatabaseError):
            BatchOperationMixin.batch_delete_execute(ids=["a"], process_fn=_delete_one)

    @pytest.mark.django_db
    def test_use_transaction_true_propagates(self):
        """真实 savepoint 路径(use_transaction=True)下同样整体抛出, 且连接仍可用"""

        def process(idx: int, item: str) -> str:
            raise OperationalError("savepoint rollback failed")

        with pytest.raises(DatabaseError):
            BatchOperationMixin.batch_execute(items=["a"], process_fn=process, use_transaction=True)

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
