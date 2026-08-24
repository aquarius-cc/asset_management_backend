"""
仓库管理视图集
"""

from typing import Any

from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import Storage
from apps.assetmanagement.selectors import StorageSelector
from apps.assetmanagement.serializers import (
    StorageBatchCreateSerializer,
    StorageBatchDeleteSerializer,
    StorageSerializer,
)
from apps.assetmanagement.services import StorageService
from core.batch_mixins import BatchResponseHelper
from core.constants import STORAGE_TYPE_CHOICES
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from utils.response_utils import success_response
from utils.user_utils import resolve_operator

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class StorageViewSet(  # type: ignore[misc]
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet[Storage],
):
    queryset = Storage.objects.all()
    serializer_class = StorageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["storage_type"]
    ordering_fields = ["storage_code", "storage_name"]
    ordering = ["storage_code"]

    def _base_queryset(self) -> QuerySet[Storage]:
        """基础查询集:仅过滤软删除记录"""
        return Storage.objects.filter(is_deleted=False)

    def get_queryset(self) -> QuerySet[Storage]:
        # RBAC: Storage 为全局资源,仅按软删除过滤
        qs = self._base_queryset()
        keyword = self.request.GET.get("keyword", "").strip()
        if keyword:
            return StorageSelector.search_storages_by_keyword(keyword)
        return qs

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        storage = StorageService.create_storage(
            serializer.validated_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(
            data=StorageSerializer(storage).data,
            message="创建成功",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request: Any) -> Response:
        queryset = self._base_queryset()
        total = queryset.count()
        type_stats_qs = queryset.values("storage_type").annotate(count=Count("id")).order_by("storage_type")
        type_dict = dict(STORAGE_TYPE_CHOICES)
        type_stats = {}
        for item in type_stats_qs:
            code = item["storage_type"]
            type_stats[code] = {"name": type_dict.get(code, code), "count": item["count"]}
        return success_response(data={"total_storages": total, "by_type": type_stats})

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        storage = self.get_object()
        operator_jobcode, operator_name = resolve_operator(request.user)
        StorageService.delete_storage(
            storage.storage_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(message="删除成功")

    @action(detail=False, methods=["post"], url_path="batch-delete")  # type: ignore[type-var]
    def batch_delete(self, request: Any) -> None:
        serializer = StorageBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = StorageService.batch_delete_storage(
            serializer.validated_data["ids"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper
        return BatchResponseHelper.delete_response(  # type: ignore[no-any-return]
            result,
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: Any) -> Response:
        serializer = StorageBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = StorageService.batch_create_storage(
            serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": [StorageSerializer(item).data for item in result.get("success_items", [])],
                "fail_items": result["fail_items"],
            },
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )
