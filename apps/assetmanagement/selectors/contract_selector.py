"""
合同查询选择器

提供合同相关的查询与统计方法(从 base_selector.py 拆分)。
"""

from typing import Any

from django.db.models import Count, QuerySet, Sum

from apps.assetmanagement.models import Contract


class ContractSelector:
    """合同查询选择器"""

    @staticmethod
    def get_all_contracts() -> QuerySet[Contract]:
        return Contract.objects.filter(is_deleted=False)

    @staticmethod
    def get_contract_by_code(contract_code: str) -> Contract | None:
        try:
            return Contract.objects.get(contract_code=contract_code, is_deleted=False)  # type: ignore[no-any-return]
        except Contract.DoesNotExist:
            return None

    @staticmethod
    def search_contracts(keyword: str) -> QuerySet[Contract]:
        from django.db.models import Q

        return Contract.objects.filter(
            Q(contract_code__icontains=keyword)
            | Q(contract_name__icontains=keyword)
            | Q(supplier_name__icontains=keyword),
            is_deleted=False,
        )

    @staticmethod
    def get_contracts_by_type(contract_type: str) -> QuerySet[Contract]:
        return Contract.objects.filter(contract_type=contract_type, is_deleted=False)

    @staticmethod
    def exists_by_code(contract_code: str) -> bool:
        # 【P0-23 修复】显式过滤 is_deleted=False,防御性编码
        return Contract.objects.filter(contract_code=contract_code, is_deleted=False).exists()

    @staticmethod
    def get_contract_statistics() -> dict[str, Any]:
        total = Contract.objects.filter(is_deleted=False).count()
        type_counts = Contract.objects.filter(is_deleted=False).values("contract_type").annotate(count=Count("id"))
        settlement_counts = (
            Contract.objects.filter(is_deleted=False).values("contract_status").annotate(count=Count("id"))
        )
        total_value = (
            Contract.objects.filter(is_deleted=False).aggregate(Sum("contract_amount"))["contract_amount__sum"] or 0
        )
        return {
            "total_contracts": total,
            "total_value": total_value,
            "by_type": {item["contract_type"]: item["count"] for item in type_counts},
            "by_status": {item["contract_status"]: item["count"] for item in settlement_counts},
        }
