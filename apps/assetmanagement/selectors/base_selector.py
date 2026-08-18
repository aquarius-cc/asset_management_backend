"""
基础查询选择器

提供仓库、合同、硬盘序列号、仪表盘的查询方法。
"""

from typing import Any

from django.db.models import Count, QuerySet, Sum

from apps.assetmanagement.models import Asset, Contract, HardDiskSN, Storage
from core.department_scope import get_asset_linked_queryset_for_user


class StorageSelector:
    """仓库查询选择器"""

    @staticmethod
    def get_all_storages() -> QuerySet[Storage]:
        return Storage.objects.filter(is_deleted=False)

    @staticmethod
    def get_storage_by_code(storage_code: str) -> Storage | None:
        try:
            return Storage.objects.get(storage_code=storage_code, is_deleted=False)
        except Storage.DoesNotExist:
            return None

    @staticmethod
    def get_storages_by_type(storage_type: str) -> QuerySet[Storage]:
        return Storage.objects.filter(storage_type=storage_type, is_deleted=False)

    @staticmethod
    def exists_by_code(storage_code: str) -> bool:
        # 【P0-21 修复】显式过滤 is_deleted=False,防御性编码
        return Storage.objects.filter(storage_code=storage_code, is_deleted=False).exists()

    @staticmethod
    def exists_by_name(storage_name: str) -> bool:
        return Storage.objects.filter(storage_name=storage_name, is_deleted=False).exists()

    @staticmethod
    def search_storages_by_keyword(keyword: str) -> QuerySet[Storage]:
        from django.db.models import Q

        return Storage.objects.filter(
            Q(storage_code__icontains=keyword)
            | Q(storage_name__icontains=keyword)
            | Q(storage_address__icontains=keyword),
            is_deleted=False,
        )


class ContractSelector:
    """合同查询选择器"""

    @staticmethod
    def get_all_contracts() -> QuerySet[Contract]:
        return Contract.objects.filter(is_deleted=False)

    @staticmethod
    def get_contract_by_code(contract_code: str) -> Contract | None:
        try:
            return Contract.objects.get(contract_code=contract_code, is_deleted=False)
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


