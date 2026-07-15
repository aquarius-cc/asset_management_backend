"""
仪表盘视图集
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mixins import LoggingMixin, ResponseWrapperMixin
from utils.response_utils import success_response

from apps.assetmanagement.selectors import DashboardSelector
from apps.assetmanagement.serializers import DashboardStatSerializer


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

    @action(detail=False, methods=["get"])
    def recent_asset_recordcodes(self, request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_recycle_assets(limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=["get"], url_path="recent_recycle_assets")
    def recent_recycle_assets(self, request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 10) or 10), 100)
        except (ValueError, TypeError):
            limit = 10
        result = DashboardSelector.get_recent_recycle_assets(limit=limit)
        return success_response(data=result)
