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

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.selectors import UnregisteredAssetSelector
from apps.unregisteredasset.serializers import (
    UnregisteredAssetApproveSerializer,
    UnregisteredAssetCreateSerializer,
    UnregisteredAssetDetailSerializer,
    UnregisteredAssetListSerializer,
    UnregisteredAssetUpdateSerializer,
)
from apps.unregisteredasset.services import UnregisteredAssetService
from core.batch_mixins import BatchResponseHelper
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError
from core.mixins import LoggingMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsDeptManagerOrAbove, IsSystemAdmin
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator


class UnregisteredAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
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

    def get_permissions(self):
        if self.action in ["destroy", "batch_delete"]:
            permission_classes = [IsSystemAdmin]
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

    def create(self, request) -> Response:
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
        operator_jobcode = request.data.get("discovery_person") or resolve_operator(request.user)[0]
        operator_name = resolve_operator(request.user)[1]

        # 创建记录
        instance = UnregisteredAssetService.create(
            data=serializer.validated_data, operator_jobcode=operator_jobcode, operator_name=operator_name
        )

        # 返回详情
        detail_serializer = UnregisteredAssetDetailSerializer(instance, context={"request": request})

        return success_response(detail_serializer.data)

    def update(self, request, unregistered_code: str | None = None) -> Response:
        """
        更新未登记资产信息

        Args:
            unregistered_code: 未登记资产编码

        Request Body:
            - 允许更新的字段(asset_name, asset_brand 等)

        Returns:
            Response: 更新后的数据
        """
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        operator_jobcode, operator_name = resolve_operator(request.user)

        updated = UnregisteredAssetService.update(
            unregistered_code=unregistered_code,
            update_data=serializer.validated_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        detail_serializer = UnregisteredAssetDetailSerializer(updated, context={"request": request})

        return success_response(detail_serializer.data)

    def destroy(self, request, unregistered_code: str | None = None) -> Response:
        """
        删除未登记资产(软删除)

        Args:
            unregistered_code: 未登记资产编码

        Returns:
            Response: 删除成功响应
        """
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        operator_jobcode, operator_name = resolve_operator(request.user)

        UnregisteredAssetService.delete(
            unregistered_code=unregistered_code, operator_jobcode=operator_jobcode, operator_name=operator_name
        )

        return success_response(None)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, unregistered_code: str | None = None) -> Response:
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
        instance = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not instance:
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        serializer = self.get_serializer_class("approve")(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 优先从请求数据中获取审批人工号,否则使用当前用户的工号
        operator_jobcode, operator_name = resolve_operator(request.user)
        approver = serializer.validated_data.get("approver") or operator_jobcode

        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_code,
            handle_type=serializer.validated_data["handle_type"],
            approver=approver,
            operator_name=operator_name,
            approval_remark=serializer.validated_data.get("approval_remark", ""),
        )

        return success_response(result)

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request) -> Response:
        """批量创建未登记资产"""
        items = request.data.get("items", [])
        if not items:
            return error_response(message="请提供要创建的数据列表", status_code=status.HTTP_400_BAD_REQUEST)
        # 【DR-1 收敛】字面量 100 → 统一常量(超限时 400 即时拒绝的契约保持不变)
        if len(items) > MAX_BATCH_SIZE:
            return error_response(
                message=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", status_code=status.HTTP_400_BAD_REQUEST
            )

        # 【DR-1 收敛】异常分层: AppValidationError 透传注册错误码,
        # 消除原 CREATE_FAILED 单码制与 str(e) 的内部异常文本暴露
        success_items = []
        fail_items = []
        for idx, item in enumerate(items):
            try:
                serializer = UnregisteredAssetCreateSerializer(data=item)
                serializer.is_valid(raise_exception=True)
                instance = UnregisteredAssetService.create(
                    data=serializer.validated_data,
                    operator_jobcode=resolve_operator(request.user)[0],
                    operator_name=resolve_operator(request.user)[1],
                )
                success_items.append(UnregisteredAssetDetailSerializer(instance).data)
            except AppValidationError as e:
                fail_items.append(
                    {
                        "index": idx,
                        "error_code": e.error_code or "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                        "input_data": item,
                    }
                )
            except drf_exceptions.ValidationError as e:
                # 条目级 serializer 校验失败(DRF ValidationError)
                fail_items.append(
                    {
                        "index": idx,
                        "error_code": "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                        "input_data": item,
                    }
                )
            except Exception:
                fail_items.append(
                    {
                        "index": idx,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误,请稍后重试",
                        "input_data": item,
                    }
                )

        return success_response(
            data={
                "total": len(items),
                "success_count": len(success_items),
                "fail_count": len(fail_items),
                "success_items": success_items,
                "fail_items": fail_items,
            },
            message=f"批量创建完成,成功 {len(success_items)} 条,失败 {len(fail_items)} 条",
        )

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request) -> Response:
        """
        【新增】批量删除未登记资产(软删除)

        接收前端提交的未登记资产编码列表,逐条删除。
        仅允许删除待审批状态的记录。

        请求格式:
            POST /api/unregisteredassets/unregistered-assets/batch-delete/
            {
                "ids": ["UNR-20260601-ABC123", "UNR-20260602-DEF456"]
            }

        响应格式:
            {
                "code": 200,
                "message": "批量删除成功",
                "data": {
                    "total": 2,
                    "success_count": 1,
                    "fail_count": 1,
                    "success_ids": ["UNR-20260601-ABC123"],
                    "fail_items": [{"id": "UNR-20260602-DEF456", "error_code": "...", "error_message": "..."}]
                }
            }
        """
        ids = request.data.get("ids", [])
        if not ids:
            return error_response(message="请提供要删除的 ID 列表", status_code=status.HTTP_400_BAD_REQUEST)

        if len(ids) > 100:
            return error_response(message="单次批量删除不能超过 100 条", status_code=status.HTTP_400_BAD_REQUEST)

        success_ids = []
        fail_items = []

        for unregistered_code in ids:
            try:
                instance = UnregisteredAssetSelector.get_by_code(unregistered_code)
                if not instance:
                    fail_items.append(
                        {
                            "id": unregistered_code,
                            "error_code": "NOT_FOUND",
                            "error_message": f"未登记资产 {unregistered_code} 不存在",
                        }
                    )
                    continue

                # 仅允许删除待审批状态的记录
                if instance.approval_status != "pending":
                    fail_items.append(
                        {
                            "id": unregistered_code,
                            "error_code": "STATUS_NOT_ALLOWED",
                            "error_message": f"当前审批状态为 {instance.approval_status},不允许删除",
                        }
                    )
                    continue

                UnregisteredAssetService.delete(
                    unregistered_code=unregistered_code,
                    operator_jobcode=resolve_operator(request.user)[0],
                    operator_name=resolve_operator(request.user)[1],
                )
                success_ids.append(unregistered_code)

            except AppValidationError as e:
                fail_items.append(
                    {"id": unregistered_code, "error_code": "VALIDATION_ERROR", "error_message": str(e.detail)}
                )
            except Exception:
                fail_items.append(
                    {
                        "id": unregistered_code,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误,请稍后重试",
                    }
                )

        # 【DR-1 收敛】响应组装复用 BatchResponseHelper
        return BatchResponseHelper.delete_response(
            {
                "total": len(ids),
                "success_count": len(success_ids),
                "fail_count": len(fail_items),
                "success_ids": success_ids,
                "fail_items": fail_items,
            },
            message=f"批量删除完成,成功 {len(success_ids)} 条,失败 {len(fail_items)} 条",
        )
