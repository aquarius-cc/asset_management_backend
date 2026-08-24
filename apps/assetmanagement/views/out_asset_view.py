"""
出库资产管理视图集
"""

from django.db.models import Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter  # type: ignore[attr-defined]
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import OutAsset
from apps.assetmanagement.selectors import AssetSelector, OutAssetSelector
from apps.assetmanagement.serializers import (
    OutAssetBatchCreateSerializer,
    OutAssetBatchDeleteSerializer,
    OutAssetCreateSerializer,
    OutAssetDetailSerializer,
    OutAssetListSerializer,
    OutAssetUpdateSerializer,
)
from apps.assetmanagement.services import OutAssetService
from core.batch_mixins import BatchResponseHelper
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, OperatorContextMixin, RecordcodeLookupMixin


OUTASSET_STATUS_MAP = dict(OutAsset.OUTASSET_STATUS_CHOICES) if hasattr(OutAsset, "OUTASSET_STATUS_CHOICES") else {}


@extend_schema(tags=["出库管理"])
class OutAssetViewSet(
    OperatorContextMixin,
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet[OutAsset],
):
    queryset = OutAsset.objects.filter(is_deleted=False)
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["outasset_type"]
    ordering_fields = ["outasset_date"]
    ordering = ["-outasset_date"]
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_create",
        "batch_delete",
        "cancel_outasset",
    ]

    # 导出配置
    export_columns = [
        {"header": "资产编码", "field": "asset_recordcode__asset_code"},
        {"header": "资产名称", "field": "asset_recordcode__asset_name"},
        {"header": "出库类型", "field": "outasset_type"},
        {"header": "出库日期", "field": "outasset_date"},
        {"header": "品牌", "field": "asset_recordcode__asset_brand"},
        {"header": "规格", "field": "asset_recordcode__asset_specification"},
    ]
    export_filename = "out_assets_export.xlsx"
    export_sheet_name = "出库记录"

    def get_permissions(self):
        """RBAC: 写操作需 asset_admin+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self) -> QuerySet[OutAsset]:
        """RBAC 行级过滤 + 关键词搜索"""
        if self.action == "list":
            qs = OutAssetSelector.get_queryset_for_user(self.request.user)
        else:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            qs = OutAssetSelector.get_queryset_for_user(self.request.user).with_asset_details()  # type: ignore[attr-defined]

        keyword = self.request.query_params.get("keyword", "").strip()
        search_type = self.request.query_params.get("searchType", "all").lower()
        status_filter = self.request.query_params.get("asset_current_status", "").strip()

        if keyword:
            asset_cond = Q(asset_recordcode__asset_code__icontains=keyword) | Q(
                asset_recordcode__asset_name__icontains=keyword
            )
            user_cond = (
                Q(asset_recordcode__asset_applicant_recordcode__employee_jobcode__icontains=keyword)
                | Q(asset_recordcode__asset_applicant_recordcode__employee_name__icontains=keyword)
                | Q(asset_recordcode__asset_manager_recordcode__employee_jobcode__icontains=keyword)
                | Q(asset_recordcode__asset_manager_recordcode__employee_name__icontains=keyword)
            )
            if search_type == "asset":
                qs = qs.filter(asset_cond)
            elif search_type == "user":
                qs = qs.filter(user_cond)
            else:
                qs = qs.filter(asset_cond | user_cond)

        if status_filter:
            qs = qs.filter(asset_recordcode__asset_current_status=status_filter)

        return qs.order_by("-outasset_date")

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return OutAssetListSerializer
        elif self.action == "recyclable":
            return OutAssetListSerializer
        elif self.action == "create":
            return OutAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return OutAssetUpdateSerializer
        return OutAssetDetailSerializer

    @action(detail=False, methods=["get"], url_path="recyclable")
    def recyclable(self, request):
        filters = {}
        keyword = request.query_params.get("search", "").strip()
        if keyword:
            filters["keyword"] = keyword
            filters["search_type"] = request.query_params.get("searchType", "all").lower()

        FILTER_PARAMS = [
            "asset_code",
            "asset_name",
            "asset_specification",
            "asset_brand",
            "outasset_applicant_name",
            "outasset_manager_name",
            "department",
            "department_code",
            "employee_jobcode",
        ]
        for param in FILTER_PARAMS:
            value = request.query_params.get(param, "").strip()
            if value:
                filters[param] = value

        years = request.query_params.get("years")
        if years and years.isdigit():
            filters["years"] = int(years)

        ordering = request.query_params.get("ordering", "").strip()
        if ordering:
            filters["ordering"] = ordering

        queryset = OutAssetSelector.get_recyclable_outassets(filters if filters else None, user=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(data={"count": queryset.count(), "results": serializer.data})

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data.pop("recordcode", None)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        outasset = OutAssetService.create_outasset(
            serializer.validated_data,
            **self.get_operator_context(),
        )
        return success_response(
            data=OutAssetCreateSerializer(outasset).data, message="出库成功", status_code=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        recordcode = self.kwargs.get("recordcode")
        outasset = OutAssetService.update_outasset(
            recordcode=recordcode,
            update_data=request.data,
        )
        return success_response(data=OutAssetDetailSerializer(outasset).data, message="更新成功")

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = OutAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = OutAssetService.batch_create_outasset(
            serializer.validated_data["items"],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        # 【DR-1/B-8】响应组装复用 BatchResponseHelper; input_data 以用户原始输入回显
        return BatchResponseHelper.create_response(
            result,
            OutAssetCreateSerializer,
            message=f"批量出库完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
            request_items=serializer.initial_data.get("items"),
        )

    def destroy(self, request, *args, **kwargs):
        outasset = self.get_object()
        result = OutAssetService.batch_delete_outasset(
            recordcodes=[outasset.recordcode],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        if result["fail_count"] > 0:
            fail_item = result["fail_items"][0]
            return error_response(
                message=fail_item["error_message"], status_code=400,
                errors={"error_code": fail_item.get("error_code")},
            )
        return success_response(message="删除成功")

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = OutAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = OutAssetService.batch_delete_outasset(
            serializer.validated_data["ids"],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper
        return BatchResponseHelper.delete_response(
            result,
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(name="asset_code", type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)
        ],
        responses={200: OutAssetListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_code>[^/.]+)")
    def by_asset(self, request, asset_code=None) -> Response:
        visible = AssetSelector.get_queryset_for_user(request.user).filter(asset_code=asset_code).exists()
        if not visible:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        records = OutAssetSelector.get_outassets_by_asset(asset_code, user=request.user)
        return self._paginate_and_respond(records)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="applicant_jobcode", type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True
            )
        ],
        responses={200: OutAssetDetailSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="by-applicant/(?P<applicant_jobcode>[^/.]+)")
    def by_applicant(self, request, applicant_jobcode=None) -> Response:
        if not applicant_jobcode:
            return error_response(message="请提供申请人工号", status_code=400)
        records = OutAssetSelector.get_outassets_by_applicant(applicant_jobcode, user=request.user)
        return self._paginate_and_respond(records)

    @action(detail=True, methods=["post"], url_path="cancel", permission_classes=[IsAssetAdminOrAbove])
    def cancel_outasset(self, request, recordcode=None):
        """POST /out-assets/{recordcode}/cancel/ — 取消出库,恢复资产状态"""
        outasset = self.get_object()
        result = OutAssetService.batch_delete_outasset(
            recordcodes=[outasset.recordcode],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        if result["fail_count"] > 0:
            fail_item = result["fail_items"][0]
            return error_response(
                message=fail_item["error_message"], status_code=400,
                errors={"error_code": fail_item.get("error_code")},
            )
        return success_response(message="取消出库成功,资产状态已恢复")

    @action(detail=False, methods=["get"])
    def statistics(self, request) -> Response:
        from django.db.models import Count

        queryset = self.get_queryset()
        total = queryset.count()
        type_counts = queryset.values("outasset_type").annotate(count=Count("id"))
        return success_response(
            data={"total_outassets": total, "by_type": {item["outasset_type"]: item["count"] for item in type_counts}},
            message="查询成功",
        )
