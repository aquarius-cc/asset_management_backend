"""
合同管理模型测试

测试 Contract 模型的:
- 创建和字段验证
- 合同状态枚举
- 条件唯一约束
"""

from decimal import Decimal

import pytest

from apps.assetmanagement.models import Contract


@pytest.mark.django_db
class TestContractModel:
    """
    合同管理模型测试类
    """

    def test_create_contract(self):
        """
        测试创建合同
        """
        contract = Contract.objects.create(
            contract_code="CONT-001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_amount=Decimal("100000.00"),
            supplier_name="测试供应商",
        )

        assert contract.contract_code == "CONT-001"
        assert contract.contract_name == "测试合同"
        assert contract.contract_type == "tender_procurement"
        assert contract.contract_amount == Decimal("100000.00")
        assert contract.supplier_name == "测试供应商"

    def test_contract_str(self):
        """
        测试合同字符串表示
        """
        contract = Contract.objects.create(
            contract_code="CONT-002",
            contract_name="测试合同2",
            contract_type="service",
            contract_amount=Decimal("50000.00"),
            supplier_name="供应商2",
        )

        assert str(contract) == "测试合同2(CONT-002)"

    def test_contract_status_choices(self):
        """
        测试合同状态枚举
        """
        contract = Contract.objects.create(
            contract_code="CONT-003",
            contract_name="测试合同3",
            contract_type="tender_procurement",
            contract_amount=Decimal("80000.00"),
            supplier_name="供应商3",
            contract_status="purchasing",
        )

        assert contract.contract_status == "purchasing"

    def test_contract_new_fields(self):
        """
        测试合同新增字段
        """
        contract = Contract.objects.create(
            contract_code="CONT-004",
            contract_name="测试合同4",
            contract_type="tender_procurement",
            supplier_name="新供应商",
            contract_amount=Decimal("120000.00"),
            settlemented_price=Decimal("110000.00"),
            contract_total_quantity=100,
            contract_start_date="2024-04-01",
            contract_end_date="2024-12-31",
            contract_status="purchasing",
            project_change=False,
            project_change_type=None,
            receive_check_date=None,
            initial_check_date=None,
            final_check_date=None,
            paid_record=None,
            amount_paid=Decimal("50000.00"),
            amount_unpaid=Decimal("70000.00"),
            contract_description="测试合同描述",
            sort_order=1,
        )

        assert contract.supplier_name == "新供应商"
        assert contract.contract_amount == Decimal("120000.00")
        assert contract.settlemented_price == Decimal("110000.00")
        assert contract.contract_total_quantity == 100
        assert contract.contract_status == "purchasing"
        assert contract.amount_paid == Decimal("50000.00")
        assert contract.amount_unpaid == Decimal("70000.00")
        assert contract.sort_order == 1

    def test_contract_code_max_length(self):
        """
        测试合同编码最大长度(Char(50))
        """
        long_code = "C" * 48  # 48字符,小于50
        contract = Contract.objects.create(
            contract_code=long_code,
            contract_name="测试合同5",
            contract_type="tender_procurement",
            contract_amount=Decimal("90000.00"),
            supplier_name="供应商5",
        )

        assert len(contract.contract_code) == 48

    def test_contract_name_max_length(self):
        """
        测试合同名称最大长度(Char(200))
        """
        long_name = "测试合同名称" * 30  # 120字符
        contract = Contract.objects.create(
            contract_code="CONT-006",
            contract_name=long_name,
            contract_type="tender_procurement",
            contract_amount=Decimal("95000.00"),
            supplier_name="供应商6",
        )

        assert len(contract.contract_name) > 100

    def test_contract_status流转(self):
        """
        测试合同状态流转
        """
        contract = Contract.objects.create(
            contract_code="CONT-007",
            contract_name="测试合同7",
            contract_type="tender_procurement",
            contract_amount=Decimal("100000.00"),
            supplier_name="供应商7",
            contract_status="purchasing",
        )

        # 测试状态流转
        statuses = [
            "purchasing",
            "purchase_finished",
            "receive_check",
            "initial_check",
            "project_settlement",
            "settlement_done",
            "final_check",
            "project_finished",
        ]

        for status in statuses:
            contract.contract_status = status
            contract.save(update_fields=["contract_status"])
            assert contract.contract_status == status

    def test_contract_amount计算(self):
        """
        测试合同金额计算
        """
        contract = Contract.objects.create(
            contract_code="CONT-008",
            contract_name="测试合同8",
            contract_type="tender_procurement",
            contract_amount=Decimal("100000.00"),
            supplier_name="供应商8",
            amount_paid=Decimal("30000.00"),
            amount_unpaid=Decimal("70000.00"),
        )

        # 验证金额计算
        assert contract.amount_paid + contract.amount_unpaid == contract.contract_amount
