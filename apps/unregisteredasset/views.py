"""
未登记资产视图集

该模块定义 DRF ViewSet，提供未登记资产的 RESTful API。

【AGENTS 规范 - 视图层】
- 职责分离：View 只处理 HTTP 请求/响应，业务逻辑委托 Service
- 权限控制：使用 DRF 权限类
- 序列化器选择：根据动作选择不同的序列化器
- 异常处理：捕获业务异常转换为 HTTP 响应

【API 端点】
- GET    /api/v1/unregistered-assets/          列表
- POST   /api/v1/unregistered-assets/          创建
- GET    /api/v1/unregistered-assets/{code}/   详情
- PUT    /api/v1/unregistered-assets/{code}/   更新
- DELETE /api/v1/unregistered-assets/{code}/   删除
- POST   /api/v1/unregistered-assets/{code}/approve/ 审批
"""

from typing import Type, List

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions import AppValidationError
from core.pagination import CustomPageNumberPagination
from core.mixins import LoggingMixin, ResponseWrapperMixin
from rest_framework.viewsets import ModelViewSet

from utils.response_utils import success_response

from .models import UnregisteredAsset
from .selectors import UnregisteredAssetSelector
from .services import UnregisteredAssetService
from .serializers import (
    UnregisteredAssetCreateSerializer,
    UnregisteredAssetUpdateSerializer,
    UnregisteredAssetApproveSerializer,
    UnregisteredAssetListSerializer,
    UnregisteredAssetDetailSerializer,
)


class UnregisteredAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """
    未登记资产视图集

    提供未登记资产的 CRUD 和审批操作。

    【权限控制】
    - 列表/详情：认证用户可访问
    - 创建：认证用户
    - 更新/删除：创建者或管理员（仅待审批状态）
    - 审批：管理员

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
    # 默认权限：需要认证
    permission_classes = [IsAuthenticated]

    # filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['scenario_type', 'approval_status', 'discovery_person_jobcode','related_asset_code']
    ordering_fields = ['unregistered_code', 'asset_name']
    ordering = ['-discovery_date']
    lookup_field = 'unregistered_code'
    # 查询参数映射
    filter_mappings = {
        'scenario_type': 'scenario_type',
        'approval_status': 'approval_status',
        'discovery_person': 'discovery_person_jobcode',
    }

    def get_serializer_class(self, action: str = None) -> Type:
        """
        根据动作返回对应的序列化器类

        Args:
            action: 动作名称，默认为当前动作

        Returns:
            Type: 序列化器类
        """
        action = action or self.action

        serializer_map = {
            'list': UnregisteredAssetListSerializer,
            'retrieve': UnregisteredAssetDetailSerializer,
            'create': UnregisteredAssetCreateSerializer,
            'update': UnregisteredAssetUpdateSerializer,
            'partial_update': UnregisteredAssetUpdateSerializer,
            'approve': UnregisteredAssetApproveSerializer,
        }
        return serializer_map.get(action, UnregisteredAssetListSerializer)

    # def list(self, request) -> Response:
    #     """
    #     获取未登记资产列表

    #     Query Parameters:
    #         - scenario_type: 场景类型筛选
    #         - approval_status: 审批状态筛选
    #         - discovery_person: 发现人筛选

    #     Returns:
    #         Response: 序列化后的列表数据
    #     """
    #     # 获取查询参数
    #     filters = {}
    #     for param, field in self.filter_mappings.items():
    #         value = request.query_params.get(param)
    #         if value:
    #             filters[field] = value

    #     # 查询数据
    #     queryset = UnregisteredAssetSelector.list_by_filters(**filters)

    #     # 序列化
    #     serializer = self.get_serializer_class()(
    #         queryset,
    #         many=True,
    #         context={'request': request}
    #     )

    #     return success_response(
    #         msg='success',
    #         data = serializer.data
    #     )

    # def retrieve(self, request, pk: str = None) -> Response:
    #     """
    #     获取未登记资产详情

    #     Args:
    #         pk: 未登记资产编码

    #     Returns:
    #         Response: 序列化后的详情数据

    #     Raises:
    #         NotFound: 记录不存在时抛出
    #     """
    #     instance = UnregisteredAssetSelector.get_by_code(pk)
    #     if not instance:
    #         raise NotFound(detail=f'未登记资产 {pk} 不存在')

    #     serializer = self.get_serializer_class()(
    #         instance,
    #         context={'request': request}
    #     )

    #     return Response({
    #         'code': 200,
    #         'msg': 'success',
    #         'data': serializer.data
    #     })

    def create(self, request) -> Response:
        """
        创建未登记资产申请

        Request Body:
            - scenario_type: 场景类型（必填）
            - asset_name: 资产名称（必填）
            - discovery_date: 发现日期（必填）
            - discovery_location: 发现地点（必填）
            - 其他可选字段...

        Returns:
            Response: 创建成功的数据
        """
        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # 获取当前用户
            operator_jobcode = request.user.employee_jobcode
            operator_name = getattr(request.user, 'employee_name', None)

            # 创建记录
            instance = UnregisteredAssetService.create(
                data=serializer.validated_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )

            # 返回详情
            detail_serializer = UnregisteredAssetDetailSerializer(
                instance,
                context={'request': request}
            )

            return success_response(detail_serializer.data, status=status.HTTP_201_CREATED)

        except AppValidationError as e:
            raise ValidationError(detail=e.detail)

    def update(self, request, pk: str = None) -> Response:
        """
        更新未登记资产信息

        Args:
            pk: 未登记资产编码

        Request Body:
            - 允许更新的字段（asset_name, asset_brand 等）

        Returns:
            Response: 更新后的数据
        """
        instance = UnregisteredAssetSelector.get_by_code(pk)
        if not instance:
            raise NotFound(detail=f'未登记资产 {pk} 不存在')

        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            operator_jobcode = request.user.employee_jobcode
            operator_name = getattr(request.user, 'employee_name', None)

            updated = UnregisteredAssetService.update(
                unregistered_code=pk,
                update_data=serializer.validated_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )

            detail_serializer = UnregisteredAssetDetailSerializer(
                updated,
                context={'request': request}
            )

            return success_response(detail_serializer.data)

        except AppValidationError as e:
            raise ValidationError(detail=e.detail)

    def destroy(self, request, pk: str = None) -> Response:
        """
        删除未登记资产（软删除）

        Args:
            pk: 未登记资产编码

        Returns:
            Response: 删除成功响应
        """
        instance = UnregisteredAssetSelector.get_by_code(pk)
        if not instance:
            raise NotFound(detail=f'未登记资产 {pk} 不存在')

        try:
            operator_jobcode = request.user.employee_jobcode
            operator_name = getattr(request.user, 'employee_name', None)

            UnregisteredAssetService.delete(
                unregistered_code=pk,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )

            return success_response( None )

        except AppValidationError as e:
            raise ValidationError(detail=e.detail)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk: str = None) -> Response:
        """
        审批处理未登记资产

        Args:
            pk: 未登记资产编码

        Request Body:
            - handle_type: 处理方式（必填）
            - approval_remark: 审批备注（可选）

        Returns:
            Response: 处理结果
        """
        instance = UnregisteredAssetSelector.get_by_code(pk)
        if not instance:
            raise NotFound(detail=f'未登记资产 {pk} 不存在')

        serializer = self.get_serializer_class('approve')(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            approver_jobcode = request.user.employee_jobcode
            operator_name = getattr(request.user, 'employee_name', None)

            result = UnregisteredAssetService.approve_and_handle(
                unregistered_code=pk,
                handle_type=serializer.validated_data['handle_type'],
                approver_jobcode=approver_jobcode,
                operator_name=operator_name,
                approval_remark=serializer.validated_data.get('approval_remark', '')
            )

            return success_response(
                data = result,
                msg='审批处理成功',
            )

        except AppValidationError as e:
            raise ValidationError(detail=e.detail)
