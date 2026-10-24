"""
仪表盘视图集
"""

from typing import Any

from django.http import QueryDict
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


def _parse_int_param(query_params: QueryDict, key: str, default: int, upper: int) -> int:
    """仪表盘 query 参数统一解析（M-28 / BF-140：同形 try/except 去重，DR-1）。

    缺省/空值/非法值回退 default，超 upper 时钳位。limit（默认 10/上限 100）
    与 days（默认 30/上限 365）共用。两者均为非分页 top-N/时间窗参数，
    豁免 B4 page/page_size 分页规范（backend-business-rules.md B4 豁免条款）。
    """
    try:
        return min(int(query_params.get(key, default) or default), upper)
    except (ValueError, TypeError):
        return default


class DashboardViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DashboardStatSerializer

    @action(detail=False, methods=["get"])
    def overview(self, request: Any) -> Response:
        stats = DashboardSelector.get_overview_statistics(request.user)
        return success_response(data=stats)

    @extend_schema(
        summary="最近发放",
        # limit 由 _parse_int_param 解析（缺省/非法回退 10、上限 100），
        # spectacular 无法内省出，故显式声明，避免基线与运行时脱节。
        parameters=[_limit_parameter()],
    )
    @action(detail=False, methods=["get"])
    def recent_out_assets(self, request: Any) -> Response:
        limit = _parse_int_param(request.query_params, "limit", 10, 100)
        result = DashboardSelector.get_recent_out_assets(request.user, limit=limit)
        return success_response(data=result)

    @extend_schema(
        summary="最近回收",
        parameters=[_limit_parameter()],
    )
    @action(detail=False, methods=["get"], url_path="recent_recycle_assets")
    def recent_recycle_assets(self, request: Any) -> Response:
        limit = _parse_int_param(request.query_params, "limit", 10, 100)
        result = DashboardSelector.get_recent_recycle_assets(request.user, limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=["get"])
    def trend(self, request: Any) -> Response:
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date and end_date:
            result = DashboardSelector.get_asset_trend(request.user, start_date=start_date, end_date=end_date)
        else:
            days = _parse_int_param(request.query_params, "days", 30, 365)
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
        days = _parse_int_param(request.query_params, "days", 30, 365)
        result = DashboardSelector.get_expiring_assets(request.user, days=days)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="maintenance_reminders")
    def maintenance_reminders(self, request: Any) -> Response:
        result = DashboardSelector.get_maintenance_reminders(request.user)
        return success_response(data=result)
