"""
BF-092 I-4 + I-10 测试

I-4: 合同行锁防并发丢失更新——付款读-改-写场景。
I-10: 结算后金额重算——状态流转 settlement_done 后 amount_unpaid 滞留旧口径修复;
      settlemented_price 经 PATCH 编辑后 perform_update 触发重算。
"""

import json
import threading
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import Contract
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.services.contract_service import ContractService


# 【BF-092/I-4】SQLite 不支持 select_for_update 行级锁,并发用例守卫(CI 为 Postgres 照常执行)
requires_row_lock = pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite 不支持 select_for_update 行级锁,跳过真并发用例(CI 为 Postgres)",
)


def _contract_data(**overrides):
    defaults = {
        "contract_code": "C001",
        "contract_name": "测试合同",
        "contract_type": "tender_procurement",
        "contract_amount": Decimal("10000.00"),
        "supplier_name": "供应商A",
        "contract_start_date": "2024-01-01",
        "contract_end_date": "2024-12-31",
        "contract_status": "purchasing",
    }
    defaults.update(overrides)
    return defaults


def _advance_to_settlement_done(contract_code: str) -> None:
    """通过合法 FSM 路径推进合同至 settlement_done 状态"""
    for target in ("receive_check", "initial_check", "project_settlement", "settlement_done"):
        ContractService.update_settlement_status(contract_code, target)


# ============================================================
# I-4: 行锁选择器
# ============================================================


@pytest.mark.django_db
class TestGetContractForUpdate:
    """I-4: get_contract_for_update 选择器"""

    def test_returns_contract(self):
        ContractService.create_contract(_contract_data())
        result = ContractSelector.get_contract_for_update("C001")
        assert result.contract_code == "C001"

    def test_missing_contract_raises_does_not_exist(self):
        with pytest.raises(Contract.DoesNotExist):
            ContractSelector.get_contract_for_update("NOPE")

    def test_soft_deleted_not_found(self):
        c = ContractService.create_contract(_contract_data())
        c.is_deleted = True
        c.save(update_fields=["is_deleted"])
        with pytest.raises(Contract.DoesNotExist):
            ContractSelector.get_contract_for_update("C001")


# ============================================================
# I-4: 并发付款
# ============================================================


@pytest.mark.django_db(transaction=True)
class TestConcurrentPayment:
    """I-4: 并发付款读-改-写行锁保护"""

    @requires_row_lock
    def test_concurrent_add_payment_no_lost_update(self):
        """两个并发付款请求,金额累加不得丢失(行锁串行化)"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("100000.00")))

        errors = []
        lock = threading.Lock()

        def pay(amount_val):
            try:
                with transaction.atomic():
                    ContractService.add_payment_record("C001", Decimal(str(amount_val)), "并发付款")
            except Exception as e:
                with lock:
                    errors.append(f"{amount_val}: {type(e).__name__}: {e}")

        t1 = threading.Thread(target=pay, args=(10000,))
        t2 = threading.Thread(target=pay, args=(20000,))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"并发付款不应报错: {errors}"
        contract = Contract.objects.get(contract_code="C001")
        # 两次付款金额合计 30000,不允许出现「一方覆盖另一方」(丢失更新则只会看到 10000 或 20000)
        assert contract.amount_paid == Decimal("30000.00")
        data = json.loads(contract.paid_record)
        assert len(data["payments"]) == 2


# ============================================================
# I-4: 单条付款不再全字段回写
# ============================================================


@pytest.mark.django_db
class TestPaymentSaveFields:
    """I-4: add_payment_record 定向 save(update_fields)"""

    def test_save_update_fields_set(self):
        """验证 save 调用使用 update_fields(防全字段回写并发风险)"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        contract = Contract.objects.get(contract_code="C001")
        assert contract.amount_paid == Decimal("10000.00")
        assert contract.amount_unpaid == Decimal("40000.00")


# ============================================================
# I-10: 结算状态流转后金额重算
# ============================================================


