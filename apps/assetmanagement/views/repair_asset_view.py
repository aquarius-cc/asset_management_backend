"""
维修记录视图集 - 独立文件(DR-5 拆分自 asset_lifecycle_view.py)。

Class:
  - RepairAssetViewSet: 维修记录视图集(路由前缀 repair-assets/)
    - list/create/update/destroy: 标准CRUD(destroy 守卫:in_progress 拒绝)
    - batch_delete: 批量删除维修记录(进行中的记录跳过并返回失败明细)

调用链:
  urls.py -> RepairAssetViewSet -> RepairAssetService/RepairAssetSelector/serializers
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.assetmanagement.selectors import RepairAssetSelector
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.serializers import (
    RepairAssetBatchDeleteSerializer,
    RepairAssetCreateSerializer,
    RepairAssetDetailSerializer,
    RepairAssetListSerializer,
    RepairAssetUpdateSerializer,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from apps.assetmanagement.services.repair_asset_service import RepairAssetService
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


@extend_schema_view(
    list=extend_schema(
        summary="获取维修记录列表",
        description="分页查询维修记录列表,支持筛选、搜索和排序",
        tags=["维修记录"],
    ),
    create=extend_schema(
        summary="创建维修记录",
        description="创建一条新的维修记录",
        tags=["维修记录"],
    ),
    retrieve=extend_schema(
        summary="获取维修记录详情",
        description="根据记录码获取单条维修记录的详细信息",
        tags=["维修记录"],
    ),
    update=extend_schema(
        summary="更新维修记录",
        description="更新维修记录的完整信息",
        tags=["维修记录"],
    ),
    partial_update=extend_schema(
        summary="部分更新维修记录",
        description="部分更新维修记录信息",
        tags=["维修记录"],
    ),
    destroy=extend_schema(
        summary="删除维修记录",
        description="删除指定的维修记录(进行中的记录拒绝)",
        tags=["维修记录"],
    ),
)
class RepairAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    # RepairAssetSelector.get_repair_assets_for_list() 不需要 RBAC,可用作类属性
    queryset = RepairAssetSelector.get_repair_assets_for_list()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["asset_recordcode__asset_name", "repair_reason"]
    ordering_fields = ["repair_date", "created_at"]
    ordering = ["-repair_date"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "batch_delete"):
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return RepairAssetSelector.get_queryset_for_user(self.request.user)

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return RepairAssetListSerializer
        elif self.action == "create":
            return RepairAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return RepairAssetUpdateSerializer
        return RepairAssetDetailSerializer

    def create(self, request, *args, **kwargs):
        """通过 RepairAssetService 创建,确保防重复校验"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        asset = data.get("asset_recordcode")

        operator_jobcode, operator_name = resolve_operator(request.user)
        repair_record = RepairAssetService.create_repair_asset(
            asset_code=asset.asset_code,
            repair_reason=data.get("repair_reason", ""),
            repair_date=str(data.get("repair_date", "")),
            repair_description=data.get("repair_description", ""),
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return success_response(
            data=RepairAssetDetailSerializer(repair_record).data,
            message="创建成功",
            status_code=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        """删除维修记录(进行中的记录拒绝,防止资产卡死 repairing)"""
        obj = self.get_object()
        AssetLifecycleMixin.delete_repair_asset(
            recordcode=obj.recordcode,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data={"recordcode": obj.recordcode}, message="删除成功")

    @extend_schema(
        summary="批量删除维修记录",
        description="批量删除维修记录(进行中的记录将被跳过并返回失败明细)",
        operation_id="repair_asset_batch_delete",
        tags=["维修记录"],
        request=RepairAssetBatchDeleteSerializer,
        responses={
            200: OpenApiResponse(
                description="批量删除完成",
                examples=[
                    OpenApiExample(
                        "成功",
                        value={
                            "code": 0,
                            "message": "批量删除完成",
                            "data": {
                                "total": 3,
                                "success_count": 3,
                                "fail_count": 0,
                                "success_ids": [],
                                "fail_items": [],
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="参数错误"),
        },
    )
    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        from core.batch_mixins import BatchOperationMixin

        serializer = RepairAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        def _delete_one(recordcode: str) -> None:
            AssetLifecycleMixin.delete_repair_asset(
                recordcode=recordcode,
                operator_jobcode=resolve_operator(request.user)[0],
                operator_name=resolve_operator(request.user)[1],
            )

        return success_response(
            data=BatchOperationMixin.batch_delete_execute(ids=ids, process_fn=_delete_one),
            message="批量删除完成",
        )

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_code>[^/.]+)")
    def by_asset(self, request, asset_code=None):
        visible = AssetSelector.get_queryset_for_user(request.user).filter(
            asset_code=asset_code
        ).exists()
        if not visible:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        records = RepairAssetSelector.get_by_asset_code(asset_code, user=request.user)
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(records, many=True)
        return success_response(data=serializer.data, message="查询成功")
