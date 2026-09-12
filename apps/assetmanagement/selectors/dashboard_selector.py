"""
仪表盘查询选择器

提供仪表盘统计相关的查询方法(从 base_selector.py 拆分)。
"""

from typing import Any

from django.db.models import Count, QuerySet, Sum

from apps.assetmanagement.models import Asset, Contract
from core.department_scope import (
    build_asset_owned_department_q,
    get_asset_linked_queryset_for_user,
    get_department_codes_for_user,
)


class DashboardSelector:
    """仪表盘查询选择器"""

    @staticmethod
    def _scoped_asset_queryset(user: Any) -> QuerySet[Any, Any]:
        """按用户部门范围过滤 Asset 查询集(与全系统行级隔离单一事实来源)

        get_department_codes_for_user 返回值语义:
        - None: 无限制(system_admin / auditor / superuser / 无 Employee)
        - 空列表: 无权限(部门级角色但无部门),返回空集
        - 非空列表: 限定部门范围(三路径归属)
        """
        codes = get_department_codes_for_user(user)
        if codes is None:
            return Asset.objects.filter(is_deleted=False)
        if not codes:
            return Asset.objects.none()
        return Asset.objects.filter(is_deleted=False).filter(build_asset_owned_department_q(codes))

    @staticmethod
    def get_statistics(user: Any) -> dict[str, Any]:
        assets = DashboardSelector._scoped_asset_queryset(user)
        asset_stats = assets.aggregate(
            total=Count("id"), total_value=Sum("asset_purchase_price")
        )
        status_counts = (
            assets.values("asset_current_status").annotate(count=Count("id"))
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
    def get_overview_statistics(user: Any) -> dict[str, Any]:
        """获取仪表盘概览统计 — 资产 + 合同 + 状态分布 + 月度/累计操作数(按用户范围)"""
        from django.utils import timezone

        from apps.assetmanagement.models import OutAsset, RecycleAsset

        now = timezone.now()

        assets = DashboardSelector._scoped_asset_queryset(user)
        asset_stats = assets.aggregate(
            total=Count("id"), total_value=Sum("asset_purchase_price")
        )
        contract_stats = Contract.objects.filter(is_deleted=False).aggregate(total=Count("id"))

        # 按状态分组（一次查询覆盖全部 8 种状态）
        status_counts = dict(
            assets.values_list("asset_current_status")
            .annotate(count=Count("id"))
            .values_list("asset_current_status", "count")
        )

        status_distribution = {
            code: {"name": label, "count": status_counts.get(code, 0)}
            for code, label in Asset.ASSET_STATUS_CHOICES
        }

        # 月度 / 累计操作数(与资产同范围隔离)
        scoped_out_qs = get_asset_linked_queryset_for_user(user, OutAsset.objects.filter(is_deleted=False))
        scoped_recycle_qs = get_asset_linked_queryset_for_user(user, RecycleAsset.objects.filter(is_deleted=False))
        monthly_distributed = scoped_out_qs.filter(
            outasset_date__year=now.year, outasset_date__month=now.month
        ).count()
        monthly_recycled = scoped_recycle_qs.filter(
            recycle_asset_date__year=now.year, recycle_asset_date__month=now.month
        ).count()
        total_distributed = scoped_out_qs.count()
        total_recycled = scoped_recycle_qs.count()

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
    def get_recent_out_assets(user: Any, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近出库记录(按用户部门范围隔离)"""
        from apps.assetmanagement.models import OutAsset

        out_qs = get_asset_linked_queryset_for_user(
            user,
            OutAsset.objects.filter(is_deleted=False).select_related(
                "asset_recordcode",
                "outasset_applicant_recordcode",
                "outasset_applicant_recordcode__employee_department",
            ),
        )
        outassets = out_qs.order_by("-outasset_date")[:limit]
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
    def get_recent_recycle_assets(user: Any, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近回收记录(按用户部门范围隔离)"""
        from apps.assetmanagement.models import RecycleAsset

        recycle_qs = get_asset_linked_queryset_for_user(
            user,
            RecycleAsset.objects.filter(is_deleted=False).select_related(
                "asset_recordcode",
                "outasset_recordcode",
                "operator_employee",
                "operator_employee__employee_department",
            ),
        )
        recycles = recycle_qs.order_by("-recycle_asset_date")[:limit]
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
        user: Any,
        days: int = 30,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取资产趋势数据(按日统计,按用户部门范围隔离)

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
            DashboardSelector._scoped_asset_queryset(user)
            .filter(created_at__date__gte=range_start, created_at__date__lte=range_end)
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
    def get_department_distribution(user: Any) -> list[dict[str, Any]]:
        """获取资产按部门分布统计(仅展示用户范围内的部门,不泄露其他部门)

        返回格式对齐前端 types/dashboard.ts 内联类型：
        [{"department_name": str, "asset_count": int, "percentage": float}]
        """
        codes = get_department_codes_for_user(user)
        if codes is not None and not codes:
            return []

        dept_stats_qs = Asset.objects.filter(is_deleted=False, asset_manager_recordcode__isnull=False)
        if codes:
            dept_stats_qs = dept_stats_qs.filter(
                asset_manager_recordcode__employee_department__department_code__in=codes
            )
        dept_stats = dept_stats_qs.values(
            "asset_manager_recordcode__employee_department__department_name"
        ).annotate(asset_count=Count("id")).order_by("-asset_count")

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
    def get_type_distribution(user: Any) -> list[dict[str, Any]]:
        """获取资产按类型分布统计(按用户部门范围隔离)

        返回格式对齐前端 types/dashboard.ts 内联类型：
        [{"type_name": str, "count": int, "percentage": float}]
        """
        type_stats = (
            DashboardSelector._scoped_asset_queryset(user)
            .select_related("asset_type_recordcode")
            .filter(asset_type_recordcode__isnull=False)
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
    def get_expiring_assets(user: Any, days: int = 30) -> list[dict[str, Any]]:
        """获取即将到期的资产(保修期即将结束,按用户部门范围隔离)

        返回格式对齐前端 types/dashboard.ts ExpiringAsset：
        [{"id": int, "asset_code": str, "asset_name": str, "expire_date": str, "days_until_expire": int}]
        """
        from datetime import date

        from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

        expiring_assets = (
            DashboardSelector._scoped_asset_queryset(user)
            .filter(asset_warranty_period__gt=0, asset_purchase_date__isnull=False)
            .order_by("asset_purchase_date")[:50]
        )

        result = []
        for asset in expiring_assets:
            warranty_end = asset.asset_purchase_date + relativedelta(months=asset.asset_warranty_period * 12)  # type: ignore[operator]
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
    def get_maintenance_reminders(user: Any) -> list[dict[str, Any]]:
        """获取维护提醒数据(按用户部门范围隔离)

        返回格式对齐前端 types/dashboard.ts MaintenanceReminder：
        [{"id": int, "asset_code": str, "asset_name": str, "maintenance_date": str, "type": str}]
        注：maintenance_date 取 asset_entry_date（入库日期），type 暂固定为 "定期检查"。
        """
        from django.utils import timezone

        now = timezone.now().date()

        assets = (
            DashboardSelector._scoped_asset_queryset(user)
            .filter(asset_current_status="in_use", asset_entry_date__isnull=False)
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