class HardDiskSNSelector:
    """硬盘序列号查询选择器"""

    @staticmethod
    def get_queryset_for_user(user):
        """RBAC 行级过滤(硬盘通过 asset_recordcode 关联到 Asset)"""
        return get_asset_linked_queryset_for_user(user, HardDiskSN.objects.filter(is_deleted=False))

    @staticmethod
    def get_by_recordcode(recordcode: str) -> HardDiskSN | None:
        """按 recordcode 查询单条"""
        try:
            return HardDiskSN.objects.get(recordcode=recordcode, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def get_by_recordcodes(recordcodes: list[str]) -> dict[str, HardDiskSN]:
        """按 recordcode 批量查询(返回 {recordcode: HardDiskSN} 映射)"""
        records = HardDiskSN.objects.filter(recordcode__in=recordcodes, is_deleted=False)
        return {record.recordcode: record for record in records}

    @staticmethod
    def get_by_pk(pk: int) -> HardDiskSN | None:
        """按主键查询"""
        try:
            return HardDiskSN.objects.get(pk=pk, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def get_by_sn_code(sn_code: str) -> HardDiskSN | None:
        """按序列号查询"""
        try:
            return HardDiskSN.objects.get(harddisk_sn_code=sn_code, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def exists_by_sn_code(sn_code: str) -> bool:
        """检查序列号是否已存在"""
        return HardDiskSN.objects.filter(harddisk_sn_code=sn_code, is_deleted=False).exists()

    @staticmethod
    def get_existing_sn_codes(sn_codes: list[str]) -> set[str]:
        """批量查询已存在的序列号集合"""
        if not sn_codes:
            return set()
        return set(
            HardDiskSN.objects.filter(harddisk_sn_code__in=sn_codes, is_deleted=False).values_list(
                "harddisk_sn_code", flat=True
            )
        )

    @staticmethod
    def get_by_asset(asset_recordcode: str) -> QuerySet[HardDiskSN]:
        """查询某资产的所有硬盘"""
        return HardDiskSN.objects.filter(asset_recordcode=asset_recordcode, is_deleted=False).order_by(
            "harddisk_sn_code"
        )

    @staticmethod
    def get_by_asset_code(asset_code: str) -> QuerySet[HardDiskSN]:
        """按资产编码查询所有硬盘"""
        return HardDiskSN.objects.filter(
            asset_recordcode__asset_code=asset_code,
            asset_recordcode__is_deleted=False,
            is_deleted=False,
        ).order_by("harddisk_sn_code")

    @staticmethod
    def count_by_asset(asset_recordcode: str) -> int:
        """统计某资产的硬盘数量"""
        return HardDiskSN.objects.filter(asset_recordcode=asset_recordcode, is_deleted=False).count()

    @staticmethod
    def get_by_status(status: str) -> QuerySet[HardDiskSN]:
        """按状态查询"""
        return HardDiskSN.objects.filter(harddisk_status=status, is_deleted=False)


class DashboardSelector:
    """仪表盘查询选择器"""

    @staticmethod
    def get_statistics() -> dict[str, Any]:
        asset_stats = Asset.objects.filter(is_deleted=False).aggregate(
            total=Count("id"), total_value=Sum("asset_purchase_price")
        )
        status_counts = (
            Asset.objects.filter(is_deleted=False).values("asset_current_status").annotate(count=Count("id"))
        )
        status_dict = {item["asset_current_status"]: item["count"] for item in status_counts}
        return {
            "total_assets": asset_stats["total"] or 0,
            "total_value": asset_stats["total_value"] or 0,
            "in_store": status_dict.get("in_store", 0),
            "in_use": status_dict.get("in_use", 0),
            "recycled_pending": status_dict.get("recycled_pending", 0),
            "damaged": status_dict.get("damaged", 0),
            "scrapped": status_dict.get("scrapped", 0),
        }

    @staticmethod
    def get_overview_statistics() -> dict[str, Any]:
        """获取仪表盘概览统计 — 资产 + 合同 + 状态分布 + 月度/累计操作数"""
        from django.utils import timezone

        from apps.assetmanagement.models import OutAsset, RecycleAsset

        now = timezone.now()

        asset_stats = Asset.objects.filter(is_deleted=False).aggregate(
            total=Count("id"), total_value=Sum("asset_purchase_price")
        )
        contract_stats = Contract.objects.filter(is_deleted=False).aggregate(total=Count("id"))

        # 按状态分组（一次查询覆盖全部 8 种状态）
        status_counts = dict(
            Asset.objects.filter(is_deleted=False)
            .values_list("asset_current_status")
            .annotate(count=Count("id"))
            .values_list("asset_current_status", "count")
        )

        STATUS_LABELS = {
            "in_store": "在库",
            "in_use": "在用",
            "recycled_pending": "已回收待发放",
            "broken": "已损坏",
            "repairing": "维修中",
            "lost": "已遗失",
            "damaged": "待报废",
            "scrapped": "已报废",
        }
        status_distribution = {
            code: {"name": label, "count": status_counts.get(code, 0)}
            for code, label in STATUS_LABELS.items()
        }

        # 月度 / 累计操作数
        monthly_distributed = OutAsset.objects.filter(
            is_deleted=False, outasset_date__year=now.year, outasset_date__month=now.month
        ).count()
        monthly_recycled = RecycleAsset.objects.filter(
            is_deleted=False, recycle_asset_date__year=now.year, recycle_asset_date__month=now.month
        ).count()
        total_distributed = OutAsset.objects.filter(is_deleted=False).count()
        total_recycled = RecycleAsset.objects.filter(is_deleted=False).count()

        return {
            "total_assets": asset_stats["total"] or 0,
            "total_value": asset_stats["total_value"] or 0,
            "total_contracts": contract_stats["total"] or 0,
            "active_assets": status_counts.get("in_use", 0),
            "in_stock_assets": status_counts.get("in_store", 0),
            "monthly_distributed": monthly_distributed,
            "monthly_recycled": monthly_recycled,
            "pending_waste": status_counts.get("damaged", 0),
            "wasted_assets": status_counts.get("scrapped", 0),
            "total_recycled": total_recycled,
            "total_distributed": total_distributed,
            "status_distribution": status_distribution,
            "timestamp": now.isoformat(),
        }

    @staticmethod
    def get_recent_out_assets(limit: int = 10) -> list:
        """获取最近出库记录"""
        from apps.assetmanagement.models import OutAsset

        outassets = (
            OutAsset.objects.filter(is_deleted=False)
            .select_related(
                "asset_recordcode",
                "outasset_applicant_recordcode",
                "outasset_applicant_recordcode__employee_department",
            )
            .order_by("-outasset_date")[:limit]
        )
        return [
            {
                "id": oa.pk,
                "recordcode": oa.recordcode,
                "asset_code": oa.asset_recordcode.asset_code if oa.asset_recordcode else None,
                "asset_name": oa.asset_recordcode.asset_name if oa.asset_recordcode else None,
                "outasset_date": oa.outasset_date,
                "outasset_type": oa.outasset_type,
                "recipient_name": (
                    oa.outasset_applicant_recordcode.employee_name
                    if oa.outasset_applicant_recordcode
                    else None
                ),
                "department_name": (
                    oa.outasset_applicant_recordcode.employee_department.department_name
                    if oa.outasset_applicant_recordcode
                    and oa.outasset_applicant_recordcode.employee_department
                    else None
                ),
            }
            for oa in outassets
        ]

    @staticmethod
    def get_recent_recycle_assets(limit: int = 10) -> list:
        """获取最近回收记录"""
        from apps.assetmanagement.models import RecycleAsset

        recycles = (
            RecycleAsset.objects.filter(is_deleted=False)
            .select_related(
                "asset_recordcode",
                "outasset_recordcode",
                "operator_employee",
                "operator_employee__employee_department",
            )
            .order_by("-recycle_asset_date")[:limit]
        )
        return [
            {
                "id": r.pk,
                "recordcode": r.recordcode,
                "asset_code": r.asset_recordcode.asset_code if r.asset_recordcode else None,
                "asset_name": r.asset_recordcode.asset_name if r.asset_recordcode else None,
                "recycle_asset_date": r.recycle_asset_date,
                "returner_name": (
                    r.operator_employee.employee_name if r.operator_employee else None
                ),
                "department_name": (
                    r.operator_employee.employee_department.department_name
                    if r.operator_employee and r.operator_employee.employee_department
                    else None
                ),
            }
            for r in recycles
        ]

    @staticmethod
    def get_asset_trend(
        days: int = 30,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取资产趋势数据(按日统计)

        支持两种模式：
        1. 日期范围模式：传入 start_date/end_date (YYYY-MM-DD)，返回该范围内每日数据
        2. 天数模式：传入 days，返回最近 N 天数据（默认）

        返回格式对齐前端 types/dashboard.ts AssetTrendData：
        [{"date": "YYYY-MM-DD", "new_assets": N, "distributed": 0, "recovered": 0, "scrapped": 0}]
        注：distributed/recovered/scrapped 暂无独立数据源，填 0 占位。
        """
        from datetime import date, timedelta

        from django.db.models.functions import TruncDate
        from django.utils import timezone

        if start_date and end_date:
            range_start = date.fromisoformat(start_date)
            range_end = date.fromisoformat(end_date)
        else:
            range_end = timezone.now().date()
            range_start = range_end - timedelta(days=days)

        daily_creates = (
            Asset.objects.filter(is_deleted=False, created_at__date__gte=range_start, created_at__date__lte=range_end)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        create_map = {item["date"].isoformat(): item["count"] for item in daily_creates}

        trend_data = []
        current_date = range_start
        while current_date <= range_end:
            date_str = current_date.isoformat()
            trend_data.append(
                {
                    "date": date_str,
                    "new_assets": create_map.get(date_str, 0),
                    "distributed": 0,
                    "recovered": 0,
                    "scrapped": 0,
                }
            )
            current_date += timedelta(days=1)

        return trend_data

    @staticmethod
    def get_department_distribution() -> list[dict[str, Any]]:
        """获取资产按部门分布统计

        返回格式对齐前端 types/dashboard.ts 内联类型：
        [{"department_name": str, "asset_count": int, "percentage": float}]
        """
        dept_stats = (
            Asset.objects.filter(is_deleted=False, asset_manager_recordcode__isnull=False)
            .values("asset_manager_recordcode__employee_department__department_name")
            .annotate(asset_count=Count("id"))
            .order_by("-asset_count")
        )

        total = sum(item["asset_count"] for item in dept_stats) or 1
        return [
            {
                "department_name": item["asset_manager_recordcode__employee_department__department_name"] or "未知",
                "asset_count": item["asset_count"],
                "percentage": round(item["asset_count"] / total * 100, 1),
            }
            for item in dept_stats
        ]

    @staticmethod
    def get_type_distribution() -> list[dict[str, Any]]:
        """获取资产按类型分布统计

        返回格式对齐前端 types/dashboard.ts 内联类型：
        [{"type_name": str, "count": int, "percentage": float}]
        """
        type_stats = (
            Asset.objects.filter(is_deleted=False, asset_type_recordcode__isnull=False)
            .values("asset_type_recordcode__type_name")
            .annotate(asset_count=Count("id"))
            .order_by("-asset_count")
        )

        total = sum(item["asset_count"] for item in type_stats) or 1
        return [
            {
                "type_name": item["asset_type_recordcode__type_name"],
                "count": item["asset_count"],
                "percentage": round(item["asset_count"] / total * 100, 1),
            }
            for item in type_stats
        ]

    @staticmethod
    def get_expiring_assets(days: int = 30) -> list[dict[str, Any]]:
        """获取即将到期的资产(保修期即将结束)

        返回格式对齐前端 types/dashboard.ts ExpiringAsset：
        [{"id": int, "asset_code": str, "asset_name": str, "expire_date": str, "days_until_expire": int}]
        """
        from datetime import date

        from dateutil.relativedelta import relativedelta

        expiring_assets = (
            Asset.objects.filter(is_deleted=False, asset_warranty_period__gt=0, asset_purchase_date__isnull=False)
            .order_by("asset_purchase_date")[:50]
        )

        result = []
        for asset in expiring_assets:
            warranty_end = asset.asset_purchase_date + relativedelta(months=asset.asset_warranty_period * 12)
            days_remaining = (warranty_end - date.today()).days

            if 0 <= days_remaining <= days:
                result.append(
                    {
                        "id": asset.id,
                        "asset_code": asset.asset_code,
                        "asset_name": asset.asset_name,
                        "expire_date": warranty_end.isoformat(),
                        "days_until_expire": days_remaining,
                    }
                )

        return sorted(result, key=lambda x: x["days_until_expire"])

    @staticmethod
    def get_maintenance_reminders() -> list[dict[str, Any]]:
        """获取维护提醒数据

        返回格式对齐前端 types/dashboard.ts MaintenanceReminder：
        [{"id": int, "asset_code": str, "asset_name": str, "maintenance_date": str, "type": str}]
        注：maintenance_date 取 asset_entry_date（入库日期），type 暂固定为 "定期检查"。
        """
        from django.utils import timezone

        now = timezone.now().date()

        assets = (
            Asset.objects.filter(is_deleted=False, asset_current_status="in_use", asset_entry_date__isnull=False)
            .order_by("asset_entry_date")[:50]
        )

        result = []
        for asset in assets:
            usage_months = (now.year - asset.asset_entry_date.year) * 12 + (now.month - asset.asset_entry_date.month)

            if usage_months >= 24:
                result.append(
                    {
                        "id": asset.id,
                        "asset_code": asset.asset_code,
                        "asset_name": asset.asset_name,
                        "maintenance_date": asset.asset_entry_date.isoformat(),
                        "type": "定期检查",
                    }
                )

        return sorted(result, key=lambda x: x["maintenance_date"])
