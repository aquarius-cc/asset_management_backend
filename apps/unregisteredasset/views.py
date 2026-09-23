"""
未登记资产视图集

该模块定义 DRF ViewSet,提供未登记资产的 RESTful API。

【AGENTS 规范 - 视图层】
- 职责分离:View 只处理 HTTP 请求/响应,业务逻辑委托 Service
- 权限控制:使用 DRF 权限类
- 序列化器选择:根据动作选择不同的序列化器
- 异常处理:捕获业务异常转换为 HTTP 响应

【API 端点】
- GET    /api/v1/unregistered-assets/          列表
- POST   /api/v1/unregistered-assets/          创建
- GET    /api/v1/unregistered-assets/{code}/   详情
- PUT    /api/v1/unregistered-assets/{code}/   更新
- DELETE /api/v1/unregistered-assets/{code}/   删除
- POST   /api/v1/unregistered-assets/{code}/approve/ 审批
"""

from typing import Any

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.selectors import UnregisteredAssetSelector
from apps.unregisteredasset.serializers import (
    UnregisteredAssetApproveSerializer,
    UnregisteredAssetBatchDeleteSerializer,
    UnregisteredAssetCreateSerializer,
    UnregisteredAssetDetailSerializer,
    UnregisteredAssetListSerializer,
    UnregisteredAssetUpdateSerializer,
)
from apps.unregisteredasset.services import UnregisteredAssetService
from core.batch_mixins import BatchDeleteViewMixin, BatchResponseHelper
from core.constants import MAX_BATCH_SIZE
from core.mixins import LoggingMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsDeptManagerOrAbove, IsSystemAdmin
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator


