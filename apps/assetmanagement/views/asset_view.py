"""
资产管理视图集
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

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors import AssetSelector
from apps.assetmanagement.serializers import (
    AssetBatchCreateSerializer,
    AssetBatchDeleteSerializer,
    AssetCreateSerializer,
    AssetDetailSerializer,
    AssetListSerializer,
    AssetUpdateSerializer,
    CombinedAssetSerializer,
    ContractDetailSerializer,
)
from apps.assetmanagement.services import AssetService, RepairAssetService
from core.batch_mixins import BatchResponseHelper
from core.constants import ASSET_STATUS_CHOICES
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


ASSET_STATUS_MAP = dict(ASSET_STATUS_CHOICES)


class AssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet[Asset],
):
    queryset = AssetSelector.get_assets_with_all_relations()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_create",
        "batch_delete",
        "change_status",
        "change_outasset_employee",
        "found_and_return",
        "repair",
        "repair_done",
        "repair_failed",
    ]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["asset_current_status", "asset_type_recordcode", "asset_storage_recordcode"]
    ordering_fields = ["asset_code", "asset_entry_date", "asset_purchase_price", "asset_name"]
    ordering = ["-asset_entry_date"]

    # 导出配置(HIGH-12: 使用 ExportExcelMixin 替代自定义导出)
    export_columns = [
        {"header": "资产编码", "field": "asset_code"},
        {"header": "资产名称", "field": "asset_name"},
        {"header": "规格", "field": "asset_specification"},
        {"header": "品牌", "field": "asset_brand"},
        {"header": "当前状态", "field": "asset_current_status", "display_map": ASSET_STATUS_MAP},
        {"header": "资产分类", "field": "asset_type_recordcode__type_name"},
        {"header": "存放仓库", "field": "asset_storage_recordcode__storage_name"},
        {"header": "使用人", "field": "asset_manager_recordcode__employee_name"},
        {"header": "购买日期", "field": "asset_purchase_date"},
        {"header": "购买价格", "field": "asset_purchase_price"},
    ]
    export_filename = "assets_export.xlsx"
    export_sheet_name = "资产列表"

    def get_permissions(self):
        """RBAC: 写操作需 asset_admin+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self) -> type:
        if self.action == "create":
            return AssetCreateSerializer
        elif self.action == "list":
            return AssetListSerializer
        elif self.action in ["update", "partial_update"]:
            return AssetUpdateSerializer
        return AssetDetailSerializer

    def get_queryset(self) -> QuerySet[Asset]:
        # RBAC 行级数据隔离(所有动作统一限权,list 用列表预加载,其余保留详情预加载)
        if self.action == "list":
            qs = AssetSelector.get_queryset_for_user(self.request.user)
        else:
            qs = AssetSelector.apply_user_scope(AssetSelector.get_assets_with_all_relations(), self.request.user)

        keyword = self.request.GET.get("keyword", "").strip()
        if keyword:
            qs = qs.filter(
                Q(asset_code__icontains=keyword)
                | Q(asset_name__icontains=keyword)
                | Q(asset_brand__icontains=keyword)
                | Q(asset_specification__icontains=keyword)
            )
        return qs

    def _scoped(self, queryset: QuerySet[Asset]) -> QuerySet[Asset]:
        """对自定义 Action 构建的 Asset QuerySet 施加 RBAC 部门范围"""
        return AssetSelector.apply_user_scope(queryset, self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assets = AssetService.create_asset(
            serializer.validated_data,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        response_serializer = AssetDetailSerializer(assets, many=True)
        count = len(assets)
        message = f"创建成功,共创建 {count} 条资产记录" if count > 1 else "创建成功"
        return success_response(data=response_serializer.data, message=message, status_code=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        asset = self.get_object()
        asset_code = asset.asset_code
        asset = AssetService.update_asset(
            asset_code=asset_code,
            update_data=request.data,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        serializer = AssetDetailSerializer(asset)
        return success_response(data=serializer.data, message="更新成功")

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        asset = self.get_object()
        asset_code = asset.asset_code
        AssetService.delete_asset(
            asset_code=asset_code,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(message="删除成功")

    @extend_schema(
        parameters=[
            OpenApiParameter(name="name", type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)
        ],
        responses={200: AssetDetailSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="getassetbyname/(?P<name>[^/.]+)")
    def get_asset_by_name(self, request, name=None) -> Response:
        if not name:
            return success_response(data={"count": 0, "results": []})
        assets = self._scoped(AssetSelector.search_assets(keyword=name))
        serializer = AssetDetailSerializer(assets, many=True)
        return success_response(data={"count": assets.count(), "results": serializer.data})

    @action(detail=False, methods=["get"], url_path="getassetbyrecordcode/(?P<recordcode>[^/.]+)")
    def get_asset_by_recordcode(self, request, recordcode=None) -> Response:
        code = request.query_params.get("recordcode")
        if not code:
            return error_response(message="缺少 recordcode 参数", status_code=400)
        assets = self.get_queryset().filter(recordcode=code)
        serializer = self.get_serializer(assets, many=True)
        return success_response(data=serializer.data)

    @action(detail=False, methods=["get"], url_path="combine_search")
    def combine_search(self, request) -> Response:
        field_filters = {}
        exact_filters = {}
        for param in [
            "asset_name",
            "asset_specification",
            "asset_brand",
            "asset_code",
            "asset_contract",
            "asset_contract_name",
        ]:
            value = request.query_params.get(param, "").strip()
            if value:
                field_filters[param] = value
        for param in ["asset_current_status", "asset_type", "asset_storage"]:
            value = request.query_params.get(param, "").strip()
            if value:
                exact_filters[param] = value
        assets = self._scoped(AssetSelector.combine_search(field_filters, exact_filters))
        page = self.paginate_queryset(assets)
        if page is not None:
            serializer = AssetListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = AssetListSerializer(assets, many=True)
        return success_response(data={"count": assets.count(), "results": serializer.data}, message="查询成功")

    @action(detail=False, methods=["get"], url_path="search")
    def search_assets(self, request) -> Response:
        keyword = request.query_params.get("keyword", "").strip() or None
        status_filter = request.query_params.get("status", "").strip() or None
        asset_type = request.query_params.get("asset_type", "").strip() or None
        storage_code = request.query_params.get("storage_code", "").strip() or None
        contract_code = request.query_params.get("contract_code", "").strip() or None
        assets = self._scoped(
            AssetSelector.search_assets(
                keyword=keyword,
                status=status_filter,
                asset_type=asset_type,
                storage_code=storage_code,
                contract_code=contract_code,
            )
        )
        page = self.paginate_queryset(assets)
        if page is not None:
            serializer = AssetDetailSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = AssetDetailSerializer(assets, many=True)
        return success_response(data={"count": assets.count(), "results": serializer.data}, message="查询成功")

    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request) -> Response:
        stats = AssetService.get_asset_statistics(user=self.request.user)
        return success_response(data=stats, message="查询成功")

    @action(
        detail=False, methods=["get"], url_path="search_available", permission_classes=[permissions.IsAuthenticated]
    )
    def search_available(self, request) -> Response:
        available = self._scoped(
            AssetSelector.get_available_assets(
                asset_code=request.query_params.get("asset_code"),
                asset_name=request.query_params.get("asset_name"),
                asset_specification=request.query_params.get("asset_specification"),
                asset_brand=request.query_params.get("asset_brand"),
                asset_contract_code=request.query_params.get("asset_contract_code"),
                asset_contract_name=request.query_params.get("asset_contract_name"),
            )
        )
        page = self.paginate_queryset(available)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(available, many=True)
        return success_response(data={"count": available.count(), "results": serializer.data})

    @extend_schema(
        deprecated=True,
        description=(
            "[已废弃] UI 已切换至专用状态接口(出库/回收/送修/报废等), 此端点仅供系统管理员数据修复使用. "
            "注意: 仅执行状态机合法边转换并记录审计, 不创建任何业务单据, 变更后须人工补录对应单据."
        ),
    )
    @action(detail=True, methods=["post"], url_path="change_status")
    def change_status(self, request, recordcode=None) -> Response:
        """废弃端点: 手动状态变更(仅限系统管理员数据修复, 不创建业务单据)"""
        asset = self.get_object()
        asset_code = asset.asset_code
        new_status = request.data.get("status")
        description = request.data.get("description", "")
        asset = AssetService.change_asset_status(
            asset_code,
            new_status,
            description,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        serializer = AssetDetailSerializer(asset)
        return success_response(
            data={"asset": serializer.data},
            message=f"状态已更改为: {ASSET_STATUS_MAP.get(new_status, new_status)}",
        )

    @extend_schema(
        description="更新资产申请人和资产保管人信息",
        parameters=[
            OpenApiParameter(
                name="change_outasset_employee", description="更新资产申请人和资产保管人信息", required=False, type=str
            )
        ],
    )
    @action(detail=True, methods=["POST"], url_path="change_outasset_employee")
    def change_outasset_employee(self, request, recordcode=None) -> Response:
        asset = self.get_object()
        asset_code = asset.asset_code
        applicant_jobcode = request.data.get("applicant_jobcode")
        manager_jobcode = request.data.get("manager_jobcode")
        asset = AssetService.change_outasset_employee(asset_code, applicant_jobcode, manager_jobcode)
        serializer = AssetDetailSerializer(asset)
        return success_response(
            data={"asset": serializer.data},
            message=f"资产 {asset_code} 已更新资产申请人 {applicant_jobcode} 和资产保管人 {manager_jobcode}",
        )

    @action(detail=False, methods=["get"], url_path="combined_details")
    def combined_details(self, request) -> Response:
        asset_code = request.query_params.get("asset_code")
        if not asset_code:
            return error_response(message="请提供资产编码", status_code=400)
        visible = self._scoped(AssetSelector.get_assets_for_list()).filter(asset_code=asset_code).first()
        if visible is None:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        data = CombinedAssetSerializer.get_asset_details_data(asset_code)
        return success_response(data=data, message="查询成功")

    @action(detail=False, methods=["get"], url_path="contract_by_asset/(?P<asset_code>[^/.]+)")
    def contract_by_asset(self, request, asset_code=None) -> Response:
        if not asset_code:
            return error_response(message="请提供资产编码", status_code=400)
        asset = self._scoped(AssetSelector.get_assets_for_list()).filter(asset_code=asset_code).first()
        if asset is None:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        contract = asset.asset_contract_recordcode
        if contract is None:
            return error_response(message=f"资产 {asset_code} 未关联合同", status_code=404)
        serializer = ContractDetailSerializer(contract)
        return success_response(data=serializer.data, message="查询成功")

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = AssetBatchCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="参数验证失败", status_code=400, errors=serializer.errors)
        result = AssetService.batch_create_asset(
            serializer.validated_data["items"],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        # 【DR-1/B-8】响应组装复用 BatchResponseHelper; input_data 以用户原始输入回显
        return BatchResponseHelper.create_response(
            result,
            AssetDetailSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
            request_items=serializer.initial_data.get("items"),
        )

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = AssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        scoped_codes = set(
            self.get_queryset().filter(asset_code__in=ids).values_list("asset_code", flat=True)
        )
        # RBAC: 越权/不存在资产不进入删除流程(视同不存在)
        result = AssetService.batch_delete_asset(
            [code for code in ids if code in scoped_codes],
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_ids": result["success_ids"],
                "fail_items": result["fail_items"],
            },
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @action(detail=True, methods=["post"], url_path="mark-broken", permission_classes=[IsAssetAdminOrAbove])
    def mark_broken(self, request, recordcode=None):
        """POST /assets/{recordcode}/mark-broken/ — 标记资产损坏"""
        asset = self.get_object()
        asset = AssetService.mark_asset_broken(
            asset_code=asset.asset_code,
            broken_reason=request.data.get("broken_reason", ""),
            broken_description=request.data.get("broken_description", ""),
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=AssetDetailSerializer(asset).data, message="资产已标记为损坏")

    @action(detail=True, methods=["post"], url_path="mark-lost", permission_classes=[IsAssetAdminOrAbove])
    def mark_lost(self, request, recordcode=None):
        """POST /assets/{recordcode}/mark-lost/ — 标记资产遗失"""
        asset = self.get_object()
        asset = AssetService.mark_asset_lost(
            asset_code=asset.asset_code,
            lost_reason=request.data.get("lost_reason", ""),
            last_known_location=request.data.get("last_known_location", ""),
            lost_description=request.data.get("lost_description", ""),
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=AssetDetailSerializer(asset).data, message="资产已标记为遗失")

    @action(detail=True, methods=["post"], url_path="found")
    def found_and_return(self, request, recordcode=None):
        asset = self.get_object()
        asset = AssetService.find_and_return_asset(
            asset_code=asset.asset_code,
            found_location=request.data.get("found_location", ""),
            found_description=request.data.get("found_description", ""),
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=AssetDetailSerializer(asset).data, message="遗失资产已找回并入库")

    @action(detail=True, methods=["post"], url_path="repair")
    def repair(self, request, recordcode=None):
        asset = self.get_object()
        from apps.assetmanagement.serializers.repair_asset_serializers import RepairAssetDetailSerializer

        repair_record = RepairAssetService.create_repair_asset(
            asset_code=asset.asset_code,
            repair_reason=request.data.get("repair_reason", ""),
            repair_date=request.data.get("repair_date", ""),
            repair_description=request.data.get("repair_description", ""),
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(
            data=RepairAssetDetailSerializer(repair_record).data, message="Asset sent for repair"
        )

    @action(detail=True, methods=["post"], url_path="repair-done")
    def repair_done(self, request, recordcode=None):
        asset = self.get_object()
        from apps.assetmanagement.serializers.repair_asset_serializers import RepairAssetDetailSerializer

        repair_record = RepairAssetService.complete_repair(
            asset_code=asset.asset_code,
            actual_return_date=request.data.get("actual_return_date", ""),
            physical_grade_after=request.data.get("physical_grade_after", ""),
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=RepairAssetDetailSerializer(repair_record).data, message="Repair completed")

    @action(detail=True, methods=["post"], url_path="repair-failed")
    def repair_failed(self, request, recordcode=None):
        asset = self.get_object()
        from apps.assetmanagement.serializers.repair_asset_serializers import RepairAssetDetailSerializer

        repair_record = RepairAssetService.fail_repair(
            asset_code=asset.asset_code,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=RepairAssetDetailSerializer(repair_record).data, message="Repair failed")

    # =====================================================================
    # P1-6: 以资产为中心的 Action 端点(规范文档路径对齐)
    # 这些端点是对现有子资源 API 的补充,提供规范文档定义的路径风格
    # =====================================================================

    @action(detail=True, methods=["get"], url_path="logs", permission_classes=[permissions.IsAuthenticated])
    def status_log(self, request, recordcode=None):
        """GET /assets/{recordcode}/logs/ — 获取资产状态变更日志"""
        asset = self.get_object()
        from apps.assetmanagement.selectors import AssetSelector
        from apps.assetmanagement.serializers import AssetOperationLogSerializer
        from utils.response_utils import success_response

        logs = AssetSelector.get_operation_logs_for_asset(asset)
        return success_response(data=AssetOperationLogSerializer(logs, many=True).data)

    @action(detail=True, methods=["get"], url_path="qr-code-image", permission_classes=[permissions.IsAuthenticated])
    def qr_code_image(self, request, recordcode=None):
        """GET /assets/{recordcode}/qr-code-image/ — 生成资产二维码 PNG 图片"""
        asset = self.get_object()
        try:
            from django.conf import settings
            from django.http import HttpResponse

            from apps.assetmanagement.services import AssetService

            base_url = settings.FRONTEND_BASE_URL
            png_data = AssetService.generate_qr_code_image(asset, base_url)
            response = HttpResponse(png_data, content_type="image/png")
            response["Content-Disposition"] = f'inline; filename="qr_{asset.asset_code}.png"'
            return response
        except ImportError:
            return error_response(message="缺少 qrcode 依赖,请安装:pip install qrcode[pil]", status_code=500)
