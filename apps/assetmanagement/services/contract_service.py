"""
合同管理服务

提供合同管理的业务逻辑,包括付款记录管理等。
"""

import copy
import json
import uuid
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.models import Contract
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.state_machine.contract_fsm import ContractFSM, ContractInvalidTransitionError
from core.audit_service import GenericAuditService
from core.batch_mixins import BatchOperationMixin
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError


def _parse_paid_record(raw: str | None) -> dict[str, Any]:
    """解析 paid_record,兼容纯文本旧格式"""
    if not raw:
        return {"payments": []}
    try:
        data = json.loads(raw)
        if "payments" not in data:
            data["payments"] = []
        return data  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {"payments": []}


class ContractService:
    """
    合同管理服务

    提供合同管理的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_contract(
        contract_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Contract:
        """
        创建单个合同

        Args:
            contract_data: 合同数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            Contract: 创建成功的合同实例

        Raises:
            AppValidationError: 合同编码已存在时抛出
        """
        contract_code = contract_data.get("contract_code")

        if ContractSelector.exists_by_code(contract_code):  # type: ignore[arg-type]
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
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return contract  # type: ignore[no-any-return]

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

        current_data = _parse_paid_record(contract.paid_record)
        payment = {
            "id": f"pay_{uuid.uuid4().hex[:12]}",
            "date": timezone.now().strftime("%Y-%m-%d"),
            "amount": str(amount),
            "description": description,
            "payment_method": "bank_transfer",
            "status": "pending",
            "created_at": timezone.now().isoformat(),
        }
        current_data["payments"].append(payment)
        contract.paid_record = json.dumps(current_data, ensure_ascii=False)

        contract.amount_paid = (contract.amount_paid or 0) + amount
        # 自动计算未付金额
        if (
            contract.contract_status in ("settlement_done", "final_check", "project_finished")
            and contract.settlemented_price
        ):
            contract.amount_unpaid = contract.settlemented_price - contract.amount_paid
        else:
            contract.amount_unpaid = (contract.contract_amount or 0) - contract.amount_paid

        contract.save()
        return contract

    @staticmethod
    @transaction.atomic
    def update_settlement_status(
        contract_code: str,
        status: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Contract:
        """
        更新合同状态

        Args:
            contract_code: 合同编码
            status: 合同状态
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

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
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return contract

    @staticmethod
    def get_contract_statistics() -> dict[str, Any]:
        """获取合同统计信息"""
        return ContractSelector.get_contract_statistics()

    @staticmethod
    @transaction.atomic
    def delete_contract(
        contract_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        """
        删除合同(软删除)

        Args:
            contract_code: 合同编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract or contract.is_deleted:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在或已删除", error_code="CONTRACT_NOT_FOUND")

        # 【P2-14 修复】删除前检查关联资产,防止数据不一致
        from apps.assetmanagement.models import Asset

        if Asset.objects.filter(asset_contract_recordcode=contract, is_deleted=False).exists():
            raise AppValidationError(detail="合同存在关联资产,不允许删除", error_code="HAS_RELATED_ASSETS")

        GenericAuditService.log_delete(
            record_code=contract.contract_code,
            app_label="contract",
            description=f"删除合同: {contract.contract_name}",
            before_data={
                "contract_code": contract.contract_code,
                "contract_name": contract.contract_name,
            },
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        contract.delete()

    @staticmethod
    def batch_create_contract(
        contract_data_list: list[dict[str, Any]],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> dict[str, Any]:
        """
        【新增】批量创建合同(逐条独立执行,返回详细结果)

        Args:
            contract_data_list: 合同数据列表

        Returns:
            Dict[str, Any]: 批量创建结果
        """
        if len(contract_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        def _create_item(idx: int, contract_data: Any) -> Contract:
            return ContractService.create_contract(
                copy.deepcopy(contract_data),
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_execute(
            items=contract_data_list,
            process_fn=_create_item,
            max_batch_size=MAX_BATCH_SIZE,
        )

    @staticmethod
    def batch_delete_contract(
        contract_codes: list[str],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> dict[str, Any]:
        """
        批量删除合同(软删除,逐条独立执行)
        """

        def _delete_item(contract_code: str) -> None:
            ContractService.delete_contract(
                contract_code,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_delete_execute(
            ids=contract_codes,
            process_fn=_delete_item,
            max_batch_size=100,
        )

    @staticmethod
    @transaction.atomic
    def delete_payment_record(contract_code: str, payment_id: str) -> Contract:
        """
        删除支付记录(软删除:status → deleted)

        Args:
            contract_code: 合同编码
            payment_id: 支付记录 ID

        Returns:
            Contract: 更新后的合同实例
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        data = _parse_paid_record(contract.paid_record)
        for p in data["payments"]:
            if p["id"] == payment_id:
                p["status"] = "deleted"
                break
        else:
            raise AppValidationError(detail="支付记录不存在", error_code="PAYMENT_NOT_FOUND")

        contract.paid_record = json.dumps(data, ensure_ascii=False)
        contract.save(update_fields=["paid_record", "updated_at"])
        return contract

    @staticmethod
    @transaction.atomic
    def approve_payment_record(contract_code: str, payment_id: str) -> Contract:
        """
        审核通过支付记录(status → approved)

        Args:
            contract_code: 合同编码
            payment_id: 支付记录 ID

        Returns:
            Contract: 更新后的合同实例
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        data = _parse_paid_record(contract.paid_record)
        for p in data["payments"]:
            if p["id"] == payment_id:
                if p["status"] == "deleted":
                    raise AppValidationError(
                        detail="已删除的支付记录不可审核", error_code="PAYMENT_ALREADY_DELETED"
                    )
                p["status"] = "approved"
                break
        else:
            raise AppValidationError(detail="支付记录不存在", error_code="PAYMENT_NOT_FOUND")

        contract.paid_record = json.dumps(data, ensure_ascii=False)
        contract.save(update_fields=["paid_record", "updated_at"])
        return contract
