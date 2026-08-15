"""
资产类型管理视图集
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.assetmanagement.models import AssetType
from apps.assetmanagement.serializers import (
    AssetTypeBatchCreateSerializer,
    AssetTypeBatchDeleteSerializer,
    AssetTypeSerializer,
)
from apps.assetmanagement.services import AssetTypeService
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsSystemAdmin
from utils.response_utils import success_response

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class AssetTypeViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = AssetType.objects.all()
    serializer_class = AssetTypeSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_delete",
        "batch_create",
    ]

    def get_permissions(self):
        """RBAC: 写操作需 IsSystemAdmin+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsSystemAdmin()]
        return [permissions.IsAuthenticated()]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["type_code", "type_name", "level"]
    search_fields = ["type_code", "type_name"]
    ordering_fields = ["type_code", "type_name", "sort_order"]
    ordering = ["sort_order", "type_code"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset_type = AssetTypeService.create_asset_type(serializer.validated_data)
        return success_response(
            data=AssetTypeSerializer(asset_type).data, message="创建成功", status_code=status.HTTP_201_CREATED
        )

    def destroy(self, request, *args, **kwargs):
        asset_type = self.get_object()
        AssetTypeService.delete_asset_type(asset_type.type_code)
        return success_response(message="删除成功")

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = AssetTypeBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AssetTypeService.batch_delete_asset_type(serializer.validated_data["ids"])
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

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = AssetTypeBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AssetTypeService.batch_create_asset_type(serializer.validated_data["items"])
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": [AssetTypeSerializer(item).data for item in result.get("success_items", [])],
                "fail_items": result["fail_items"],
            },
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )
