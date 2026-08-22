"""
仪表盘视图集
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.assetmanagement.selectors import DashboardSelector
from apps.assetmanagement.serializers import DashboardStatSerializer
from core.mixins import LoggingMixin, ResponseWrapperMixin
from utils.response_utils import success_response


class DashboardViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DashboardStatSerializer

    @action(detail=False, methods=["get"])
    def overview(self, request) -> Response:
        stats = DashboardSelector.get_overview_statistics()
        return success_response(data=stats)

    @action(detail=False, methods=["get"])
    def recent_out_assets(self, request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_out_assets(limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="recent_recycle_assets")
    def recent_recycle_assets(self, request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_recycle_assets(limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=["get"])
    def trend(self, request) -> Response:
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date and end_date:
            result = DashboardSelector.get_asset_trend(start_date=start_date, end_date=end_date)
        else:
            try:
                days = min(int(request.query_params.get("days", 30) or 30), 365)
            except (ValueError, TypeError):
                days = 30
            result = DashboardSelector.get_asset_trend(days=days)
        return success_response(data=result)

    @action(detail=False, methods=["get"])
    def department_distribution(self, request) -> Response:
        result = DashboardSelector.get_department_distribution()
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="type_distribution")
    def type_distribution(self, request) -> Response:
        result = DashboardSelector.get_type_distribution()
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="expiring_assets")
    def expiring_assets(self, request) -> Response:
        try:
            days = min(int(request.query_params.get("days", 30) or 30), 365)
        except (ValueError, TypeError):
            days = 30
        result = DashboardSelector.get_expiring_assets(days=days)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="maintenance_reminders")
    def maintenance_reminders(self, request) -> Response:
        result = DashboardSelector.get_maintenance_reminders()
        return success_response(data=result)
