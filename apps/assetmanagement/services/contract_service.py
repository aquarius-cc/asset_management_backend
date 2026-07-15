"""
合同管理服务

提供合同管理的业务逻辑，包括付款记录管理等。
"""

import copy
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.models import Contract
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.state_machine.contract_fsm import ContractFSM, ContractInvalidTransitionError
from core.audit_service import GenericAuditService
from core.batch_mixins import BatchOperationMixin
from core.exceptions import AppValidationError


class ContractService:
    """
    合同管理服务

    提供合同管理的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_contract(contract_data: dict[str, Any]) -> Contract:
        """
        创建单个合同

        Args:
            contract_data: 合同数据字典

        Returns:
            Contract: 创建成功的合同实例

        Raises:
            AppValidationError: 合同编码已存在时抛出
        """
        contract_code = contract_data.get("contract_code")

        if ContractSelector.exists_by_code(contract_code):
            raise AppValidationError(detail=f"合同编码 {contract_code} 已存在", error_code="DUPLICATE_CONTRACT_CODE")

        contract = Contract.objects.create(**contract_data)

        GenericAuditService.log_create(
            record_code=contract.contract_code,
            app_label="contract",
            description=f"创建合同: {contract.contract_name}",
            after_data={
                "contract_code": contract.contract_code,
                "contract_name": contract.contract_name,
                "contract_type": contract.contract_type,
            },
        )

        return contract

    @staticmethod
    @transaction.atomic
    def add_payment_record(contract_code: str, amount: Decimal, description: str = "") -> Contract:
        """
        添加付款记录

        Args:
            contract_code: 合同编码
            amount: 付款金额
            description: 付款说明

        Returns:
            Contract: 更新后的合同实例
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        if amount <= 0:
            raise AppValidationError(detail="付款金额必须大于0", error_code="INVALID_PAYMENT_AMOUNT")

        current_record = contract.paid_record or ""
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        new_record = f"{timestamp}: 付款 {amount} 元"
        if description:
            new_record += f" - {description}"
        new_record += "\n"
        contract.paid_record = current_record + new_record

        contract.amount_paid = (contract.amount_paid or 0) + amount
        # 自动计算未付金额
        if contract.contract_status in ("settlement_done", "final_check", "project_finished") and contract.settlemented_price:
            contract.amount_unpaid = contract.settlemented_price - contract.amount_paid
        else:
            contract.amount_unpaid = (contract.contract_amount or 0) - contract.amount_paid

        contract.save()
        return contract

    @staticmethod
    @transaction.atomic
    def update_settlement_status(contract_code: str, status: str) -> Contract:
        """
        更新合同状态

        Args:
            contract_code: 合同编码
            status: 合同状态

        Returns:
            Contract: 更新后的合同实例
        """
        valid_statuses = dict(Contract.CONTRACT_STATUS_CHOICES)
        if status not in valid_statuses:
            raise AppValidationError(detail=f"无效的合同状态: {status}", error_code="INVALID_CONTRACT_STATUS")

        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        before_status = contract.contract_status
        try:
            ContractFSM.transition(contract, status)
        except ContractInvalidTransitionError as e:
            raise AppValidationError(detail=str(e), error_code="INVALID_CONTRACT_TRANSITION")
        contract.save()

        GenericAuditService.log_update(
            record_code=contract.contract_code,
            app_label="contract",
            description=f"更新合同状态: {contract.contract_name}",
            before_data={"contract_status": before_status},
            after_data={"contract_status": status},
        )

        return contract

    @staticmethod
    def get_contract_statistics() -> dict[str, Any]:
        """获取合同统计信息"""
        return ContractSelector.get_contract_statistics()

    @staticmethod
    @transaction.atomic
    def delete_contract(contract_code: str) -> None:
        """
        删除合同（软删除）

        Args:
            contract_code: 合同编码
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract or contract.is_deleted:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在或已删除", error_code="CONTRACT_NOT_FOUND")

        # 【P2-14 修复】删除前检查关联资产，防止数据不一致
        from apps.assetmanagement.models import Asset

        if Asset.objects.filter(asset_contract_recordcode=contract, is_deleted=False).exists():
            raise AppValidationError(detail="合同存在关联资产，不允许删除", error_code="HAS_RELATED_ASSETS")

        GenericAuditService.log_delete(
            record_code=contract.contract_code,
            app_label="contract",
            description=f"删除合同: {contract.contract_name}",
            before_data={
                "contract_code": contract.contract_code,
                "contract_name": contract.contract_name,
            },
        )

        contract.delete()

    @staticmethod
    def batch_create_contract(
        contract_data_list: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        【新增】批量创建合同（逐条独立执行，返回详细结果）

        Args:
            contract_data_list: 合同数据列表

        Returns:
            Dict[str, Any]: 批量创建结果
        """
        MAX_BATCH_SIZE = 100
        if len(contract_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_items: list[Contract] = []
        fail_items: list[dict[str, Any]] = []

        for idx, contract_data in enumerate(contract_data_list):
            try:
                result = ContractService.create_contract(
                    copy.deepcopy(contract_data),
                )
                success_items.append(result)
            except AppValidationError as e:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": contract_data.get("row_number"),
                        "input_data": contract_data,
                        "error_code": e.error_code or "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                    }
                )
            except Exception:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": contract_data.get("row_number"),
                        "input_data": contract_data,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误，请稍后重试",
                    }
                )

        return {
            "total": len(contract_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items,
        }

    @staticmethod
    def batch_delete_contract(contract_codes: list[str]) -> dict[str, Any]:
        """
        批量删除合同（软删除，逐条独立执行）
        """

        def _delete_item(contract_code: str) -> None:
            ContractService.delete_contract(contract_code)

        return BatchOperationMixin.batch_delete_execute(
            ids=contract_codes,
            process_fn=_delete_item,
            max_batch_size=100,
        )