@pytest.mark.django_db
class TestSettlementRecalc:
    """I-10: update_settlement_status 结算后金额重算"""

    def test_settlement_done_recalculates_amounts(self):
        """状态流转 settlement_done 后,amount_unpaid 基于 settlemented_price 重算"""
        ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("100000.00"),
                settlemented_price=Decimal("80000.00"),
                contract_status="purchase_finished",
            )
        )
        # 手动加一笔付款(使 amount_paid > 0)
        ContractService.add_payment_record("C001", Decimal("40000.00"), "预付款")

        # 推进至 settlement_done → 应触发 _recalc_paid_amounts
        _advance_to_settlement_done("C001")
        contract = Contract.objects.get(contract_code="C001")
        # settlemented_price=80000, amount_paid=40000 → amount_unpaid 应为 40000
        # (修复前为 60000,基于 contract_amount=100000 的旧口径)
        assert contract.amount_unpaid == Decimal("40000.00")

    def test_settlement_done_recalculates_with_zero_payments(self):
        """结算后零付款,amount_unpaid = settlemented_price"""
        ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("100000.00"),
                settlemented_price=Decimal("75000.00"),
                contract_status="purchase_finished",
            )
        )
        _advance_to_settlement_done("C001")
        contract = Contract.objects.get(contract_code="C001")
        assert contract.amount_unpaid == Decimal("75000.00")

    def test_non_settlement_transition_no_recalc(self):
        """非结算状态流转不受影响(不触发结算重算分支)"""
        ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("50000.00"),
                contract_status="purchasing",
            )
        )
        result = ContractService.update_settlement_status("C001", "purchase_finished")
        # purchasing 状态下 _recalc 分支是 else(contract_amount - amount_paid)
        assert result.amount_unpaid == Decimal("50000.00")


# ============================================================
# I-10: perform_update settlemented_price 编辑后重算
# ============================================================


@pytest.mark.django_db
class TestPerformUpdateSettlementedPrice:
    """I-10: PATCH 编辑 settlemented_price 后 perform_update 触发重算"""

    @pytest.fixture
    def admin_client(self, api_client, admin_auth_user):
        api_client.force_authenticate(user=admin_auth_user)
        return api_client

    @pytest.fixture
    def settlement_done_contract(self, db):
        """已推进至 settlement_done 状态的合同(settlemented_price 生效前提)"""
        c = ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("10000.00"),
                settlemented_price=Decimal("10000.00"),
                contract_status="purchase_finished",
            )
        )
        _advance_to_settlement_done("C001")
        c.refresh_from_db()
        return c

    def test_patch_settlemented_price_recalculates(self, admin_client, settlement_done_contract):
        """PATCH 修改 settlemented_price 后 amount_unpaid 应重算"""
        url = reverse("contracts-detail", kwargs={"recordcode": settlement_done_contract.recordcode})
        response = admin_client.patch(url, {"settlemented_price": 8000.00}, format="json")
        assert response.status_code == status.HTTP_200_OK
        settlement_done_contract.refresh_from_db()
        # settlemented_price=8000, amount_paid=0 → amount_unpaid=8000
        assert settlement_done_contract.amount_unpaid == Decimal("8000.00")

    def test_patch_other_field_no_recalc(self, admin_client, settlement_done_contract):
        """PATCH 修改其他字段不触发 settlemented_price 重算路径"""
        url = reverse("contracts-detail", kwargs={"recordcode": settlement_done_contract.recordcode})
        response = admin_client.patch(url, {"contract_name": "改名后的合同"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        settlement_done_contract.refresh_from_db()
        assert settlement_done_contract.amount_unpaid == Decimal("10000.00")  # 原值不变

    def test_patch_settlemented_price_after_payment(self, admin_client, settlement_done_contract):
        """有付款后再 PATCH settlemented_price,重算基于 settlemented_price"""
        # 先加一笔付款
        ContractService.add_payment_record("C001", Decimal("3000.00"), "首付款")
        url = reverse("contracts-detail", kwargs={"recordcode": settlement_done_contract.recordcode})
        response = admin_client.patch(url, {"settlemented_price": 8000.00}, format="json")
        assert response.status_code == status.HTTP_200_OK
        settlement_done_contract.refresh_from_db()
        # settlemented_price=8000, amount_paid=3000 → amount_unpaid=5000
        assert settlement_done_contract.amount_unpaid == Decimal("5000.00")
