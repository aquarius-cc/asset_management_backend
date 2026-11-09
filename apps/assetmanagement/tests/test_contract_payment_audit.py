"""合同支付域审计载荷测试(M-05 收口)

覆盖:
- operator_jobcode kw-only 必填: 忘传即 TypeError(对齐 M-07 形态,防无操作人审计行)
- operator_name 合法为空(None):与 resolve_operator 返回形态一致
"""

from decimal import Decimal
from typing import Any

import pytest

from apps.assetmanagement.models import Contract
from apps.assetmanagement.services.contract_payment_audit import (
    log_payment_added,
    log_payment_approved,
    log_payment_batch_summary,
    log_payment_deleted,
)


@pytest.fixture
def contract(db: Any) -> Contract:
    return Contract.objects.create(
        contract_code="C001",
        contract_name="审计载荷测试合同",
        contract_amount=10000.00,
        contract_status="purchasing",
        contract_type="service",
        contract_start_date="2024-01-01",
        contract_end_date="2025-01-01",
    )


class TestOperatorRequired:
    def test_log_payment_added_missing_operator_raises_type_error(self, contract):
        with pytest.raises(TypeError):
            log_payment_added(contract, {"id": "P1", "date": "2024-03-01"}, Decimal("100"))

    def test_log_payment_batch_summary_missing_operator_raises_type_error(self):
        with pytest.raises(TypeError):
            log_payment_batch_summary("C001", {"total": 1, "success_count": 1, "fail_count": 0, "success_items": []})

    def test_log_payment_deleted_missing_operator_raises_type_error(self, contract):
        with pytest.raises(TypeError):
            log_payment_deleted(contract, "P1", "100")

    def test_log_payment_approved_missing_operator_raises_type_error(self, contract):
        with pytest.raises(TypeError):
            log_payment_approved(contract, "P1")

    def test_operator_name_none_is_legal(self, contract):
        """operator_name=None 为合法形态(resolve_operator 链中 name 可为空),仅 jobcode 必填"""
        log_payment_added(contract, {"id": "P1", "date": "2024-03-01"}, Decimal("100"), operator_jobcode="U001")
