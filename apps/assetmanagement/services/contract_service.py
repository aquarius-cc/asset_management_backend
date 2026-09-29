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
from apps.assetmanagement.selectors import AssetSelector, ContractSelector
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


def _build_payment_entry(
    amount: Decimal,
    description: str = "",
    *,
    payment_date: str | None = None,
    payment_method: str = "bank_transfer",
    status: str = "pending",
) -> dict[str, Any]:
    """构造单条付款记录(DR-1: 期初已付与常规付款共用同一构造函数)

    payment_date 缺省取当天(BF-054: 原实现硬编码 timezone.now,历史付款无法回填真实日期)。
    created_at 恒为「录入时间」,与 payment_date(付款发生时间)语义分离。
    """
    return {
        "id": f"pay_{uuid.uuid4().hex[:12]}",
        "date": payment_date or timezone.now().strftime("%Y-%m-%d"),
        "amount": str(amount),
        "description": description,
        "payment_method": payment_method,
        "status": status,
        "created_at": timezone.now().isoformat(),
    }


def _sum_active_paid(payments: list[Any]) -> Decimal:
    """汇总非 deleted 付款金额

    【Q-A 口径】含 pending,语义为「已登记付款额」而非「已核销额」——与既有
    add_payment_record 行为一致(新增即计入),故 delete 时扣减、approve 时不变。
    """
    total = Decimal("0")
    for payment in payments:
        if not isinstance(payment, dict) or payment.get("status") == "deleted":
            continue
        try:
            total += Decimal(str(payment.get("amount", "0")))
        except ArithmeticError:
            # 旧格式纯文本记录无合法 amount,跳过该条而非中断整笔重算
            continue
    return total


def _recalc_paid_amounts(contract: Contract) -> None:
    """按 paid_record 重算 amount_paid / amount_unpaid(BF-053 单一实现)

    【为何必须单一实现】此前仅 add_payment_record 做「增量 + 重算」,而
    delete_payment_record / approve_payment_record 只改 paid_record 不动金额,
    软删一笔付款后 amount_paid 仍含该笔且永不回落。三处现共用本函数。
    """
    payments = _parse_paid_record(contract.paid_record).get("payments", [])
    contract.amount_paid = _sum_active_paid(payments)
    if (
        contract.contract_status in ("settlement_done", "final_check", "project_finished")
        and contract.settlemented_price
    ):
        contract.amount_unpaid = contract.settlemented_price - contract.amount_paid
    else:
        contract.amount_unpaid = (contract.contract_amount or 0) - contract.amount_paid


