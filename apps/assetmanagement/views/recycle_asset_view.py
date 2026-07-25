"""
回收资产管理视图集
"""

import logging

from django.db.models import QuerySet
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.exceptions import AppValidationError
from core.permissions import IsAssetAdminOrAbove
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from utils.response_utils import error_response, success_response

from apps.assetmanagement.models import RecycleAsset
from apps.assetmanagement.selectors import AssetSelector, RecycleAssetSelector
from apps.assetmanagement.serializers import (
    RecycleAssetBatchCreateSerializer,
    RecycleAssetBatchDeleteSerializer,
    RecycleAssetCreateSerializer,
    RecycleAssetDetailSerializer,
    RecycleAssetListSerializer,
    RecycleAssetUpdateSerializer,
)
from apps.assetmanagement.services import RecycleAssetService
from apps.assetmanagement.serializers import OutAssetDetailSerializer

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin
from ._export_mixin import ExportExcelMixin


@extend_schema(tags=["回收管理"])
class RecycleAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = RecycleAsset.objects.filter(is_deleted=False)
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        "asset_recordcode",
        "operator_employee",
        "outasset_recordcode",
    ]
    search_fields = [
        "asset_recordcode__asset_name",
        "outasset_recordcode__recordcode",
        "operator_employee__employee_name",
    ]
    ordering_fields = ["recycle_asset_date", "recordcode"]
    ordering = ["-recycle_asset_date"]
    lookup_field = "recordcode"
    admin_actions = [
        "create", "update", "partial_update", "destroy",
        "batch_create", "batch_delete",
        "cancel_recycle", "reissue",
    ]

    # 导出配置
    export_columns = [
        {"header": "资产编码", "field": "asset_recordcode__asset_code"},
        {"header": "资产名称", "field": "asset_recordcode__asset_name"},
        {"header": "回收日期", "field": "recycle_asset_date"},
        {"header": "回收数量", "field": "recycle_asset_number"},
        {"header": "操作人", "field": "operator_employee__employee_name"},
    ]
    export_filename = "recycle_assets_export.xlsx"
    export_sheet_name = "回收记录"


    def get_permissions(self):
        """RBAC: 写操作需 IsAssetAdminOrAbove+，读操作需认证"""
        if self.action in self.admin_actions:
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]
    def get_serializer_class(self) -> type:
        if self.action == "list":
            return RecycleAssetListSerializer
        elif self.action == "create":
            return RecycleAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return RecycleAssetUpdateSerializer
        return RecycleAssetDetailSerializer

    def get_queryset(self) -> QuerySet[RecycleAsset]:
        # RBAC 行级数据隔离
        if self.action == "list":
            qs = RecycleAssetSelector.get_queryset_for_user(self.request.user)
        else:
            # 【性能优化】复用模型 QuerySet 的 with_asset_details() 方法
            qs = RecycleAssetSelector.get_queryset_for_user(self.request.user).with_asset_details()

        date_from = self.request.query_params.get("recycle_date_from")
        date_to = self.request.query_params.get("recycle_date_to")
        if date_from:
            qs = qs.filter(recycle_asset_date__gte=date_from)
        if date_to:
            qs = qs.filter(recycle_asset_date__lte=date_to)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            recycle = RecycleAssetService.create_recycle_asset(
                serializer.validated_data,
                operator_jobcode=request.user.auth_username,
                operator_name=request.user.auth_username,
            )
            return success_response(
                data=RecycleAssetCreateSerializer(recycle).data, message="回收成功", status_code=status.HTTP_201_CREATED
            )
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception:
            logging.exception("回收创建失败")
            return error_response(message="回收失败，服务器内部错误", status_code=500)

    def update(self, request, *args, **kwargs):
        recordcode = self.kwargs.get("recordcode")
        try:
            serializer = RecycleAssetUpdateSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            recycle = RecycleAssetService.update_recycle_asset(
                recordcode=recordcode,
                update_data=serializer.validated_data,
                operator_jobcode=request.user.auth_username,
                operator_name=request.user.auth_username,
            )
            return success_response(data=RecycleAssetDetailSerializer(recycle).data, message="更新成功")
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception:
            logging.exception("回收记录更新失败")
            return error_response(message="更新失败，请稍后重试", status_code=500)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_recordcode_code>[^/.]+)")
    def by_asset(self, request, asset_recordcode_code=None) -> Response:
        asset = AssetSelector.get_asset_by_code(asset_recordcode_code)
        if asset is None:
            return error_response(message=f"资产 {asset_recordcode_code} 不存在", status_code=404)
        records = RecycleAssetSelector.get_by_asset_code(asset_recordcode_code)
        return self._paginate_and_respond(records)

    @extend_schema(
        parameters=[
            OpenApiParameter(name="recordcode", type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)
        ],
        responses={200: RecycleAssetDetailSerializer},
    )
    @action(detail=False, methods=["get"], url_path="by-outasset/(?P<recordcode>[^/.]+)")
    def by_asset_recordcode(self, request, recordcode=None) -> Response:
        if not recordcode:
            return error_response(message="请提供出库记录编码", status_code=400)
        from apps.assetmanagement.selectors import RecycleAssetSelector
        record = RecycleAssetSelector.get_by_outasset_recordcode(recordcode)
        if record is None:
            return error_response(message=f"未找到出库记录 {recordcode} 对应的回收记录", status_code=404)
        serializer = RecycleAssetDetailSerializer(record)
        return success_response(data=serializer.data, message="查询成功")

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = RecycleAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        storage_obj = serializer.validated_data.get("recycle_asset_storage")
        recycle_person_obj = serializer.validated_data.get("recycle_asset_recycle_person_jobcode")

        storage_code = storage_obj.storage_code if storage_obj else None
        person_jobcode = recycle_person_obj.employee_jobcode if recycle_person_obj else None

        mapped_items = []
        for item in serializer.validated_data["items"]:
            mapped = {
                "outasset_recordcode": item["outasset_recordcode_code"].recordcode,
                "recycle_asset_date": item.get("recycle_date"),
                "recycle_type": item.get("recycle_type"),
                "recycle_asset_description": item.get("recycle_description", ""),
            }
            if storage_code:
                mapped["recycle_asset_storage"] = storage_code
            if person_jobcode:
                mapped["recycle_asset_recycle_person_jobcode"] = person_jobcode
            mapped_items.append(mapped)

        result = RecycleAssetService.batch_create_recycle_asset(
            mapped_items, operator_jobcode=request.user.auth_username, operator_name=request.user.auth_username
        )
        success_serializer = RecycleAssetCreateSerializer(result["success_items"], many=True)
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": success_serializer.data,
                "fail_items": result["fail_items"],
            },
            message=f"批量回收完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条",
        )

    def destroy(self, request, *args, **kwargs):
        try:
            asset_recordcode = self.get_object()
            result = RecycleAssetService.batch_delete_recycle_asset(
                recordcodes=[asset_recordcode.recordcode],
                operator_jobcode=request.user.auth_username,
                operator_name=request.user.auth_username,
            )
            if result["fail_count"] > 0:
                fail_item = result["fail_items"][0]
                return error_response(
                    message=fail_item["error_message"], status_code=400, business_code=fail_item.get("error_code")
                )
            return success_response(message="删除成功")
        except AppValidationError as e:
            return error_response(message=str(e.detail), status_code=400)
        except Exception:
            logging.exception("回收记录删除失败")
            return error_response(message="删除失败，请稍后重试", status_code=500)

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = RecycleAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = RecycleAssetService.batch_delete_recycle_asset(
            serializer.validated_data["ids"],
            operator_jobcode=request.user.auth_username,
            operator_name=request.user.auth_username,
        )
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_ids": result["success_ids"],
                "fail_items": result["fail_items"],
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条",
        )

    @action(detail=True, methods=["post"], url_path="cancel", permission_classes=[IsAssetAdminOrAbove])
    def cancel_recycle(self, request, recordcode=None):
        """POST /recycle-assets/{recordcode}/cancel/ — 取消回收，恢复资产到在用状态"""
        recycle = self.get_object()
        try:
            result = RecycleAssetService.batch_delete_recycle_asset(
                recordcodes=[recycle.recordcode],
                operator_jobcode=request.user.auth_username,
                operator_name=request.user.auth_username,
            )
            if result["fail_count"] > 0:
                fail_item = result["fail_items"][0]
                return error_response(
                    message=fail_item["error_message"], status_code=400, business_code=fail_item.get("error_code")
                )
            return success_response(message="取消回收成功，资产状态已恢复为在用")
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception:
            logging.exception("取消回收失败")
            return error_response(message="取消回收失败，请稍后重试", status_code=500)

    @action(detail=True, methods=["post"], url_path="reissue", permission_classes=[IsAssetAdminOrAbove])
    def reissue(self, request, recordcode=None):
        """POST /recycle-assets/{recordcode}/reissue/ — 重新发放已回收资产"""
        try:
            outasset = RecycleAssetService.reissue_recycle_asset(
                recordcode=recordcode,
                operator_jobcode=request.user.auth_username,
                operator_name=request.user.auth_username,
            )
            return success_response(
                data=OutAssetDetailSerializer(outasset).data,
                message="重新发放成功",
                status_code=status.HTTP_201_CREATED,
            )
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception:
            logging.exception("重新发放失败")
            return error_response(message="重新发放失败，服务器内部错误", status_code=500)
