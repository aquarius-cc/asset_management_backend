"""合同管理服务测试"""

import json
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.assetmanagement.models import Contract
from apps.assetmanagement.services.contract_service import ContractService
from core.exceptions import AppValidationError


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


@pytest.mark.django_db
class TestCreateContract:
    def test_create_success(self):
        result = ContractService.create_contract(_contract_data())
        assert result.contract_code == "C001"
        assert result.contract_name == "测试合同"

    def test_create_duplicate_code_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.create_contract(_contract_data(contract_code="C001", contract_name="另一个"))
        assert exc_info.value.error_code == "DUPLICATE_CONTRACT_CODE"


@pytest.mark.django_db
class TestAddPaymentRecord:
    def test_add_payment_success(self):
        _ = ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        result = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        assert result.amount_paid == Decimal("10000.00")
        assert result.amount_unpaid == Decimal("40000.00")
        data = json.loads(result.paid_record)
        assert len(data["payments"]) == 1
        assert data["payments"][0]["amount"] == "10000.00"
        assert data["payments"][0]["status"] == "pending"

    def test_add_payment_nonexistent_contract_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.add_payment_record("NOPE", Decimal("100"))
        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"

    def test_add_payment_zero_amount_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.add_payment_record("C001", Decimal("0"))
        assert exc_info.value.error_code == "INVALID_PAYMENT_AMOUNT"

    def test_add_payment_negative_amount_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError):
            ContractService.add_payment_record("C001", Decimal("-100"))

    def test_add_payment_cumulative(self):
        _ = ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        ContractService.add_payment_record("C001", Decimal("10000.00"))
        result = ContractService.add_payment_record("C001", Decimal("5000.00"))
        assert result.amount_paid == Decimal("15000.00")
        assert result.amount_unpaid == Decimal("35000.00")

    def test_add_payment_decimal_cumulative_precision(self):
        """【CT-4 回归屏障】0.1 三次累计必须精确等于 0.3(十进制累加,禁止二进制浮点漂移)"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        ContractService.add_payment_record("C001", Decimal("0.1"))
        ContractService.add_payment_record("C001", Decimal("0.1"))
        result = ContractService.add_payment_record("C001", Decimal("0.1"))
        assert result.amount_paid == Decimal("0.3")
        assert result.amount_unpaid == Decimal("49999.70")
        data = json.loads(result.paid_record)
        assert data["payments"][2]["amount"] == "0.1"

    def test_add_payment_settlement_status_uses_settlemented_price(self):
        _ = ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("50000.00"),
                settlemented_price=Decimal("45000.00"),
                contract_status="settlement_done",
            )
        )
        result = ContractService.add_payment_record("C001", Decimal("10000.00"))
        assert result.amount_unpaid == Decimal("35000.00")


@pytest.mark.django_db
class TestUpdateSettlementStatus:
    def test_update_status_success(self):
        ContractService.create_contract(_contract_data())
        result = ContractService.update_settlement_status("C001", "purchase_finished")
        assert result.contract_status == "purchase_finished"

    def test_update_invalid_status_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.update_settlement_status("C001", "invalid_status")
        assert exc_info.value.error_code == "INVALID_CONTRACT_STATUS"

    def test_update_nonexistent_contract_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.update_settlement_status("NOPE", "purchasing")
        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"


@pytest.mark.django_db
class TestGetContractStatistics:
    def test_statistics_empty(self):
        result = ContractService.get_contract_statistics()
        assert result["total_contracts"] == 0

    def test_statistics_with_data(self):
        ContractService.create_contract(_contract_data(contract_code="CS1", contract_name="C1"))
        ContractService.create_contract(_contract_data(contract_code="CS2", contract_name="C2"))
        result = ContractService.get_contract_statistics()
        assert result["total_contracts"] == 2


@pytest.mark.django_db
class TestDeleteContract:
    def test_delete_success(self):
        ContractService.create_contract(_contract_data())
        ContractService.delete_contract("C001")
        assert Contract.all_objects.filter(contract_code="C001", is_deleted=True).exists()

    def test_delete_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.delete_contract("NOPE")
        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"

    def test_delete_already_deleted_raises(self):
        ContractService.create_contract(_contract_data())
        ContractService.delete_contract("C001")
        with pytest.raises(AppValidationError):
            ContractService.delete_contract("C001")

    def test_delete_with_related_assets_raises(self):
        from apps.assetmanagement.models import Asset, AssetType, Storage

        c = ContractService.create_contract(_contract_data())
        at = AssetType.objects.create(type_code="AT_CON", type_name="AT_CON")
        s = Storage.objects.create(
            storage_code="S_CON",
            storage_name="S_CON",
            storage_address="addr",
            storage_capacity=100,
            sort_order=0,
        )
        Asset.objects.create(
            asset_code="A_CON",
            asset_name="A_CON",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=s,
            asset_type_recordcode=at,
            asset_contract_recordcode=c,
        )
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.delete_contract("C001")
        assert exc_info.value.error_code == "HAS_RELATED_ASSETS"


@pytest.mark.django_db
class TestBatchCreateContract:
    def test_batch_create_success(self):
        data = [
            {"contract_code": "BC1", "contract_name": "批量1", "contract_amount": Decimal("1000")},
            {"contract_code": "BC2", "contract_name": "批量2", "contract_amount": Decimal("2000")},
        ]
        result = ContractService.batch_create_contract(data)
        assert result["total"] == 2
        assert result["success_count"] == 2

    def test_batch_create_with_duplicate(self):
        ContractService.create_contract(_contract_data(contract_code="BDUP_C"))
        data = [
            {"contract_code": "BDUP_C", "contract_name": "Dup", "contract_amount": Decimal("1000")},
            {"contract_code": "BNEW_C", "contract_name": "New", "contract_amount": Decimal("2000")},
        ]
        result = ContractService.batch_create_contract(data)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1

    def test_batch_create_exceeds_limit_raises(self):
        data = [
            {"contract_code": f"CC{i}", "contract_name": f"C{i}", "contract_amount": Decimal("100")} for i in range(101)
        ]
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.batch_create_contract(data)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestBatchDeleteContract:
    def test_batch_delete_success(self):
        ContractService.create_contract(_contract_data(contract_code="BDC1"))
        ContractService.create_contract(_contract_data(contract_code="BDC2"))
        result = ContractService.batch_delete_contract(["BDC1", "BDC2"])
        assert result["success_count"] == 2

    def test_batch_delete_with_nonexistent(self):
        ContractService.create_contract(_contract_data(contract_code="BDC3"))
        result = ContractService.batch_delete_contract(["BDC3", "NOPE"])
        assert result["success_count"] == 1
        assert result["fail_count"] == 1


@pytest.mark.django_db
class TestDeletePaymentRecord:
    def test_delete_payment_success(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        data = json.loads(contract.paid_record)
        payment_id = data["payments"][0]["id"]
        result = ContractService.delete_payment_record("C001", payment_id)
        updated_data = json.loads(result.paid_record)
        assert updated_data["payments"][0]["status"] == "deleted"

    def test_delete_payment_nonexistent_contract_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.delete_payment_record("NOPE", "pay_xxx")
        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"

    def test_delete_payment_nonexistent_payment_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.delete_payment_record("C001", "pay_nonexistent")
        assert exc_info.value.error_code == "PAYMENT_NOT_FOUND"


@pytest.mark.django_db
class TestApprovePaymentRecord:
    def test_approve_payment_success(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        data = json.loads(contract.paid_record)
        payment_id = data["payments"][0]["id"]
        result = ContractService.approve_payment_record("C001", payment_id)
        updated_data = json.loads(result.paid_record)
        assert updated_data["payments"][0]["status"] == "approved"

    def test_approve_deleted_payment_raises(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"))
        data = json.loads(contract.paid_record)
        payment_id = data["payments"][0]["id"]
        ContractService.delete_payment_record("C001", payment_id)
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.approve_payment_record("C001", payment_id)
        assert exc_info.value.error_code == "PAYMENT_ALREADY_DELETED"

    def test_approve_nonexistent_payment_raises(self):
        ContractService.create_contract(_contract_data())
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.approve_payment_record("C001", "pay_nonexistent")
        assert exc_info.value.error_code == "PAYMENT_NOT_FOUND"


# ========== BF-053 回归:付款金额单一重算实现 ==========


@pytest.mark.django_db
class TestPaymentAmountRecalculation:
    """CT-4 回归:delete/approve 必须与 add 同走 _recalc_paid_amounts"""

    def test_delete_payment_reduces_amount_paid(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        payment_id = json.loads(contract.paid_record)["payments"][0]["id"]
        result = ContractService.delete_payment_record("C001", payment_id)
        assert result.amount_paid == Decimal("0")
        assert result.amount_unpaid == Decimal("50000.00")

    def test_delete_partial_payment_keeps_remainder(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        contract = ContractService.add_payment_record("C001", Decimal("5000.00"), "尾款")
        first_id = json.loads(contract.paid_record)["payments"][0]["id"]
        result = ContractService.delete_payment_record("C001", first_id)
        assert result.amount_paid == Decimal("5000.00")
        assert result.amount_unpaid == Decimal("45000.00")

    def test_approve_keeps_amount_paid_unchanged(self):
        """Q-A 口径:pending 已计入 amount_paid,approve 不改变金额"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"))
        payment_id = json.loads(contract.paid_record)["payments"][0]["id"]
        result = ContractService.approve_payment_record("C001", payment_id)
        assert result.amount_paid == Decimal("10000.00")
        assert result.amount_unpaid == Decimal("40000.00")

    def test_recalc_uses_settlemented_price_basis(self):
        ContractService.create_contract(
            _contract_data(
                contract_amount=Decimal("50000.00"),
                settlemented_price=Decimal("45000.00"),
                contract_status="settlement_done",
            )
        )
        contract = ContractService.add_payment_record("C001", Decimal("10000.00"))
        payment_id = json.loads(contract.paid_record)["payments"][0]["id"]
        result = ContractService.delete_payment_record("C001", payment_id)
        assert result.amount_unpaid == Decimal("45000.00")

    def test_recalc_skips_legacy_text_entries(self):
        """旧格式纯文本付款记录无合法 amount,应跳过而非整笔重算崩溃"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = Contract.objects.get(contract_code="C001")
        contract.paid_record = json.dumps({"payments": ["2024-01-01 付款 1000元"]}, ensure_ascii=False)
        contract.save()
        result = ContractService.add_payment_record("C001", Decimal("2000.00"))
        assert result.amount_paid == Decimal("2000.00")

    def test_recalc_skips_malformed_amount(self):
        """dict 结构但 amount 非数值的历史脏数据,应跳过该条而非整笔崩溃"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = Contract.objects.get(contract_code="C001")
        contract.paid_record = json.dumps(
            {"payments": [{"id": "pay_x", "amount": "约三千", "status": "approved"}]},
            ensure_ascii=False,
        )
        contract.save()
        result = ContractService.add_payment_record("C001", Decimal("2000.00"))
        assert result.amount_paid == Decimal("2000.00")

    def test_recalc_tolerates_legacy_plain_text(self):
        """paid_record 为非法 JSON 纯文本时,重算应降级为空明细而非抛错"""
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        contract = Contract.objects.get(contract_code="C001")
        contract.paid_record = "2024-01-01 首付 1000"
        contract.save()
        result = ContractService.add_payment_record("C001", Decimal("2000.00"))
        assert result.amount_paid == Decimal("2000.00")

    def test_recalc_tolerates_json_without_payments_key(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        obj = Contract.objects.get(contract_code="C001")
        obj.paid_record = json.dumps({"legacy": True}, ensure_ascii=False)
        obj.save()
        result = ContractService.add_payment_record("C001", Decimal("2000.00"))
        assert result.amount_paid == Decimal("2000.00")


# ========== BF-054 回归:付款日期/方式可指定 + 批量回填 ==========


@pytest.mark.django_db
class TestAddPaymentRecordOptions:
    def test_payment_date_honored(self):
        ContractService.create_contract(_contract_data())
        result = ContractService.add_payment_record(
            "C001", Decimal("100.00"), payment_date="2023-06-15", payment_method="cash"
        )
        entry = json.loads(result.paid_record)["payments"][0]
        assert entry["date"] == "2023-06-15"
        assert entry["payment_method"] == "cash"

    def test_defaults_when_options_omitted(self):
        ContractService.create_contract(_contract_data())
        result = ContractService.add_payment_record("C001", Decimal("100.00"))
        entry = json.loads(result.paid_record)["payments"][0]
        assert entry["payment_method"] == "bank_transfer"
        assert entry["status"] == "pending"
        assert entry["date"] == timezone.now().strftime("%Y-%m-%d")

    def test_created_at_is_ingest_time_not_payment_date(self):
        ContractService.create_contract(_contract_data())
        result = ContractService.add_payment_record("C001", Decimal("100.00"), payment_date="2020-01-01")
        entry = json.loads(result.paid_record)["payments"][0]
        assert entry["created_at"][:4] != "2020"


@pytest.mark.django_db
class TestAddPaymentRecordBatch:
    """Q-C:回填条目内部 add → approve,一律落在 approved 且 status 不开放为入参"""

    def test_batch_all_items_land_approved(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        result = ContractService.add_payment_record_batch(
            "C001",
            [
                {"amount": Decimal("1000.00"), "description": "首付款", "payment_date": "2023-01-10"},
                {"amount": Decimal("2000.00"), "description": "进度款", "payment_method": "check"},
            ],
        )
        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["fail_count"] == 0
        contract = Contract.objects.get(contract_code="C001")
        payments = json.loads(contract.paid_record)["payments"]
        assert [p["status"] for p in payments] == ["approved", "approved"]
        assert contract.amount_paid == Decimal("3000.00")

    def test_batch_preserves_payment_date_and_method(self):
        ContractService.create_contract(_contract_data())
        ContractService.add_payment_record_batch(
            "C001", [{"amount": Decimal("1000.00"), "payment_date": "2022-03-01", "payment_method": "cash"}]
        )
        entry = json.loads(Contract.objects.get(contract_code="C001").paid_record)["payments"][0]
        assert entry["date"] == "2022-03-01"
        assert entry["payment_method"] == "cash"

    def test_batch_invalid_item_isolated_not_rolled_back(self):
        ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        result = ContractService.add_payment_record_batch(
            "C001",
            [
                {"amount": Decimal("1000.00"), "description": "有效"},
                {"amount": Decimal("-5.00"), "description": "非法金额"},
            ],
        )
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INVALID_PAYMENT_AMOUNT"
        contract = Contract.objects.get(contract_code="C001")
        assert contract.amount_paid == Decimal("1000.00")

    def test_batch_nonexistent_contract_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            ContractService.add_payment_record_batch("NOPE", [{"amount": Decimal("1.00")}])
        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"


# ========== BF-055 / 决策 2a 回归:创建期初已付规范化 ==========


@pytest.mark.django_db
class TestCreateContractOpeningPaid:
    def test_opening_paid_becomes_approved_record(self):
        result = ContractService.create_contract(_contract_data(amount_paid=Decimal("3000.00")))
        entry = json.loads(result.paid_record)["payments"][0]
        assert entry["status"] == "approved"
        assert entry["payment_method"] == "opening_balance"
        assert entry["description"] == "期初已付"
        assert result.amount_paid == Decimal("3000.00")
        assert result.amount_unpaid == Decimal("7000.00")

    def test_opening_paid_date_defaults_to_contract_start(self):
        result = ContractService.create_contract(_contract_data(amount_paid=Decimal("3000.00")))
        assert json.loads(result.paid_record)["payments"][0]["date"] == "2024-01-01"

    def test_no_opening_paid_leaves_paid_record_untouched(self):
        result = ContractService.create_contract(_contract_data())
        assert result.amount_paid == Decimal("0")
        assert not result.paid_record  # 模型默认 NULL,存量行为不变

    def test_no_opening_paid_still_computes_amount_unpaid(self):
        """新建合同即便无期初已付,amount_unpaid 也应为全额(D1 同源分叉修复)"""
        result = ContractService.create_contract(_contract_data(contract_amount=Decimal("10000.00")))
        assert result.amount_unpaid == Decimal("10000.00")

    def test_opening_paid_not_kept_as_direct_input_key(self):
        """amount_paid 为弹出后消费,不得残留为裸写字段"""
        data = _contract_data(amount_paid=Decimal("3000.00"))
        result = ContractService.create_contract(data)
        assert "amount_paid" not in data
        assert Contract.objects.get(recordcode=result.recordcode).amount_paid == Decimal("3000.00")
