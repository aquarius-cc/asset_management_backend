"""
硬盘序列号管理视图集
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import HardDiskSN
from apps.assetmanagement.selectors import AssetSelector, HardDiskSNSelector
from apps.assetmanagement.serializers import (
    HardDiskSNBatchSerializer,
    HardDiskSNSerializer,
)
from apps.assetmanagement.services import HardDiskSNService
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class HardDiskSNViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = HardDiskSN.objects.select_related("asset_recordcode").all()
    serializer_class = HardDiskSNSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["harddisk_status", "harddisk_type", "asset_recordcode"]
    search_fields = ["harddisk_sn_code", "harddisk_description"]
    ordering_fields = ["created_at", "harddisk_sn_code"]
    ordering = ["-created_at"]
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_save",
    ]

    def get_queryset(self):
        # RBAC 行级数据隔离(硬盘通过 asset_recordcode 关联到 Asset)
        return HardDiskSNSelector.get_queryset_for_user(self.request.user)

    def get_permissions(self):
        """RBAC: 写操作需 IsAssetAdminOrAbove+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        harddisk = HardDiskSNService.create(
            data=serializer.validated_data,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(
            data=HardDiskSNSerializer(harddisk).data,
            message="创建成功",
            status_code=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        recordcode = self.kwargs.get("recordcode")
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        harddisk = HardDiskSNService.update(
            recordcode=recordcode,
            update_data=serializer.validated_data,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(data=HardDiskSNSerializer(harddisk).data, message="更新成功")

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        recordcode = self.kwargs.get("recordcode")
        HardDiskSNService.delete(
            recordcode=recordcode,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
        )
        return success_response(message="删除成功")

    @action(detail=False, methods=["post"])
    def search_by_serial_number(self, request) -> Response:
        serial = request.data.get("harddisk_sn_code")
        if not serial:
            return error_response(message="请提供硬盘序列号", status_code=400)
        record = self.get_queryset().filter(harddisk_sn_code=serial).first()
        if record is None:
            return error_response(message="硬盘序列号不存在", status_code=404)
        serializer = self.get_serializer(record)
        return success_response(data=serializer.data)

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_code>[^/.]+)")
    def by_asset(self, request, asset_code=None) -> Response:
        visible_asset = AssetSelector.get_queryset_for_user(request.user).filter(asset_code=asset_code).exists()
        if not visible_asset:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        records = self.get_queryset().filter(asset_recordcode__asset_code=asset_code).order_by("harddisk_sn_code")
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(records, many=True)
        return success_response(data=serializer.data)

    @action(detail=False, methods=["post"], url_path="batch-save")
    def batch_save(self, request) -> Response:
        serializer = HardDiskSNBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = HardDiskSNService.batch_save(
            asset_recordcode=serializer.validated_data["asset_recordcode"],
            disks=serializer.validated_data["disks"],
        )
        return success_response(
            data=result,
            message=f"批量保存成功,新增 {result['created']} 条,更新 {result['updated']} 条",
            status_code=status.HTTP_200_OK,
        )
