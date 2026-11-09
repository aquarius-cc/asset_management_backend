"""合同支付域审计留痕(M-05) —— contract_service.py 支付审计载荷的唯一实现

口径(冻结决策①②): 枚举复用 add/batch→update、delete→delete、approve→approve;
细分载体 payment_action: add/batch/approve 走 after_data, delete 走 before_data
(log_delete 既有形参面仅含 before_data)。on_commit 落盘语义由 GenericAuditService 统一承载。
"""

from decimal import Decimal
from typing import Any

from apps.assetmanagement.models import Contract
from core.audit_service import GenericAuditService


def log_payment_added(
    contract: Contract,
    entry: dict[str, Any],
    amount: Decimal,
    *,
    operator_jobcode: str,
    operator_name: str | None = None,
) -> None:
    """付款记录新增→update 审计

    【M-05 收口】operator_jobcode 为 kw-only 必填(对齐 M-07 形态):
    防新调用方忘传即落一条无操作人审计行。
    """
    GenericAuditService.log_update(
        record_code=contract.contract_code,
        app_label="contract",
        description=f"付款记录新增: {entry['id']}",
        after_data={
            "payment_action": "add",
            "payment_id": entry["id"],
            "amount": str(amount),
            "payment_date": entry["date"],
        },
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
    )


def log_payment_batch_summary(
    contract_code: str,
    result: dict[str, Any],
    *,
    operator_jobcode: str,
    operator_name: str | None = None,
) -> None:
    """批量回填→update 审计,1 条请求级汇总(冻结决策②);operator_jobcode kw-only 必填(对齐 M-07)"""
    GenericAuditService.log_update(
        record_code=contract_code,
        app_label="contract",
        description=f"历史付款回填汇总: 成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        after_data={
            "payment_action": "batch",
            "total": result["total"],
            "success_count": result["success_count"],
            "fail_count": result["fail_count"],
            "payment_ids": [item["id"] for item in result["success_items"]],
        },
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
    )


def log_payment_deleted(
    contract: Contract,
    payment_id: str,
    amount: str | None,
    *,
    operator_jobcode: str,
    operator_name: str | None = None,
) -> None:
    """付款记录删除→delete 审计,载体 before_data;operator_jobcode kw-only 必填(对齐 M-07)"""
    GenericAuditService.log_delete(
        record_code=contract.contract_code,
        app_label="contract",
        description=f"付款记录删除: {payment_id}",
        before_data={
            "payment_action": "delete",
            "payment_id": payment_id,
            "amount": amount,
        },
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
    )


def log_payment_approved(
    contract: Contract,
    payment_id: str,
    *,
    operator_jobcode: str,
    operator_name: str | None = None,
) -> None:
    """付款记录审核→approve 审计;operator_jobcode kw-only 必填(对齐 M-07)"""
    GenericAuditService.log_approve(
        record_code=contract.contract_code,
        app_label="contract",
        description=f"付款记录审核通过: {payment_id}",
        after_data={"payment_action": "approve", "payment_id": payment_id},
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
    )
