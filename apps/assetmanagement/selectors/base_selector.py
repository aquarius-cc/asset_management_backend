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
        # 【P0-21 修复】显式过滤 is_deleted=False，防御性编码
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
        # 【P0-23 修复】显式过滤 is_deleted=False，防御性编码
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
        """RBAC 行级过滤（硬盘通过 asset_recordcode 关联到 Asset）"""
        return get_asset_linked_queryset_for_user(user, HardDiskSN.objects.filter(is_deleted=False))

    @staticmethod
    def get_by_recordcode(recordcode: str) -> HardDiskSN | None:
        """按 recordcode 查询单条"""
        try:
            return HardDiskSN.objects.get(recordcode=recordcode, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

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
        return HardDiskSN.objects.filter(
            harddisk_sn_code=sn_code, is_deleted=False
        ).exists()

    @staticmethod
    def get_by_asset(asset_recordcode: str) -> QuerySet[HardDiskSN]:
        """查询某资产的所有硬盘"""
        return HardDiskSN.objects.filter(
            asset_recordcode=asset_recordcode, is_deleted=False
        ).order_by("harddisk_sn_code")

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
        return HardDiskSN.objects.filter(
            asset_recordcode=asset_recordcode, is_deleted=False
        ).count()

    @staticmethod
    def get_by_status(status: str) -> QuerySet[HardDiskSN]:
        """按状态查询"""
        return HardDiskSN.objects.filter(
            harddisk_status=status, is_deleted=False
        )


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
        """获取仪表盘概览统计（资产+合同+在用资产）"""
        asset_stats = Asset.objects.filter(is_deleted=False).aggregate(
            total=Count("id"), total_value=Sum("asset_purchase_price")
        )
        contract_stats = Contract.objects.filter(is_deleted=False).aggregate(total=Count("id"))
        active_assets = Asset.objects.filter(is_deleted=False, asset_current_status="in_use").count()
        return {
            "total_assets": asset_stats["total"] or 0,
            "total_value": asset_stats["total_value"] or 0,
            "total_contracts": contract_stats["total"] or 0,
            "active_assets": active_assets,
        }

    @staticmethod
    def get_recent_out_assets(limit: int = 10) -> list:
        """获取最近出库记录"""
        from apps.assetmanagement.models import OutAsset

        outassets = (
            OutAsset.objects.filter(is_deleted=False)
            .select_related("asset_recordcode", "asset_recordcode__asset_applicant_recordcode")
            .order_by("-outasset_date")[:limit]
        )
        return [
            {
                "recordcode": oa.recordcode,
                "asset_code": oa.asset_recordcode.asset_code if oa.asset_recordcode else None,
                "asset_name": oa.asset_recordcode.asset_name if oa.asset_recordcode else None,
                "outasset_date": oa.outasset_date,
                "outasset_type": oa.outasset_type,
            }
            for oa in outassets
        ]

    @staticmethod
    def get_recent_recycle_assets(limit: int = 10) -> list:
        """获取最近回收记录"""
        from apps.assetmanagement.models import RecycleAsset

        recycles = (
            RecycleAsset.objects.filter(is_deleted=False)
            .select_related("asset_recordcode", "outasset_recordcode")
            .order_by("-recycle_asset_date")[:limit]
        )
        return [
            {
                "recordcode": r.recordcode,
                "asset_code": r.asset_recordcode.asset_code if r.asset_recordcode else None,
                "asset_name": r.asset_recordcode.asset_name if r.asset_recordcode else None,
                "recycle_asset_date": r.recycle_asset_date,
            }
            for r in recycles
        ]

    @staticmethod
    def get_asset_trend(days: int = 30) -> dict[str, Any]:
        """获取资产趋势数据（按日统计）"""
        from datetime import timedelta

        from django.db.models.functions import TruncDate
        from django.utils import timezone

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        daily_creates = (
            Asset.objects.filter(is_deleted=False, created_at__date__gte=start_date, created_at__date__lte=end_date)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        daily_value = (
            Asset.objects.filter(is_deleted=False, created_at__date__gte=start_date, created_at__date__lte=end_date)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(value=Sum("asset_purchase_price"))
            .order_by("date")
        )

        create_map = {item["date"].isoformat(): item["count"] for item in daily_creates}
        value_map = {item["date"].isoformat(): float(item["value"] or 0) for item in daily_value}

        trend_data = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()
            trend_data.append(
                {
                    "date": date_str,
                    "new_count": create_map.get(date_str, 0),
                    "total_value": value_map.get(date_str, 0),
                }
            )
            current_date += timedelta(days=1)

        return {
            "days": days,
            "trend": trend_data,
        }

    @staticmethod
    def get_department_distribution() -> list:
        """获取资产按部门分布统计"""
        dept_stats = (
            Asset.objects.filter(is_deleted=False, asset_manager_recordcode__isnull=False)
            .values(
                "asset_manager_recordcode__employee_department__department_code",
                "asset_manager_recordcode__employee_department__department_name",
            )
            .annotate(asset_count=Count("id"), total_value=Sum("asset_purchase_price"))
            .order_by("-asset_count")
        )

        return [
            {
                "department_code": item["asset_manager_recordcode__employee_department__department_code"] or "未知",
                "department_name": item["asset_manager_recordcode__employee_department__department_name"] or "未知",
                "asset_count": item["asset_count"],
                "total_value": float(item["total_value"] or 0),
            }
            for item in dept_stats
        ]

    @staticmethod
    def get_type_distribution() -> list:
        """获取资产按类型分布统计"""
        type_stats = (
            Asset.objects.filter(is_deleted=False, asset_type_recordcode__isnull=False)
            .values(
                "asset_type_recordcode__type_code",
                "asset_type_recordcode__type_name",
                "asset_type_recordcode__level",
            )
            .annotate(asset_count=Count("id"), total_value=Sum("asset_purchase_price"))
            .order_by("-asset_count")
        )

        return [
            {
                "type_code": item["asset_type_recordcode__type_code"],
                "type_name": item["asset_type_recordcode__type_name"],
                "level": item["asset_type_recordcode__level"],
                "asset_count": item["asset_count"],
                "total_value": float(item["total_value"] or 0),
            }
            for item in type_stats
        ]

    @staticmethod
    def get_expiring_assets(days: int = 30) -> list:
        """获取即将到期的资产（保修期即将结束）"""
        expiring_assets = (
            Asset.objects.filter(is_deleted=False, asset_warranty_period__gt=0, asset_purchase_date__isnull=False)
            .select_related("asset_type_recordcode", "asset_storage_recordcode", "asset_manager_recordcode")
            .order_by("asset_purchase_date")[:50]
        )

        result = []
        for asset in expiring_assets:
            from datetime import date
            from dateutil.relativedelta import relativedelta

            warranty_end = asset.asset_purchase_date + relativedelta(months=asset.asset_warranty_period * 12)
            days_remaining = (warranty_end - date.today()).days

            if 0 <= days_remaining <= days:
                result.append(
                    {
                        "asset_code": asset.asset_code,
                        "asset_name": asset.asset_name,
                        "asset_purchase_date": asset.asset_purchase_date.isoformat(),
                        "warranty_period": asset.asset_warranty_period,
                        "warranty_end_date": warranty_end.isoformat(),
                        "days_remaining": days_remaining,
                        "asset_manager": asset.asset_manager_recordcode.employee_name
                        if asset.asset_manager_recordcode
                        else None,
                    }
                )

        return sorted(result, key=lambda x: x["days_remaining"])

    @staticmethod
    def get_maintenance_reminders() -> list:
        """获取维护提醒数据"""
        from django.utils import timezone

        now = timezone.now().date()

        assets = (
            Asset.objects.filter(is_deleted=False, asset_current_status="in_use", asset_entry_date__isnull=False)
            .select_related("asset_type_recordcode", "asset_storage_recordcode", "asset_manager_recordcode")
            .order_by("asset_entry_date")[:50]
        )

        result = []
        for asset in assets:
            usage_months = (now.year - asset.asset_entry_date.year) * 12 + (now.month - asset.asset_entry_date.month)

            if usage_months >= 24:
                result.append(
                    {
                        "asset_code": asset.asset_code,
                        "asset_name": asset.asset_name,
                        "asset_entry_date": asset.asset_entry_date.isoformat(),
                        "usage_months": usage_months,
                        "asset_type": asset.asset_type_recordcode.type_name
                        if asset.asset_type_recordcode
                        else None,
                        "asset_manager": asset.asset_manager_recordcode.employee_name
                        if asset.asset_manager_recordcode
                        else None,
                        "storage_name": asset.asset_storage_recordcode.storage_name
                        if asset.asset_storage_recordcode
                        else None,
                    }
                )

        return sorted(result, key=lambda x: x["usage_months"], reverse=True)
