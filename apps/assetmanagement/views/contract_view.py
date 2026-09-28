"""
合同管理视图集
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter  # type: ignore[attr-defined]
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import Contract
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.serializers import (
    ContractBatchCreateSerializer,
    ContractBatchDeleteSerializer,
    ContractBatchPaymentRecordSerializer,
    ContractCreateSerializer,
    ContractDetailSerializer,
    ContractListSerializer,
    ContractUpdateSerializer,
)
from apps.assetmanagement.services import ContractService
from core.batch_mixins import BatchDeleteViewMixin
from core.excel_export import ExportExcelMixin
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsSystemAdmin, resolve_viewset_permissions
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class ContractViewSet(  # type: ignore[misc]
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    BatchDeleteViewMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet[Contract],
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
        "payment_record_batch",
        "delete_payment",
        "approve_payment",
    ]

    def get_permissions(self) -> Any:
        """RBAC: 写操作需 IsSystemAdmin+,读操作需认证"""
        return resolve_viewset_permissions(self.action, self.admin_actions, IsSystemAdmin)

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

    def get_queryset(self) -> Any:
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

    def perform_create(self, serializer: Any) -> None:
        """单条创建路由至 Service(B1 分层:B-5 同型,DR-1 禁止绕过业务入口)

        DRF 默认 `perform_create` 走 `ModelSerializer.create()`,即 `objects.create(**validated_data)`,
        会整体绕过 ContractService.create_contract,后果有三:
        ① 决策 2a 的期初已付规范化(转 approved 期初记录)不执行,amount_paid 被裸写;
        ② amount_unpaid 不经 _recalc_paid_amounts,创建后恒为 0;
        ③ 创建审计日志缺失(同文件的 destroy/batch_create 均已走 Service)。
        故此处显式改走 Service,并回填 instance 让 serializer.data 取到落库后的派生值。
        签名用 Any 与 role_view.py 先例一致,兼容 LoggingMixin / CreateModelMixin
        两条父链的 override 约束(LSP),避免 mypy 报参数类型不兼容。
        """
        contract_data = dict(serializer.validated_data)
        request = serializer.context["request"]
        operator_jobcode, operator_name = resolve_operator(request.user)
        contract = ContractService.create_contract(
            contract_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        serializer.instance = contract

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        contract = self.get_object()
        operator_jobcode, operator_name = resolve_operator(request.user)
        ContractService.delete_contract(
            contract.contract_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return success_response(message="删除成功")

    batch_delete_serializer = ContractBatchDeleteSerializer
    batch_delete_service = ContractService.batch_delete_contract

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: Any) -> Response:
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
    @action(detail=False, methods=["get"], url_path="get_contract_by_name/(?P<name>[^/.]+)")
    def getcontractByname(self, request: Any, name: Any = None) -> Response:
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
    def statistics(self, request: Any) -> Response:
        stats = ContractService.get_contract_statistics()
        return success_response(data=stats, message="查询成功")

    @extend_schema(
        summary="更新结算状态",
        # 直接读 request.data.get("status")，无运行时 Serializer，故基线缺
        # requestBody。取值域与本方法错误文案一致（pending/settled）。
        request=inline_serializer(
            name="ContractSettlementStatus",
            fields={
                "status": serializers.ChoiceField(
                    choices=["pending", "settled"],
                    help_text="目标结算状态",
                ),
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="update_settlement_status")
    def update_settlement_status(self, request: Any, recordcode: Any = None) -> Response:
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

    @extend_schema(
        summary="添加付款记录",
        # 直接读 request.data.get(...)，无运行时 Serializer，
        # 故基线缺 requestBody。amount 的范围校验（<=9999999999.99、有限数）
        # 在方法体内手工完成，此处只声明文档结构，不复制校验逻辑。
        # payment_date / payment_method 为 BF-054 新增（历史付款可回填真实日期与支付方式）。
        request=inline_serializer(
            name="ContractPaymentRecord",
            fields={
                "amount": serializers.DecimalField(
                    max_digits=12,
                    decimal_places=2,
                    help_text="付款金额（须为有限数且不超过 9999999999.99）",
                ),
                "description": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="付款说明（默认空串）",
                ),
                "payment_date": serializers.DateField(
                    required=False,
                    help_text="付款发生日期 YYYY-MM-DD（默认当天）",
                ),
                "payment_method": serializers.CharField(
                    required=False,
                    default="bank_transfer",
                    help_text="支付方式（自由文本，仅存于付款明细，不参与查询）",
                ),
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="payment_record")
    def payment_record(self, request: Any, recordcode: Any = None) -> Response:
        amount = request.data.get("amount")
        description = request.data.get("description", "")
        if not amount:
            return error_response(message="请提供付款金额", status_code=400)
        try:
            amount = Decimal(str(amount))
        except (ValueError, InvalidOperation):
            return error_response(message="付款金额格式错误", status_code=400)
        if not amount.is_finite():
            return error_response(message="付款金额必须为有限数字", status_code=400)
        if amount > Decimal("9999999999.99"):
            return error_response(message="付款金额超出允许范围", status_code=400)
        payment_date = request.data.get("payment_date")
        payment_method = request.data.get("payment_method") or "bank_transfer"
        contract = self.get_object()
        updated = ContractService.add_payment_record(
            contract.contract_code,
            amount,
            description,
            payment_date=str(payment_date) if payment_date else None,
            payment_method=str(payment_method),
        )
        serializer = ContractDetailSerializer(instance=updated)
        return success_response(data={"contract": serializer.data}, message="付款记录添加成功")

    @extend_schema(
        summary="批量回填历史付款记录",
        description=(
            "上传已执行合同时一次性回填其历史付款,替代「每笔发 add + approve 两次请求」。"
            "每条回填记录由服务端内部 add → approve 两步落到 approved 状态;该状态不开放为入参,"
            "以保持审批环节的单一入口与可追溯性。需保留待审核状态时请改用单条 "
            "POST /contracts/{recordcode}/payment_record/ 端点。"
        ),
        request=ContractBatchPaymentRecordSerializer,
        responses={200: ContractDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="payment_record/batch")
    def payment_record_batch(self, request: Any, recordcode: Any = None) -> Response:
        serializer = ContractBatchPaymentRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contract = self.get_object()
        items = [
            {
                "amount": item["amount"],
                "description": item.get("description") or "",
                "payment_date": str(item["payment_date"]) if item.get("payment_date") else None,
                "payment_method": item.get("payment_method") or "bank_transfer",
            }
            for item in serializer.validated_data["items"]
        ]
        result = ContractService.add_payment_record_batch(contract.contract_code, items)
        updated = ContractSelector.get_contract_by_code(contract.contract_code) or contract
        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": result["success_items"],
                "fail_items": result["fail_items"],
                "contract": ContractDetailSerializer(instance=updated).data,
            },
            message=f"历史付款回填完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

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
    def global_search(self, request: Any) -> Response:
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

    @action(detail=True, methods=["post"], url_path=r"payment_record/(?P<payment_id>[^/]+)/delete")
    def delete_payment(self, request: Any, recordcode: Any = None, payment_id: Any = None) -> Response:
        """删除支付记录(软删除)"""
        contract = self.get_object()
        updated = ContractService.delete_payment_record(contract.contract_code, payment_id)
        serializer = ContractDetailSerializer(instance=updated)
        return success_response(data={"contract": serializer.data}, message="支付记录删除成功")

    @action(detail=True, methods=["post"], url_path=r"payment_record/(?P<payment_id>[^/]+)/approve")
    def approve_payment(self, request: Any, recordcode: Any = None, payment_id: Any = None) -> Response:
        """审核通过支付记录"""
        contract = self.get_object()
        updated = ContractService.approve_payment_record(contract.contract_code, payment_id)
        serializer = ContractDetailSerializer(instance=updated)
        return success_response(data={"contract": serializer.data}, message="支付记录审核成功")
