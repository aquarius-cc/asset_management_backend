"""
资产生命周期事件视图集

包含 BrokenAsset(损坏)、LostAsset(遗失)、FoundAsset(找回)视图集。
这些视图集结构高度相似,统一管理。RepairAsset(维修)已拆分至 repair_asset_view.py。
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.assetmanagement.models import BrokenAsset, FoundAsset, LostAsset
from apps.assetmanagement.selectors import (
    BrokenAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
)
from apps.assetmanagement.serializers import (
    BrokenAssetCreateSerializer,
    BrokenAssetDetailSerializer,
    BrokenAssetListSerializer,
    BrokenAssetUpdateSerializer,
    FoundAssetCreateSerializer,
    FoundAssetDetailSerializer,
    FoundAssetListSerializer,
    FoundAssetUpdateSerializer,
    LostAssetCreateSerializer,
    LostAssetDetailSerializer,
    LostAssetListSerializer,
    LostAssetUpdateSerializer,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


@extend_schema(tags=["损坏资产"])
class BrokenAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = BrokenAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["asset_recordcode__asset_name", "broken_reason"]
    ordering_fields = ["broken_date", "created_at"]
    ordering = ["-broken_date"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "batch_delete"):
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return BrokenAssetSelector.get_queryset_for_user(self.request.user)

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return BrokenAssetListSerializer
        elif self.action == "create":
            return BrokenAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return BrokenAssetUpdateSerializer
        return BrokenAssetDetailSerializer

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return error_response(message="缺少 ids 参数", status_code=400)
        success_ids = []
        fail_items = []
        operator_jobcode, operator_name = resolve_operator(request.user)
        for recordcode in ids:
            try:
                AssetLifecycleMixin.delete_broken_asset(
                    recordcode=recordcode,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
                success_ids.append(recordcode)
            except BrokenAsset.DoesNotExist:
                fail_items.append({"id": recordcode, "error_code": "NOT_FOUND", "error_message": "Record not found"})
            except Exception:
                fail_items.append({"id": recordcode, "error_code": "INTERNAL_ERROR", "error_message": "Server error"})
        return success_response(
            data={
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"Batch delete done: {len(success_ids)} success, {len(fail_items)} fail",
        )


@extend_schema(tags=["遗失资产"])
class LostAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = LostAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["asset_recordcode__asset_name", "lost_reason"]
    ordering_fields = ["lost_date", "created_at"]
    ordering = ["-lost_date"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "batch_delete"):
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return LostAssetSelector.get_queryset_for_user(self.request.user)

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return LostAssetListSerializer
        elif self.action == "create":
            return LostAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return LostAssetUpdateSerializer
        return LostAssetDetailSerializer

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return error_response(message="缺少 ids 参数", status_code=400)
        success_ids = []
        fail_items = []
        operator_jobcode, operator_name = resolve_operator(request.user)
        for recordcode in ids:
            try:
                AssetLifecycleMixin.delete_lost_asset(
                    recordcode=recordcode,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
                success_ids.append(recordcode)
            except LostAsset.DoesNotExist:
                fail_items.append({"id": recordcode, "error_code": "NOT_FOUND", "error_message": "Record not found"})
            except Exception:
                fail_items.append({"id": recordcode, "error_code": "INTERNAL_ERROR", "error_message": "Server error"})
        return success_response(
            data={
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"Batch delete done: {len(success_ids)} success, {len(fail_items)} fail",
        )


@extend_schema(tags=["找回资产"])
class FoundAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = FoundAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["asset_recordcode__asset_name"]
    ordering_fields = ["found_date", "created_at"]
    ordering = ["-found_date"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "batch_delete"):
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return FoundAssetSelector.get_queryset_for_user(self.request.user)

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return FoundAssetListSerializer
        elif self.action == "create":
            return FoundAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return FoundAssetUpdateSerializer
        return FoundAssetDetailSerializer

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return error_response(message="缺少 ids 参数", status_code=400)
        success_ids = []
        fail_items = []
        operator_jobcode, operator_name = resolve_operator(request.user)
        for recordcode in ids:
            try:
                AssetLifecycleMixin.delete_found_asset(
                    recordcode=recordcode,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )
                success_ids.append(recordcode)
            except FoundAsset.DoesNotExist:
                fail_items.append({"id": recordcode, "error_code": "NOT_FOUND", "error_message": "Record not found"})
            except Exception:
                fail_items.append({"id": recordcode, "error_code": "INTERNAL_ERROR", "error_message": "Server error"})
        return success_response(
            data={
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"Batch delete done: {len(success_ids)} success, {len(fail_items)} fail",
        )
