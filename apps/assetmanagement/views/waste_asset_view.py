"""
已报废资产视图集

提供已报废资产的查询和删除功能。
已报废记录为终态记录,不允许创建和修改。
"""

import logging
from datetime import datetime as dt

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import WasteAsset
from apps.assetmanagement.selectors import AssetSelector, WasteAssetSelector
from apps.assetmanagement.serializers import (
    WasteAssetBatchDeleteSerializer,
    WasteAssetDetailSerializer,
    WasteAssetListSerializer,
    WasteAssetSerializer,
)
from apps.assetmanagement.services import WasteAssetService
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class WasteAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = WasteAsset.objects.filter(is_deleted=False)
    serializer_class = WasteAssetSerializer
    pagination_class = CustomPageNumberPagination
    lookup_field = "asset_recordcode__asset_code"
    admin_actions = ["create", "update", "partial_update", "destroy", "batch_delete"]

    # 导出配置
    export_columns = [
        {"header": "资产编码", "field": "asset_recordcode__asset_code"},
        {"header": "资产名称", "field": "asset_recordcode__asset_name"},
        {"header": "报废日期", "field": "waste_asset_date"},
        {"header": "报废数量", "field": "waste_asset_number"},
        {"header": "报废描述", "field": "waste_asset_description"},
    ]
    export_filename = "waste_assets_export.xlsx"
    export_sheet_name = "已报废资产"

    def get_permissions(self):
        """RBAC: 写操作需 IsAssetAdminOrAbove+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["waste_asset_date"]
    search_fields = ["asset_recordcode__asset_name", "asset_recordcode__asset_code"]
    ordering_fields = ["waste_asset_date"]
    ordering = ["-waste_asset_date"]

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return WasteAssetListSerializer
        return WasteAssetDetailSerializer

    def get_queryset(self):
        # RBAC 行级数据隔离
        if self.action == "list":
            return WasteAssetSelector.get_queryset_for_user(self.request.user)
        # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
        return WasteAssetSelector.get_queryset_for_user(self.request.user).with_asset_details()

    def create(self, request, *args, **kwargs):
        return error_response(
            message="已报废记录不允许直接创建,请通过待报废审批流程创建",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        return error_response(
            message="已报废记录为终态记录,不允许修改",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return error_response(
            message="已报废记录为终态记录,不允许修改",
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_recordcode>[^/.]+)")
    def by_asset(self, request, asset_recordcode=None) -> Response:
        asset = AssetSelector.get_asset_by_code(asset_recordcode)
        if asset is None:
            return error_response(message=f"资产 {asset_recordcode} 不存在", status_code=404)
        records = WasteAssetSelector.get_by_asset_code(asset_recordcode)
        return self._paginate_and_respond(records)

    @action(detail=False, methods=["get"])
    def statistics(self, request) -> Response:
        from django.db.models import Count
        from django.utils import timezone

        queryset = WasteAsset.objects.filter(is_deleted=False)
        total = queryset.count()
        current_year = timezone.now().year
        current_year_count = queryset.filter(waste_asset_date__year=current_year).count()

        monthly = {}
        for item in (
            queryset.filter(waste_asset_date__year=current_year)
            .values("waste_asset_date__month")
            .annotate(count=Count("id"))
            .order_by("waste_asset_date__month")
        ):
            monthly[item["waste_asset_date__month"]] = item["count"]

        return success_response(
            data={"total_waste": total, "current_year_count": current_year_count, "monthly_distribution": monthly}
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="开始日期(YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="结束日期(YYYY-MM-DD)",
            ),
        ],
        responses={200: WasteAssetListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="by-date-range")
    def by_date_range(self, request) -> Response:
        start_date = None
        end_date = None
        start_date_str = request.query_params.get("start_date", "").strip()
        end_date_str = request.query_params.get("end_date", "").strip()
        if start_date_str:
            try:
                start_date = dt.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                return error_response(message="开始日期格式错误,应为 YYYY-MM-DD", status_code=400)
        if end_date_str:
            try:
                end_date = dt.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                return error_response(message="结束日期格式错误,应为 YYYY-MM-DD", status_code=400)
        qs = WasteAsset.objects.with_asset_details().all()
        if start_date:
            qs = qs.filter(waste_asset_date__gte=start_date)
        if end_date:
            qs = qs.filter(waste_asset_date__lte=end_date)
        return self._paginate_and_respond(qs)

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = WasteAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        success_ids = []
        fail_items = []
        for asset_recordcode_code in ids:
            try:
                WasteAssetService.cancel_waste_asset(asset_recordcode_code)
                success_ids.append(asset_recordcode_code)
            except WasteAsset.DoesNotExist:
                fail_items.append(
                    {
                        "id": asset_recordcode_code,
                        "error_code": "NOT_FOUND",
                        "error_message": f"已报废记录 {asset_recordcode_code} 不存在",
                    }
                )
            except Exception as e:
                logging.exception(f"批量删除报废资产失败: {e}")
                fail_items.append(
                    {"id": asset_recordcode_code, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误"}
                )
        return success_response(
            data={
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"批量删除完成,成功 {len(success_ids)} 条,失败 {len(fail_items)} 条",
        )
