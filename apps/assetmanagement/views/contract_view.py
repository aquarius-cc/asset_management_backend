"""
合同管理视图集
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response  # noqa: F401 — used in -> Response annotations

from apps.assetmanagement.models import Contract
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.serializers import (
    ContractBatchCreateSerializer,
    ContractBatchDeleteSerializer,
    ContractCreateSerializer,
    ContractDetailSerializer,
    ContractListSerializer,
    ContractUpdateSerializer,
)
from apps.assetmanagement.services import ContractService
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsSystemAdmin
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class ContractViewSet(
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,
):
    queryset = Contract.objects.all()
    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_delete",
        "batch_create",
        "update_settlement_status",
        "payment_record",
    ]

    def get_permissions(self):
        """RBAC: 写操作需 IsSystemAdmin+,读操作需认证"""
        if self.action in self.admin_actions:
            return [IsSystemAdmin()]
        return [permissions.IsAuthenticated()]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["contract_type", "contract_status"]
    ordering_fields = ["contract_code", "contract_start_date", "contract_amount"]
    ordering = ["-created_at"]

    # 导出配置(HIGH-12)
    export_columns = [
        {"header": "合同编码", "field": "contract_code"},
        {"header": "合同名称", "field": "contract_name"},
        {"header": "合同金额", "field": "contract_amount"},
        {"header": "合同状态", "field": "contract_status"},
        {"header": "签订日期", "field": "contract_sign_date"},
        {"header": "到期日期", "field": "contract_end_date"},
    ]
    export_filename = "contracts_export.xlsx"
    export_sheet_name = "合同列表"

    def get_queryset(self):
        # RBAC: Contract 为全局资源,仅按软删除过滤
        return Contract.objects.filter(is_deleted=False)

    def get_serializer_class(self) -> type:
        if self.action == "list":
            return ContractListSerializer
        elif self.action == "create":
            return ContractCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return ContractUpdateSerializer
        return ContractDetailSerializer

    def destroy(self, request, *args, **kwargs):
        contract = self.get_object()
        operator_jobcode, operator_name = resolve_operator(request.user)
        ContractService.delete_contract(
            contract.contract_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(message="删除成功")

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request):
        serializer = ContractBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = ContractService.batch_delete_contract(
            serializer.validated_data["ids"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
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

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = ContractBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = ContractService.batch_create_contract(
            serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": [ContractCreateSerializer(item).data for item in result.get("success_items", [])],
                "fail_items": result["fail_items"],
            },
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(name="name", type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)
        ],
        responses={200: ContractDetailSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="getcontractByname/(?P<name>[^/.]+)")
    def getcontractByname(self, request, name=None) -> Response:
        name = name.strip() if name else ""
        if not name:
            return error_response(message="合同名称参数不能为空", status_code=400)
        contracts = ContractSelector.search_contracts(keyword=name)
        page = self.paginate_queryset(contracts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(contracts, many=True)
        return success_response(data={"count": contracts.count(), "results": serializer.data}, message="查询成功")

    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request) -> Response:
        stats = ContractService.get_contract_statistics()
        return success_response(data=stats, message="查询成功")

    @action(detail=True, methods=["post"], url_path="update_settlement_status")
    def update_settlement_status(self, request, recordcode=None) -> Response:
        new_status = request.data.get("status")
        if not new_status:
            return error_response(message="请提供结算状态(pending/settled)", status_code=400)
        contract = self.get_object()
        operator_jobcode, operator_name = resolve_operator(request.user)
        updated = ContractService.update_settlement_status(
            contract.contract_code,
            new_status,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        serializer = ContractDetailSerializer(instance=updated)
        return success_response(data={"contract": serializer.data}, message="结算状态更新成功")

    @action(detail=True, methods=["post"], url_path="payment_record")
    def payment_record(self, request, recordcode=None) -> Response:
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        if not amount:
            return error_response(message="请提供付款金额", status_code=400)
        try:
            amount = float(amount)
        except ValueError:
            return error_response(message="付款金额格式错误", status_code=400)
        contract = self.get_object()
        updated = ContractService.add_payment_record(contract.contract_code, amount, description)
        serializer = ContractDetailSerializer(instance=updated)
        return success_response(data={"contract": serializer.data}, message="付款记录添加成功")

    @extend_schema(
        summary="全局模糊搜索合同",
        parameters=[
            OpenApiParameter(name="keyword", type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter(name="page", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="page_size", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: ContractDetailSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="search")
    def global_search(self, request) -> Response:
        keyword = request.query_params.get("keyword", "").strip()
        if not keyword:
            return error_response(message="请提供搜索关键词", status_code=400)
        contracts = ContractSelector.search_contracts(keyword=keyword)
        page = self.paginate_queryset(contracts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(contracts, many=True)
        return success_response(data={"count": contracts.count(), "results": serializer.data}, message="查询成功")