class UnregisteredAssetViewSet(BatchDeleteViewMixin, LoggingMixin, ResponseWrapperMixin, ModelViewSet[UnregisteredAsset]):  # type: ignore[misc]
    """
    未登记资产视图集

    提供未登记资产的 CRUD 和审批操作。

    【权限控制】
    - 列表/详情:认证用户可访问
    - 创建:认证用户
    - 更新:认证用户
    - 删除/批量删除:系统管理员(IsSystemAdmin,替代遗留 is_staff 门禁)
    - 审批:部门经理及以上

    【序列化器映射】
    - list: UnregisteredAssetListSerializer
    - retrieve: UnregisteredAssetDetailSerializer
    - create: UnregisteredAssetCreateSerializer
    - update: UnregisteredAssetUpdateSerializer
    - approve: UnregisteredAssetApproveSerializer
    """

    queryset = UnregisteredAsset.objects.all()
    serializer_class = UnregisteredAssetListSerializer
    pagination_class = CustomPageNumberPagination
    # 默认权限:需要认证
    permission_classes = [IsAuthenticated]

    # filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["scenario_type", "approval_status", "discovery_person", "related_asset"]
    ordering_fields = ["unregistered_code", "asset_name"]
    ordering = ["-discovery_date"]
    lookup_field = "unregistered_code"
    # 【P2-05 修复】移除未使用的 filter_mappings(DRF DjangoFilterBackend 已通过 filterset_fields 处理)

    def get_permissions(self) -> list[BasePermission]:
        if self.action in ["destroy", "batch_delete"]:
            permission_classes: list[type[BasePermission]] = [IsSystemAdmin]
        elif self.action == "approve":
            permission_classes = [IsDeptManagerOrAbove]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self, action: str | None = None) -> type:
        """
        根据动作返回对应的序列化器类

        Args:
            action: 动作名称,默认为当前动作

        Returns:
            Type: 序列化器类
        """
        action = action or self.action

        serializer_map = {
            "list": UnregisteredAssetListSerializer,
            "retrieve": UnregisteredAssetDetailSerializer,
            "create": UnregisteredAssetCreateSerializer,
            "update": UnregisteredAssetUpdateSerializer,
            "partial_update": UnregisteredAssetUpdateSerializer,
            "approve": UnregisteredAssetApproveSerializer,
        }
        return serializer_map.get(action, UnregisteredAssetListSerializer)

    def create(self, request: Request) -> Response:
        """
        创建未登记资产申请

        Request Body:
            - scenario_type: 场景类型(必填)
            - asset_name: 资产名称(必填)
            - discovery_date: 发现日期(必填)
            - discovery_location: 发现地点(必填)
            - discovery_person: 发现人工号(可选,默认为当前用户)
            - 其他可选字段...

        Returns:
            Response: 创建成功的数据
        """
        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 获取操作人工号:优先取请求中的 discovery_person,否则解析当前用户
        operator_jobcode = request.data.get("discovery_person") or resolve_operator(request.user)[0]  # type: ignore[arg-type]
        operator_name = resolve_operator(request.user)[1]  # type: ignore[arg-type]

        # 创建记录
        instance = UnregisteredAssetService.create(
            data=serializer.validated_data, operator_jobcode=operator_jobcode, operator_name=operator_name
        )

        # 返回详情
        detail_serializer = UnregisteredAssetDetailSerializer(instance, context={"request": request})

        return success_response(detail_serializer.data)

    def update(self, request: Request, unregistered_code: str | None = None) -> Response:
        """
        更新未登记资产信息

        Args:
            unregistered_code: 未登记资产编码

        Request Body:
            - 允许更新的字段(asset_name, asset_brand 等)

        Returns:
            Response: 更新后的数据
        """
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)  # type: ignore[arg-type]
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        operator_jobcode, operator_name = resolve_operator(request.user)  # type: ignore[arg-type]

        updated = UnregisteredAssetService.update(
            unregistered_code=unregistered_code,  # type: ignore[arg-type]
            update_data=serializer.validated_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        detail_serializer = UnregisteredAssetDetailSerializer(updated, context={"request": request})

        return success_response(detail_serializer.data)

    def destroy(self, request: Request, unregistered_code: str | None = None) -> Response:
        """
        删除未登记资产(软删除)

        Args:
            unregistered_code: 未登记资产编码

        Returns:
            Response: 删除成功响应
        """
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)  # type: ignore[arg-type]
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        operator_jobcode, operator_name = resolve_operator(request.user)  # type: ignore[arg-type]

        UnregisteredAssetService.delete(
            unregistered_code=unregistered_code,  # type: ignore[arg-type]
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return success_response(None)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, unregistered_code: str | None = None) -> Response:
        """
        审批处理未登记资产

        Args:
            unregistered_code: 未登记资产编码

        Request Body:
            - handle_type: 处理方式(必填)
            - approver: 审批人工号(必填)
            - approval_remark: 审批备注(可选)

        Returns:
            Response: 处理结果
        """
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)  # type: ignore[arg-type]
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        serializer = self.get_serializer_class("approve")(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 优先从请求数据中获取审批人工号,否则使用当前用户的工号
        operator_jobcode, operator_name = resolve_operator(request.user)  # type: ignore[arg-type]
        approver = serializer.validated_data.get("approver") or operator_jobcode

        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_code,  # type: ignore[arg-type]
            handle_type=serializer.validated_data["handle_type"],
            approver=approver,
            operator_name=operator_name,
            approval_remark=serializer.validated_data.get("approval_remark", ""),
        )

        return success_response(result)

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: Any) -> Response:
        """批量创建未登记资产"""
        items = request.data.get("items", [])
        if not items:
            return error_response(message="请提供要创建的数据列表", status_code=status.HTTP_400_BAD_REQUEST)
        # 【DR-1 收敛】字面量 100 → 统一常量(超限时 400 即时拒绝的契约保持不变)
        if len(items) > MAX_BATCH_SIZE:
            return error_response(
                message=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", status_code=status.HTTP_400_BAD_REQUEST
            )

        # 【D-1 收敛】手写循环下沉至 Service(batch_execute), 操作人信息仅解析一次
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = UnregisteredAssetService.batch_create_unregistered(
            data_list=items,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return BatchResponseHelper.create_response(
            result=result,
            serializer_class=UnregisteredAssetDetailSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
            request_items=items,
        )

    batch_delete_serializer = UnregisteredAssetBatchDeleteSerializer
    batch_delete_service = UnregisteredAssetService.batch_delete_unregistered