def _apply_opening_paid(contract: Contract, opening_paid: str | int | float | Decimal | None) -> None:
    """把创建入口的期初已付金额规范化为一条 approved 期初付款记录

    调用方 create_contract 处的【BF-055 / 决策 2a】注释说明了为何要「弹出后规范化」
    而非裸写;本函数只负责该规范化的实现,与常规付款共用 _build_payment_entry(DR-1)。

    卫语句早返回等价于原式 ``opening_paid and Decimal(str(opening_paid)) > 0``:
    falsy 值短路返回,不会走到 ``Decimal(str(None))`` 这条 InvalidOperation 路径。
    非数值字符串(如 "abc")会抛 InvalidOperation——与拆分前一致,由 Serializer 先行校验兜底。
    """
    if not opening_paid or Decimal(str(opening_paid)) <= 0:
        return
    contract.paid_record = json.dumps(
        {
            "payments": [
                _build_payment_entry(
                    Decimal(str(opening_paid)),
                    "期初已付",
                    payment_date=str(contract.contract_start_date) if contract.contract_start_date else None,
                    payment_method="opening_balance",
                    status="approved",
                )
            ]
        },
        ensure_ascii=False,
    )
    contract.save(update_fields=["paid_record", "updated_at"])


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
            raise AppValidationError(detail=f"合同 {contract_code} 已存在", error_code="DUPLICATE_CONTRACT_CODE")

        # 【BF-055 / 决策 2a】amount_paid 在创建入口的语义是「期初已付金额」输入,
        # 而非反规范化字段的直接赋值。此处弹出后规范化为一条 approved 期初付款记录,
        # 再由 _recalc_paid_amounts 落库,使 amount_paid 恒等于「Σ 非 deleted 付款」——
        # 全路径不再有绕过明细表的裸写,重算因此恒等无损(无需区分「期初基线」,无 DB 迁移)。
        opening_paid = contract_data.pop("amount_paid", None)
        contract = Contract.objects.create(**contract_data)

        _apply_opening_paid(contract, opening_paid)

        # 重算无条件执行:新建合同即便无期初已付,amount_unpaid 也应为 contract_amount - 0,
        # 而非模型默认值 0(字段 help_text 明写「自动计算」)。此前该分支被关在 if 内,
        # 导致新建合同在首次付款之前 amount_unpaid 恒为 0,属 D1 同源的反规范化分叉。
        _recalc_paid_amounts(contract)
        contract.save(update_fields=["amount_paid", "amount_unpaid", "updated_at"])

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
    def add_payment_record(
        contract_code: str,
        amount: Decimal,
        description: str = "",
        *,
        payment_date: str | None = None,
        payment_method: str = "bank_transfer",
    ) -> Contract:
        """
        添加付款记录

        Args:
            contract_code: 合同编码
            amount: 付款金额
            description: 付款说明
            payment_date: 付款发生日期(YYYY-MM-DD),缺省取当天。
                【BF-054】原实现硬编码 timezone.now,历史付款无法回填真实日期。
            payment_method: 支付方式(自由文本,仅存于 paid_record 明细,不参与查询)。

        Returns:
            Contract: 更新后的合同实例
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        if amount <= 0:
            raise AppValidationError(detail="付款金额必须大于0", error_code="INVALID_PAYMENT_AMOUNT")

        current_data = _parse_paid_record(contract.paid_record)
        current_data["payments"].append(
            _build_payment_entry(
                amount,
                description,
                payment_date=payment_date,
                payment_method=payment_method,
            )
        )
        contract.paid_record = json.dumps(current_data, ensure_ascii=False)
        _recalc_paid_amounts(contract)

        contract.save()
        return contract

    @staticmethod
    @transaction.atomic
    def add_payment_record_batch(contract_code: str, payments: list[dict[str, Any]]) -> dict[str, Any]:
        """批量回填历史付款记录(DR-1: 循环框架复用 BatchOperationMixin,B-5 修法)

        【决策 Q-C】status 不开放为用户输入:每条内部执行 add → approve 两步,回填条目
        一律落在 approved。理由:① approved 保持「仅由 approve_payment_record 产生」这一
        单一入口,不开状态机后门;② approve 承载「谁批准了这笔付款」的业务控制,而
        paid_record 的 payment 结构无 approver 字段,直写会留下不可追溯的审批痕迹;
        ③ 调用方由「N 笔历史付款发 2N 次请求」降为 1 次,目标同样达成。
        需保留 pending 的历史条目时,调用方应改用单条 add_payment_record 端点。

        Args:
            contract_code: 合同编码
            payments: 付款条目列表,每项支持 amount / description / payment_date / payment_method

        Returns:
            Dict[str, Any]: 统一格式批量结果(total/success_count/fail_count/success_items/fail_items)
        """
        if not ContractSelector.get_contract_by_code(contract_code):
            raise AppValidationError(detail=f"合同 {contract_code} 不存在", error_code="CONTRACT_NOT_FOUND")

        def _add_item(idx: int, payment: Any) -> dict[str, Any]:
            added = ContractService.add_payment_record(
                contract_code,
                Decimal(str(payment["amount"])),
                str(payment.get("description") or ""),
                payment_date=payment.get("payment_date"),
                payment_method=str(payment.get("payment_method") or "bank_transfer"),
            )
            entry = _parse_paid_record(added.paid_record)["payments"][-1]
            approved = ContractService.approve_payment_record(contract_code, str(entry["id"]))
            return {
                "id": entry["id"],
                "amount": entry["amount"],
                "date": entry["date"],
                "status": "approved",
                "recordcode": approved.recordcode,
            }

        return BatchOperationMixin.batch_execute(
            items=payments,
            process_fn=_add_item,
            max_batch_size=MAX_BATCH_SIZE,
        )

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

        if AssetSelector.exists_by_contract(contract):
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
        # 【BF-053】软删必须重算金额:原实现只改 paid_record,amount_paid 仍含该笔且永不回落
        _recalc_paid_amounts(contract)
        contract.save(update_fields=["paid_record", "amount_paid", "amount_unpaid", "updated_at"])
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
                    raise AppValidationError(detail="已删除的支付记录不可审核", error_code="PAYMENT_ALREADY_DELETED")
                p["status"] = "approved"
                break
        else:
            raise AppValidationError(detail="支付记录不存在", error_code="PAYMENT_NOT_FOUND")

        contract.paid_record = json.dumps(data, ensure_ascii=False)
        # 【BF-053】与 delete 同理走共用重算:Q-A 口径下 pending 已计入 amount_paid,
        # 故 approve 不改变金额,但仍统一走单一实现,避免日后口径调整时再次分叉
        _recalc_paid_amounts(contract)
        contract.save(update_fields=["paid_record", "amount_paid", "amount_unpaid", "updated_at"])
        return contract
