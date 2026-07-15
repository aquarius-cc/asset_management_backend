"""合同管理服务测试"""

import pytest
from decimal import Decimal

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
        c = ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        result = ContractService.add_payment_record("C001", Decimal("10000.00"), "首付款")
        assert result.amount_paid == Decimal("10000.00")
        assert result.amount_unpaid == Decimal("40000.00")
        assert "10000" in result.paid_record

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
        c = ContractService.create_contract(_contract_data(contract_amount=Decimal("50000.00")))
        ContractService.add_payment_record("C001", Decimal("10000.00"))
        result = ContractService.add_payment_record("C001", Decimal("5000.00"))
        assert result.amount_paid == Decimal("15000.00")
        assert result.amount_unpaid == Decimal("35000.00")

    def test_add_payment_settlement_status_uses_settlemented_price(self):
        c = ContractService.create_contract(
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
            storage_code="S_CON", storage_name="S_CON", storage_address="addr",
            storage_capacity=100, sort_order=0,
        )
        Asset.objects.create(
            asset_code="A_CON", asset_name="A_CON", asset_purchase_price=100,
            asset_purchase_date="2024-01-01", asset_entry_date="2024-01-01",
            asset_storage_recordcode=s, asset_type_recordcode=at,
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
        data = [{"contract_code": f"CC{i}", "contract_name": f"C{i}", "contract_amount": Decimal("100")} for i in range(101)]
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
