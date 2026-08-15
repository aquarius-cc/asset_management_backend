"""
合同支付记录服务 - 提供合同支付记录的 CRUD 操作,支持 JSON 格式存储和乐观锁。

Class:
  - ContractPaymentService: 合同支付记录服务
    - add_payment: 添加支付记录
    - delete_payment: 删除支付记录
    - approve_payment: 审批支付记录
    - get_payment_count / get_total_paid: 查询统计
    - _validate_payment / _recalculate_totals: 内部校验与计算

调用链:
  本模块被 -> ContractViewSet(付款记录相关 action)调用
  本模块依赖 -> Contract, GenericAuditService, AppValidationError
"""

import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.models import Contract
from core.audit_service import GenericAuditService
from core.exceptions import AppValidationError, ResourceConflictError


logger = logging.getLogger(__name__)


class ContractPaymentService:
    """
    合同支付记录服务

    提供支付记录的添加、删除、审核、查询等功能。
    使用JSON格式存储支付记录,支持乐观锁防止并发冲突。
    """

    # 允许操作支付记录的合同状态
    ALLOWED_STATUS = [
        Contract.ContractStatus.PURCHASING,
        Contract.ContractStatus.PURCHASE_FINISHED,
        Contract.ContractStatus.RECEIVE_CHECK,
        Contract.ContractStatus.INITIAL_CHECK,
        Contract.ContractStatus.PROJECT_SETTLEMENT,
        Contract.ContractStatus.SETTLEMENT_DONE,
    ]

    # 最大支付记录数
    MAX_PAYMENT_RECORDS = 100

    def __init__(self, contract: Contract):
        self.contract = contract

    def get_paid_record(self, refresh: bool = False) -> dict[str, Any]:
        """
        获取支付记录

        Args:
            refresh: 是否强制从数据库刷新

        Returns:
            支付记录字典
        """
        default_record = {"payments": [], "total_paid": 0, "last_payment_date": None}

        if refresh:
            self.contract.refresh_from_db()

        if not self.contract.paid_record:
            return default_record

        record = self.contract.paid_record
        if not isinstance(record, dict):
            return default_record
        record.setdefault("payments", [])
        record.setdefault("total_paid", 0)
        record.setdefault("last_payment_date", None)
        return record

    def _validate_payment_id(self, payment_id: str) -> None:
        """
        校验支付记录ID格式

        Args:
            payment_id: 支付记录ID

        Raises:
            ValidationError: ID格式无效
        """
        if not payment_id or not isinstance(payment_id, str):
            raise AppValidationError(detail="支付记录ID不能为空", error_code="INVALID_PAYMENT_ID")

        # 校验UUID格式(标准UUID格式:8-4-4-4-12)
        import re

        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
        if not uuid_pattern.match(payment_id):
            raise AppValidationError(detail="支付记录ID格式无效", error_code="INVALID_PAYMENT_ID")

    def _validate_payment(self, payment_data: dict[str, Any]) -> None:
        """
        校验支付数据

        Args:
            payment_data: 支付数据

        Raises:
            ValidationError: 校验失败
        """
        # 金额校验
        amount = payment_data.get("amount")
        if amount is None:
            raise AppValidationError(detail="支付金额不能为空", error_code="INVALID_PAYMENT_AMOUNT")

        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise AppValidationError(detail="支付金额格式错误", error_code="INVALID_PAYMENT_AMOUNT")

        if amount_decimal <= 0:
            raise AppValidationError(detail="支付金额必须大于0", error_code="INVALID_PAYMENT_AMOUNT")

        if amount_decimal.as_tuple().exponent < -2:
            raise AppValidationError(detail="支付金额最多支持2位小数", error_code="INVALID_PAYMENT_AMOUNT")

        # 日期校验
        payment_date = payment_data.get("date")
        if not payment_date:
            raise AppValidationError(detail="支付日期不能为空", error_code="INVALID_PAYMENT_DATE")

        try:
            if isinstance(payment_date, str):
                pay_date = datetime.strptime(payment_date, "%Y-%m-%d").date()
            elif isinstance(payment_date, date):
                pay_date = payment_date
            else:
                raise ValueError("日期格式错误")
        except ValueError:
            raise AppValidationError(detail="支付日期格式错误,应为YYYY-MM-DD", error_code="INVALID_PAYMENT_DATE")

        if pay_date > date.today():
            raise AppValidationError(detail="支付日期不能晚于今天", error_code="INVALID_PAYMENT_DATE")

        if self.contract.contract_start_date and pay_date < self.contract.contract_start_date:
            raise AppValidationError(
                detail=f"支付日期不能早于合同签订日期{self.contract.contract_start_date}",
                error_code="INVALID_PAYMENT_DATE",
            )

    def _validate_contract_status(self) -> None:
        """
        验证合同状态

        Raises:
            ValidationError: 状态不允许操作
        """
        if self.contract.contract_status not in self.ALLOWED_STATUS:
            raise AppValidationError(
                detail=f"合同状态为{self.contract.get_contract_status_display()}时,不允许操作支付记录",
                error_code="INVALID_CONTRACT_STATUS",
            )

    def _recalculate_totals(self, record: dict[str, Any]) -> dict[str, Any]:
        """
        重新计算汇总

        Args:
            record: 支付记录

        Returns:
            更新后的支付记录
        """
        active_payments = [p for p in record["payments"] if p.get("status") != "deleted"]
        record["total_paid"] = sum(p["amount"] for p in active_payments)
        record["last_payment_date"] = active_payments[-1]["date"] if active_payments else None
        return record

    def _log_action(self, action_type: str, detail: dict[str, Any], operator: str) -> None:
        """
        记录审计日志

        Args:
            action_type: 操作类型
            detail: 操作详情
            operator: 操作人
        """
        GenericAuditService.log_update(
            record_code=self.contract.contract_code,
            app_label="contract",
            description=f"{action_type}: {json.dumps(detail, ensure_ascii=False)}",
            after_data=detail,
            operator_jobcode=operator,
        )

    def _get_payment_limit(self) -> Decimal | None:
        """
        获取支付金额上限

        根据合同状态和结算价格计算支付上限:
        - 结算完成/最终验收/项目结束状态:使用结算价格
        - 其他状态:使用合同金额

        Returns:
            支付金额上限,如果未设置则返回None
        """
        if (
            self.contract.contract_status
            in [
                Contract.ContractStatus.SETTLEMENT_DONE,
                Contract.ContractStatus.FINAL_CHECK,
                Contract.ContractStatus.PROJECT_FINISHED,
            ]
            and self.contract.settlemented_price
        ):
            return self.contract.settlemented_price
        else:
            return self.contract.contract_amount

    @transaction.atomic
    def add_payment(self, payment_data: dict[str, Any], operator: str = "system") -> dict[str, Any]:
        """
        添加支付记录

        Args:
            payment_data: 支付数据,包含date、amount、description等
            operator: 操作人

        Returns:
            更新后的支付记录

        Raises:
            ValidationError: 校验失败
            ResourceConflictError: 并发冲突
        """
        self._validate_contract_status()
        self._validate_payment(payment_data)

        original_version = self.contract.version
        record = self.get_paid_record()

        # 检查数量限制
        active_payments = [p for p in record["payments"] if p.get("status") != "deleted"]
        if len(active_payments) >= self.MAX_PAYMENT_RECORDS:
            raise AppValidationError(
                detail=f"支付记录数量已达上限{self.MAX_PAYMENT_RECORDS}条", error_code="PAYMENT_RECORDS_LIMIT_EXCEEDED"
            )

        # 校验付款累计上限
        amount = Decimal(str(payment_data["amount"]))
        new_total_paid = Decimal(str(record["total_paid"])) + amount

        payment_limit = self._get_payment_limit()

        if payment_limit is not None and new_total_paid > payment_limit:
            raise AppValidationError(
                detail=f"付款金额累计 {new_total_paid} 元超过合同限额 {payment_limit} 元",
                error_code="PAYMENT_EXCEED_LIMIT",
            )

        # 构建支付记录
        payment = {
            "id": str(uuid.uuid4()),
            "date": str(payment_data["date"]),
            "amount": float(amount),
            "description": payment_data.get("description", ""),
            "payment_method": payment_data.get("payment_method"),
            "operator": operator,
            "status": "pending",
            "created_at": timezone.now().isoformat(),
        }

        record["payments"].append(payment)
        record = self._recalculate_totals(record)

        # 计算未支付金额
        amount_unpaid = Decimal("0")
        if payment_limit is not None:
            amount_unpaid = payment_limit - Decimal(str(record["total_paid"]))
            amount_unpaid = max(amount_unpaid, Decimal("0"))

        # 乐观锁更新
        active_count = len([p for p in record["payments"] if p.get("status") != "deleted"])
        updated = Contract.objects.filter(recordcode=self.contract.recordcode, version=original_version).update(
            paid_record=record,
            amount_paid=Decimal(str(record["total_paid"])),
            amount_unpaid=amount_unpaid,
            has_payment=active_count > 0,
            version=original_version + 1,
        )

        if not updated:
            raise ResourceConflictError(detail="数据已被其他用户修改,请刷新后重试")

        # 记录审计日志
        self._log_action("添加支付记录", {"payment_id": payment["id"], "amount": float(amount)}, operator)

        return record

    @transaction.atomic
    def delete_payment(self, payment_id: str, operator: str = "system") -> dict[str, Any]:
        """
        软删除支付记录

        Args:
            payment_id: 支付记录ID
            operator: 操作人

        Returns:
            更新后的支付记录

        Raises:
            ValidationError: 校验失败
            ResourceConflictError: 并发冲突
        """
        self._validate_payment_id(payment_id)
        self._validate_contract_status()

        original_version = self.contract.version
        record = self.get_paid_record()

        # 查找并标记为删除
        payment_found = False
        for payment in record["payments"]:
            if payment["id"] == payment_id:
                if payment.get("status") == "approved":
                    raise AppValidationError(
                        detail="已审核的支付记录不能删除", error_code="APPROVED_PAYMENT_CANNOT_DELETE"
                    )
                payment["status"] = "deleted"
                payment["deleted_at"] = timezone.now().isoformat()
                payment["deleted_by"] = operator
                payment_found = True
                break

        if not payment_found:
            raise AppValidationError(detail=f"支付记录{payment_id}不存在", error_code="PAYMENT_NOT_FOUND")

        record = self._recalculate_totals(record)

        # 计算未支付金额
        amount_unpaid = Decimal("0")
        payment_limit = self._get_payment_limit()

        if payment_limit is not None:
            amount_unpaid = payment_limit - Decimal(str(record["total_paid"]))
            amount_unpaid = max(amount_unpaid, Decimal("0"))

        # 乐观锁更新
        updated = Contract.objects.filter(recordcode=self.contract.recordcode, version=original_version).update(
            paid_record=record,
            amount_paid=Decimal(str(record["total_paid"])),
            amount_unpaid=amount_unpaid,
            has_payment=len([p for p in record["payments"] if p.get("status") != "deleted"]) > 0,
            version=original_version + 1,
        )

        if not updated:
            raise ResourceConflictError(detail="数据已被其他用户修改,请刷新后重试")

        # 记录审计日志
        self._log_action("删除支付记录", {"payment_id": payment_id}, operator)

        return record

    @transaction.atomic
    def approve_payment(self, payment_id: str, approver: str = "system") -> dict[str, Any]:
        """
        审核支付记录

        Args:
            payment_id: 支付记录ID
            approver: 审核人

        Returns:
            更新后的支付记录

        Raises:
            ValidationError: 校验失败
            ConflictError: 并发冲突
        """
        self._validate_payment_id(payment_id)

        original_version = self.contract.version
        record = self.get_paid_record()

        # 查找并审核
        payment_found = False
        for payment in record["payments"]:
            if payment["id"] == payment_id:
                if payment.get("status") != "pending":
                    raise AppValidationError(detail="只有待审核的记录可以审核", error_code="INVALID_PAYMENT_STATUS")
                payment["status"] = "approved"
                payment["approved_by"] = approver
                payment["approved_at"] = timezone.now().isoformat()
                payment_found = True
                break

        if not payment_found:
            raise AppValidationError(detail=f"支付记录{payment_id}不存在", error_code="PAYMENT_NOT_FOUND")

        # 乐观锁更新
        active_count = len([p for p in record["payments"] if p.get("status") != "deleted"])
        updated = Contract.objects.filter(recordcode=self.contract.recordcode, version=original_version).update(
            paid_record=record, has_payment=active_count > 0, version=original_version + 1
        )

        if not updated:
            raise ResourceConflictError(detail="数据已被其他用户修改,请刷新后重试")

        # 记录审计日志
        self._log_action("审核支付记录", {"payment_id": payment_id, "approver": approver}, approver)

        return record

    def get_payment_count(self) -> int:
        """
        获取有效支付记录数量

        Returns:
            有效支付记录数量
        """
        record = self.get_paid_record()
        return len([p for p in record["payments"] if p.get("status") != "deleted"])

    def get_total_paid(self) -> Decimal:
        """
        获取已支付总额

        Returns:
            已支付总额
        """
        record = self.get_paid_record()
        return Decimal(str(record["total_paid"]))
