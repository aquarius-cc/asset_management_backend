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

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
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
from core.permissions import (
    IsAssetAdminOrAbove,
    IsDeptManagerOrAbove,
    IsSystemAdmin,
    IsSystemAdminOrAssetAdmin,
    is_system_admin,
    resolve_viewset_permissions,
)
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator


# 4.5 矩阵「角色×动作」权限映射(经 resolve_viewset_permissions 统一分发, DR-1);
# 行级隔离由 get_queryset → Selector.get_queryset_for_user 兜底(B12)。
_ACTION_PERMISSION_OVERRIDES: dict[str, type[BasePermission]] = {
    "list": IsAssetAdminOrAbove,
    "retrieve": IsAssetAdminOrAbove,
    "create": IsSystemAdminOrAssetAdmin,
    "batch_create": IsSystemAdminOrAssetAdmin,
    "update": IsSystemAdminOrAssetAdmin,
    "partial_update": IsSystemAdminOrAssetAdmin,
    "destroy": IsSystemAdminOrAssetAdmin,
    "batch_delete": IsSystemAdminOrAssetAdmin,
    "approve": IsDeptManagerOrAbove,
}


class UnregisteredAssetViewSet(  # type: ignore[misc]
    BatchDeleteViewMixin, LoggingMixin, ResponseWrapperMixin, ModelViewSet[UnregisteredAsset]
):
    """
    未登记资产视图集

    提供未登记资产的 CRUD 和审批操作。

    【权限控制】(4.5 矩阵 backend-business-rules.md:187-193, 经 _ACTION_PERMISSION_OVERRIDES 分发)
    - 列表/详情:资产管理员及以上(asset_admin/dept_manager/system_admin; regular/auditor 403)
    - 创建/更新/删除/批量删除:系统管理员或资产管理员(dept_manager 403 只读)
    - 审批:部门经理及以上(system_admin/dept_manager)
    - 行级隔离:Selector.get_queryset_for_user(部门+下级+本人例外; 越权 404)
    - 创建代录 discovery_person:默认=本人,仅 system_admin 可代录(否则 403)
    - 审批 approver:服务端强制=当前审批人(传入值被忽略)

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
    # 角色门禁按 4.5 矩阵经 get_permissions 分发;此处仅保留认证兜底默认值
    permission_classes = [IsAuthenticated]

    # filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["scenario_type", "approval_status", "discovery_person", "related_asset"]
    ordering_fields = ["unregistered_code", "asset_name"]
    ordering = ["-discovery_date"]
    lookup_field = "unregistered_code"
    # 【P2-05 修复】移除未使用的 filter_mappings(DRF DjangoFilterBackend 已通过 filterset_fields 处理)

    def get_permissions(self) -> list[BasePermission]:
        """按 4.5 矩阵「角色×动作」分发角色门禁(行级隔离由 get_queryset 兜底)"""
        return resolve_viewset_permissions(
            self.action,
            admin_actions=frozenset(),
            admin_permission=IsSystemAdmin,
            action_overrides=_ACTION_PERMISSION_OVERRIDES,
        )

    def get_queryset(self) -> QuerySet[UnregisteredAsset]:
        """行级隔离(4.5 规则1-3):list/retrieve 及 get_object 统一走 Selector(B12)"""
        return UnregisteredAssetSelector.get_queryset_for_user(self.request.user)

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
            - discovery_person: 发现人工号(可选,默认当前用户;仅 system_admin 可代录)
            - 其他可选字段...

        Returns:
            Response: 创建成功的数据
        """
        # 语义5: operator 恒为当前操作人,与 discovery_person 解耦
        operator_jobcode, operator_name = resolve_operator(request.user)  # type: ignore[arg-type]

        # F-P1-6: discovery_person 代录白名单(语义2: 仅 system_admin 可传非本人工号;
        # discovery_person 不在 CreateSerializer fields,白名单只能读原始 request.data)
        discovery_target = str(request.data.get("discovery_person") or "").strip()  # type: ignore[union-attr]
        if discovery_target and discovery_target != operator_jobcode and not is_system_admin(request.user):
            raise PermissionDenied(detail="仅系统管理员可代录发现人")
        discovery_jobcode = discovery_target or operator_jobcode

        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 创建记录
        instance = UnregisteredAssetService.create(
            data=serializer.validated_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            discovery_person_jobcode=discovery_jobcode,
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
        instance = UnregisteredAssetSelector.get_by_code_for_user(request.user, unregistered_code)  # type: ignore[arg-type]
        if not instance:
            # 4.5 语义4: 行级越权与不存在同构 404,不泄露存在性
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
        instance = UnregisteredAssetSelector.get_by_code_for_user(request.user, unregistered_code)  # type: ignore[arg-type]
        if not instance:
            # 4.5 语义4: 行级越权与不存在同构 404,不泄露存在性
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
        instance = UnregisteredAssetSelector.get_by_code_for_user(request.user, unregistered_code)  # type: ignore[arg-type]
        if not instance:
            # 4.5 语义4: 行级越权(dept_manager 跨部门)与不存在同构 404
            raise NotFound(detail=f"未登记资产 {unregistered_code} 不存在")

        serializer = self.get_serializer_class("approve")(data=request.data)
        serializer.is_valid(raise_exception=True)

        # F-P1-5: 语义3 — approver 强制=当前审批人,无条件覆盖客户端传入值(防代签)
        operator_jobcode, operator_name = resolve_operator(request.user)  # type: ignore[arg-type]
        approver = operator_jobcode

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
    # B14 行级: 注入 request.user, Service 逐条按行级隔离过滤(越权→NOT_FOUND)
    batch_delete_passes_user = True
