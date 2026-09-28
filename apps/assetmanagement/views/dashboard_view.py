"""
仪表盘视图集
"""

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.assetmanagement.selectors import DashboardSelector
from apps.assetmanagement.serializers import DashboardStatSerializer  # type: ignore[attr-defined]
from core.mixins import LoggingMixin, ResponseWrapperMixin
from utils.response_utils import success_response


def _limit_parameter() -> OpenApiParameter:
    """最近列表类 action 共用的 limit 查询参数声明（DR-1：单一构造点）。"""
    return OpenApiParameter(
        name="limit",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        default=10,
        description="返回条数上限（默认 10，运行时上限 100）",
    )


class DashboardViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DashboardStatSerializer

    @action(detail=False, methods=["get"])
    def overview(self, request: Any) -> Response:
        stats = DashboardSelector.get_overview_statistics(request.user)
        return success_response(data=stats)

    @extend_schema(
        summary="最近发放",
        # limit 由本方法自行解析 query_params（带 try/except 兜底与 100 上限），
        # spectacular 无法内省出，故显式声明，避免基线与运行时脱节。
        parameters=[_limit_parameter()],
    )
    @action(detail=False, methods=["get"])
    def recent_out_assets(self, request: Any) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_out_assets(request.user, limit=limit)
        return success_response(data=result)

    @extend_schema(
        summary="最近回收",
        parameters=[_limit_parameter()],
    )
    @action(detail=False, methods=["get"], url_path="recent_recycle_assets")
    def recent_recycle_assets(self, request: Any) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_recycle_assets(request.user, limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=["get"])
    def trend(self, request: Any) -> Response:
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date and end_date:
            result = DashboardSelector.get_asset_trend(request.user, start_date=start_date, end_date=end_date)
        else:
            try:
                days = min(int(request.query_params.get("days", 30) or 30), 365)
            except (ValueError, TypeError):
                days = 30
            result = DashboardSelector.get_asset_trend(request.user, days=days)
        return success_response(data=result)

    @action(detail=False, methods=["get"])
    def department_distribution(self, request: Any) -> Response:
        result = DashboardSelector.get_department_distribution(request.user)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="type_distribution")
    def type_distribution(self, request: Any) -> Response:
        result = DashboardSelector.get_type_distribution(request.user)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="expiring_assets")
    def expiring_assets(self, request: Any) -> Response:
        try:
            days = min(int(request.query_params.get("days", 30) or 30), 365)
        except (ValueError, TypeError):
            days = 30
        result = DashboardSelector.get_expiring_assets(request.user, days=days)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="maintenance_reminders")
    def maintenance_reminders(self, request: Any) -> Response:
        result = DashboardSelector.get_maintenance_reminders(request.user)
        return success_response(data=result)
