"""
待报废资产视图集

提供待报废资产的 CRUD 操作和审批功能。
业务流程：待报废审批通过后，自动流转为已报废资产。
"""

import logging

from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from core.constants import APPROVAL_STATUS_CHOICES
from core.exceptions import AppValidationError
from core.permissions import IsDeptManagerOrAbove
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from utils.response_utils import error_response, success_response

from apps.assetmanagement.models import DamagedAsset
from apps.assetmanagement.selectors import AssetSelector, DamagedAssetSelector
from apps.assetmanagement.serializers import (
    DamagedAssetAproveSerializer,
    DamagedAssetBatchDeleteSerializer,
    DamagedAssetCreateSerializer,
    DamagedAssetDetailSerializer,
    DamagedAssetListSerializer,
    DamagedAssetSerializer,
    DamagedAssetUpdateSerializer,
    WasteAssetDetailSerializer,
)
from apps.assetmanagement.services import DamagedAssetService

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin
from ._export_mixin import ExportExcelMixin


class DamagedAssetViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = DamagedAsset.objects.select_related(
        "asset_recordcode",
        "asset_recordcode__asset_type_recordcode",
        "asset_recordcode__asset_contract_recordcode",
        "asset_recordcode__asset_storage_recordcode",
        "asset_recordcode__asset_manager_recordcode",
        "approver",
    ).all()
    serializer_class = DamagedAssetSerializer
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"
    admin_actions = ["update", "partial_update", "destroy", "approve", "reject", "batch_delete"]

    # 导出配置
    export_columns = [
        {"header": "资产编码", "field": "asset_recordcode__asset_code"},
        {"header": "资产名称", "field": "asset_recordcode__asset_name"},
        {"header": "审批状态", "field": "approval_status"},
        {"header": "原状态", "field": "original_status"},
        {"header": "损坏数量", "field": "damaged_asset_number"},
        {"header": "损坏日期", "field": "damaged_asset_date"},
    ]
    export_filename = "damaged_assets_export.xlsx"
    export_sheet_name = "待报废资产"


    def get_permissions(self):
        """RBAC: 写操作需 IsDeptManagerOrAbove+，读操作需认证"""
        if self.action in self.admin_actions:
            return [IsDeptManagerOrAbove()]
        return [permissions.IsAuthenticated()]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["approval_status"]
    search_fields = ["asset_recordcode__asset_name"]
    ordering_fields = ["damaged_date"]
    ordering = ["-damaged_date"]

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return DamagedAssetListSerializer
        elif self.action == "create":
            return DamagedAssetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return DamagedAssetUpdateSerializer
        elif self.action in ["approve", "reject"]:
            return DamagedAssetAproveSerializer
        return DamagedAssetDetailSerializer

    def get_queryset(self):
        # RBAC 行级数据隔离
        if self.action == "list":
            return DamagedAssetSelector.get_queryset_for_user(self.request.user)
        return DamagedAsset.objects.select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "approver",
        ).filter(is_deleted=False)

    def destroy(self, request, *args, **kwargs):
        try:
            obj = self.get_object()
            asset_recordcode = obj.asset_recordcode.recordcode if obj.asset_recordcode else None
            if not asset_recordcode:
                return error_response(message="关联资产不存在", status_code=400)
            DamagedAssetService.cancel_asset_recordcode(
                asset_recordcode_code=asset_recordcode,
                operator_jobcode=request.user.auth_id,
                operator_name=request.user.auth_username,
            )
            return success_response(message="取消待报废申请成功")
        except AppValidationError as e:
            return error_response(message=str(e.detail), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"取消待报废申请失败: {e}")
            return error_response(message="操作失败，请稍后重试", status_code=500)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message=str(serializer.errors), status_code=status.HTTP_400_BAD_REQUEST)
        try:
            damaged_data = serializer.validated_data
            damaged_data["asset_recordcode"] = damaged_data.get("asset_recordcode")
            damaged_data["damaged_date"] = damaged_data.get("damaged_date", timezone.now().date())
            damaged_data["damaged_asset_description"] = damaged_data.get("damaged_asset_description", "")
            damaged_data["damaged_asset_number"] = damaged_data.get("damaged_asset_number", 1)
            damaged_asset = DamagedAssetService.create_damaged_asset(
                damaged_data=damaged_data,
                operator_jobcode=request.user.auth_id,
                operator_name=request.user.auth_username,
            )
            return success_response(
                data=DamagedAssetCreateSerializer(damaged_asset).data,
                message="创建待报废记录成功",
                status_code=status.HTTP_201_CREATED,
            )
        except AppValidationError as e:
            return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"创建待报废记录失败: {e}")
            return error_response(message="创建失败，请稍后重试", status_code=500)

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.approval_status != "pending":
            return error_response(
                message=f"当前审批状态为 {obj.approval_status}，不允许修改",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(obj, data=request.data)
        if not serializer.is_valid():
            return error_response(message=str(serializer.errors), status_code=status.HTTP_400_BAD_REQUEST)
        try:
            serializer.save()
            return success_response(
                data=DamagedAssetUpdateSerializer(serializer.instance).data, message="更新待报废记录成功"
            )
        except Exception as e:
            logging.exception(f"更新待报废记录失败: {e}")
            return error_response(message="更新失败，请稍后重试", status_code=500)

    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.approval_status != "pending":
            return error_response(
                message=f"当前审批状态为 {obj.approval_status}，不允许修改",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message=str(serializer.errors), status_code=status.HTTP_400_BAD_REQUEST)
        try:
            serializer.save()
            return success_response(
                data=DamagedAssetUpdateSerializer(serializer.instance).data, message="更新待报废记录成功"
            )
        except Exception as e:
            logging.exception(f"更新待报废记录失败: {e}")
            return error_response(message="更新失败，请稍后重试", status_code=500)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, recordcode=None, **kwargs) -> Response:
        try:
            obj = self.get_object()
            asset_recordcode = obj.asset_recordcode.recordcode if obj.asset_recordcode else None
            if not asset_recordcode:
                return error_response(message="关联资产不存在", status_code=400)
            approver_jobcode = request.data.get("approver_jobcode") or request.user.auth_id
            operator_name = request.data.get("operator_name") or request.user.auth_username
            result = DamagedAssetService.approve_asset_recordcode(
                asset_recordcode_code=asset_recordcode, approver_jobcode=approver_jobcode, operator_name=operator_name
            )
            return success_response(
                data={
                    "damaged_asset": DamagedAssetDetailSerializer(result["damaged_asset"]).data,
                    "waste_asset": WasteAssetDetailSerializer(result["waste_asset"]).data,
                },
                message="审批通过，已报废记录已创建",
            )
        except AppValidationError as e:
            return error_response(message=str(e.detail), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"审批待报废申请失败: {e}")
            return error_response(message="审批失败，请稍后重试", status_code=500)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, recordcode=None, **kwargs) -> Response:
        try:
            obj = self.get_object()
            asset_recordcode = obj.asset_recordcode.recordcode if obj.asset_recordcode else None
            if not asset_recordcode:
                return error_response(message="关联资产不存在", status_code=400)
            approver_jobcode = request.data.get("approver_jobcode") or request.user.auth_id
            operator_name = request.data.get("operator_name") or request.user.auth_username
            result = DamagedAssetService.reject_asset_recordcode(
                asset_recordcode_code=asset_recordcode, approver_jobcode=approver_jobcode, operator_name=operator_name
            )
            return success_response(data=DamagedAssetDetailSerializer(result).data, message="审批拒绝成功")
        except AppValidationError as e:
            return error_response(message=str(e.detail), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"拒绝待报废申请失败: {e}")
            return error_response(message="审批失败，请稍后重试", status_code=500)

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_recordcode>[^/.]+)")
    def by_asset(self, request, asset_recordcode=None) -> Response:
        asset = AssetSelector.get_asset_by_code(asset_recordcode)
        if asset is None:
            return error_response(message=f"资产 {asset_recordcode} 不存在", status_code=404)
        records = DamagedAssetSelector.get_by_asset_code(asset_recordcode)
        return self._paginate_and_respond(records)

    @action(detail=False, methods=["get"])
    def statistics(self, request) -> Response:
        queryset = self.queryset
        total = queryset.count()
        status_stats = queryset.values("approval_status").annotate(count=Count("id")).order_by("approval_status")
        status_dict = dict(APPROVAL_STATUS_CHOICES)
        by_status = {
            item["approval_status"]: {
                "name": status_dict.get(item["approval_status"], item["approval_status"]),
                "count": item["count"],
            }
            for item in status_stats
        }
        return success_response(data={"total_damaged": total, "by_status": by_status})

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = DamagedAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        success_ids = []
        fail_items = []
        for asset_recordcode_code in ids:
            try:
                DamagedAssetService.cancel_asset_recordcode(asset_recordcode_code)
                success_ids.append(asset_recordcode_code)
            except AppValidationError as e:
                fail_items.append({"id": asset_recordcode_code, "error_code": "VALIDATION_ERROR", "error_message": str(e)})
            except Exception:
                fail_items.append({"id": asset_recordcode_code, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误"})
        return success_response(
            data={
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"批量删除完成，成功 {len(success_ids)} 条，失败 {len(fail_items)} 条",
        )
