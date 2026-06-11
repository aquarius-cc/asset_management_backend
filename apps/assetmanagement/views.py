from core.exceptions import AppValidationError
"""
资产管理视图模块（优化版）

优化点：
- 移除所有显式的 is_deleted 过滤，BaseModel.objects 已自动处理软删除
- 使用 core.constants 中统一的状态选择常量，替代模型内部 CHOICES
- 在 Service 层抛出 core.exceptions.ValidationError 等自定义异常，
  视图层精确捕获并返回对应状态码
- 充分利用 ResponseWrapperMixin 提供的默认 list/create/update/destroy，
  仅在需要自定义业务逻辑时重写
- 统一使用 QuerySet[Model] 类型标注，消除 Any
"""

import logging
from datetime import datetime
from typing import Type

from django.db.models import Q, QuerySet
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.openapi import OpenApiParameter
from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import Serializer

from utils.response_utils import success_response, error_response
from core.constants import (
    ASSET_STATUS_CHOICES,
    ASSET_APPEARANCE_CHOICES,
    OUTASSET_TYPE_CHOICES,
    STORAGE_TYPE_CHOICES,
    CONTRACT_TYPE_CHOICES,
    CONTRACT_SETTLEMENT_CHOICES,
    APPROVAL_STATUS_CHOICES,
    EMPLOYEE_STATUS_CHOICES,
    HARDDISK_STATUS_CHOICES,
)
from core.exceptions import ValidationError, NotFoundError, BusinessLogicError
from core.pagination import CustomPageNumberPagination
from core.mixins import ResponseWrapperMixin, LoggingMixin
from core.exceptions import ValidationError
from .services import DamagedAssetService

from apps.assetmanagement.models import (
    Storage,
    AssetType,
    Contract,
    Asset,
    OutAsset,
    RecycleAsset,
    DamagedAsset,
    WasteAsset,
    HardDiskSN,
)
from apps.assetmanagement.serializers import (
    StorageSerializer,
    AssetTypeSerializer,
    ContractSerializer,
    ContractDetailSerializer,
    AssetSerializer,
    AssetDetailSerializer,
    AssetCreateSerializer,
    AssetBatchCreateSerializer,
    AssetBatchDeleteSerializer,
    OutAssetSerializer,
    OutAssetDetailSerializer,
    OutAssetBatchCreateSerializer,
    OutAssetBatchDeleteSerializer,
    RecycleAssetSerializer,
    RecycleAssetBatchCreateSerializer,
    RecycleAssetBatchDeleteSerializer,
    DamagedAssetSerializer,
    WasteAssetSerializer,
    HardDiskSNSerializer,
    HardDiskSNBatchSerializer,  # 【AGENTS 规范】批量保存序列化器
    CombinedAssetSerializer,
    DashboardStatSerializer,
    ErrorResponseSerializer,
)
from apps.assetmanagement.services import (
    AssetService,
    OutAssetService,
    RecycleAssetService,
    ContractService,
    StorageService,     # 【AGENTS 规范 - P3-42】仓库创建服务
    AssetTypeService,   # 【AGENTS 规范 - P3-43】资产类型创建服务
    HardDiskSNService,  # 【AGENTS 规范】硬盘序列号批量保存服务
)
from apps.assetmanagement.selectors import (
    AssetSelector,
    ContractSelector,
    StorageSelector,
    OutAssetSelector,
    RecycleAssetSelector,
    DamagedAssetSelector,
    WasteAssetSelector,
    HardDiskSNSelector,
    DashboardSelector,  # 【P1-08】仪表盘统计查询选择器
)

# ==================== 状态名称映射（来自 core.constants） ====================
ASSET_STATUS_MAP = dict(ASSET_STATUS_CHOICES)
STORAGE_TYPE_MAP = dict(STORAGE_TYPE_CHOICES)
OUTASSET_TYPE_MAP = dict(OUTASSET_TYPE_CHOICES)
CONTRACT_TYPE_MAP = dict(CONTRACT_TYPE_CHOICES)
CONTRACT_SETTLEMENT_MAP = dict(CONTRACT_SETTLEMENT_CHOICES)

# ==================== 视图集 ====================

class StorageViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    queryset = Storage.objects.all()          # 自动过滤 is_deleted=False
    serializer_class = StorageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['storage_type']
    ordering_fields = ['storage_code', 'storage_name']
    ordering = ['storage_code']
    lookup_field = 'storage_code'

    def get_queryset(self) -> QuerySet[Storage]:
        keyword = self.request.GET.get('keyword', '').strip()
        if keyword:
            return Storage.objects.filter(
                Q(storage_code__icontains=keyword) |
                Q(storage_name__icontains=keyword) |
                Q(storage_address__icontains=keyword)
            )
        return super().get_queryset()

    def get_object(self) -> Storage:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except Storage.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except Storage.DoesNotExist:
            raise Http404(f"Storage with id or storage_code '{lookup_value}' not found.")

        self.check_object_permissions(self.request, obj)
        return obj

    # 【AGENTS 规范 - P3-42】重写 create，调用 StorageService.create_storage()
    # 实现仓库编码和名称的唯一性校验
    def create(self, request, *args, **kwargs):
        """
        【AGENTS 规范 - P3-42】创建仓库

        【修复内容】重写 create 方法，调用 StorageService.create_storage()，
        实现仓库编码和名称的唯一性校验，替代 Mixin 默认的 ORM create。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            storage = StorageService.create_storage(serializer.validated_data)
            return success_response(data=StorageSerializer(storage).data,
                                    message='创建成功', status_code=status.HTTP_201_CREATED)
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request) -> Response:
        queryset = self.queryset
        total = queryset.count()
        type_stats = {
            code: {'name': name, 'count': queryset.filter(storage_type=code).count()}
            for code, name in STORAGE_TYPE_CHOICES
        }
        return success_response(data={'total_storages': total, 'by_type': type_stats})


class AssetTypeViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    queryset = AssetType.objects.all()
    serializer_class = AssetTypeSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'asset_type_code'

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['asset_type_category']
    search_fields = ['asset_type_secondary', 'asset_type_code']
    ordering_fields = ['asset_type_code', 'asset_type_secondary']
    ordering = ['asset_type_code']

    def get_object(self) -> AssetType:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except AssetType.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except AssetType.DoesNotExist:
            raise Http404(f"AssetType with id or asset_type_code '{lookup_value}' not found.")

        self.check_object_permissions(self.request, obj)
        return obj

    # 【AGENTS 规范 - P3-43】重写 create，调用 AssetTypeService.create_asset_type()
    # 实现资产类型编码的唯一性校验
    def create(self, request, *args, **kwargs):
        """
        【AGENTS 规范 - P3-43】创建资产类型

        【修复内容】重写 create 方法，调用 AssetTypeService.create_asset_type()，
        实现资产类型编码的唯一性校验，替代 Mixin 默认的 ORM create。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        print("create asset type:", serializer.validated_data)
        try:
            asset_type = AssetTypeService.create_asset_type(serializer.validated_data)
            return success_response(data=AssetTypeSerializer(asset_type).data,
                                    message='创建成功', status_code=status.HTTP_201_CREATED)
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)


class ContractViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    queryset = Contract.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'contract_code'
    lookup_value_regex = '.*?'
    pagination_class = CustomPageNumberPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['contract_type', 'contract_settlment_status']
    ordering_fields = ['contract_code', 'contract_signing_date', 'contract_price']
    ordering = ['-contract_signing_date']

    def get_serializer_class(self) -> Type:
        if self.action in ['retrieve', 'list']:
            return ContractDetailSerializer
        return ContractSerializer

    def get_object(self) -> Contract:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except Contract.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except Contract.DoesNotExist:
            raise Http404(f"Contract with id or contract_code '{lookup_value}' not found.")

        self.check_object_permissions(self.request, obj)
        return obj

    # 使用 Mixin 提供的默认 list 即可，无需重写
    # 如果有自定义 list 逻辑，可在此添加，但必须保证响应格式

    # 重写 destroy 以处理关联资产（业务逻辑已在 Service 中）
    def destroy(self, request, *args, **kwargs):
        try:
            contract = self.get_object()
            ContractService.delete_contract(contract.contract_code)
            return success_response(message='删除成功')
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except NotFoundError as e:
            return error_response(message=str(e), status_code=404)
        except Exception as e:
            logging.exception('合同删除失败')
            return error_response(message='删除失败，请稍后重试', status_code=500)

    @extend_schema(
        parameters=[OpenApiParameter(name='name', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)],
        responses={200: ContractDetailSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='getcontractByname/(?P<name>[^/.]+)')
    def getcontractByname(self, request, name=None) -> Response:
        """
        【AGENTS 规范 - P1-06】按合同名称模糊查询

        【修复内容】使用 ContractSelector.search_contracts() 替代直接 ORM 查询，
        自动过滤 is_deleted=False。
        """
        name = name.strip() if name else ''
        if not name:
            return error_response(message='合同名称参数不能为空', status_code=400)

        # 【AGENTS 规范】通过 Selector 查询，keyword 匹配合同编码、名称、供应商
        contracts = ContractSelector.search_contracts(keyword=name)
        serializer = self.get_serializer(contracts, many=True)
        return success_response(data={
            'count': contracts.count(),
            'results': serializer.data
        }, message='查询成功')

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request) -> Response:
        stats = ContractService.get_contract_statistics()
        return success_response(data=stats, message='查询成功')

    # 【AGENTS 规范 - P3-41】更新合同结算状态
    @action(detail=True, methods=['post'], url_path='update_settlement_status')
    def update_settlement_status(self, request, pk=None) -> Response:
        """
        【AGENTS 规范 - P3-41】更新合同结算状态

        【修复内容】新增 action，调用 ContractService.update_settlement_status()，
        支持更新合同的结算状态（pending/settled），包含状态有效性校验。
        """
        contract_code = self.kwargs.get('contract_code')
        new_status = request.data.get('status')
        if not new_status:
            return error_response(message='请提供结算状态（pending/settled）', status_code=400)
        try:
            contract = ContractService.update_settlement_status(contract_code, new_status)
            serializer = ContractDetailSerializer(instance=contract)
            return success_response(data={'contract': serializer.data}, message='结算状态更新成功')
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception as e:
            logging.exception('合同结算状态更新失败')
            return error_response(message='更新失败，请稍后重试', status_code=500)

    @action(detail=True, methods=['post'], url_path='payment_record')
    def payment_record(self, request, pk=None) -> Response:
        contract_code = self.kwargs.get('contract_code')
        amount = request.data.get('amount')
        description = request.data.get('description', '')
        if not amount:
            return error_response(message='请提供付款金额', status_code=400)
        try:
            amount = float(amount)
            contract = ContractService.add_payment_record(contract_code, amount, description)
            serializer = ContractDetailSerializer(instance=contract)
            return success_response(data={'contract': serializer.data}, message='付款记录添加成功')
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except ValueError:
            return error_response(message='付款金额格式错误', status_code=400)

    @extend_schema(
        summary='全局模糊搜索合同',
        parameters=[
            OpenApiParameter(name='keyword', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
            OpenApiParameter(name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='page_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: ContractDetailSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='search')
    def global_search(self, request) -> Response:
        """
        【AGENTS 规范 - P1-07】全局模糊搜索合同

        【修复内容】使用 ContractSelector.search_contracts() 替代手写 ORM 查询，
        消除重复代码，自动过滤 is_deleted=False。
        """
        keyword = request.query_params.get('keyword', '').strip()
        if not keyword:
            return error_response(message='请提供搜索关键词', status_code=400)

        # 【AGENTS 规范】通过 Selector 查询，复用已有的 search_contracts 方法
        contracts = ContractSelector.search_contracts(keyword=keyword)
        page = self.paginate_queryset(contracts)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(contracts, many=True)
        return success_response(data={
            'count': contracts.count(),
            'results': serializer.data
        }, message='查询成功')


class AssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    # 【AGENTS 规范 - 性能优化】使用 select_related 减少外键查询次数
    # 【AGENTS 规范 - 性能优化】使用 prefetch_related 预取关联的硬盘序列号，避免 N+1 查询
    queryset = Asset.objects.select_related(
        'asset_type_code', 'asset_contract_code', 'asset_storage_code'
    ).prefetch_related(
        'harddisk_sns'  # 预取关联的硬盘序列号列表
    ).all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['asset_current_status', 'asset_type_code', 'asset_storage_code']
    ordering_fields = ['asset_code', 'asset_entry_date', 'asset_purchase_price', 'asset_name']
    ordering = ['-asset_entry_date']
    lookup_field = 'asset_code'

    def get_serializer_class(self) -> Type:
        if self.action == 'create':
            return AssetCreateSerializer
        elif self.action in ['retrieve', 'list']:
            return AssetDetailSerializer
        return AssetSerializer

    def get_queryset(self) -> QuerySet[Asset]:
        # 【AGENTS 规范 - 性能优化】列表页使用 for_list() 精简字段，排除大字段
        if self.action == 'list':
            qs = Asset.objects.for_list().all()
        else:
            # 详情页及其他：完整字段 + 硬盘序列号预加载
            qs = Asset.objects.with_all_relations().with_harddisk_sns().all()

        keyword = self.request.GET.get('keyword', '').strip()
        if keyword:
            qs = qs.filter(
                Q(asset_code__icontains=keyword) |
                Q(asset_name__icontains=keyword) |
                Q(asset_brand__icontains=keyword) |
                Q(asset_specification__icontains=keyword)
            )
        # 过滤参数由 DjangoFilterBackend 自动处理
        return qs

    def get_object(self) -> Asset:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except Asset.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except Asset.DoesNotExist:
            raise Http404(f"Asset with id or asset_code '{lookup_value}' not found.")

        self.check_object_permissions(self.request, obj)
        return obj

    # 【AGENTS 规范】自定义 create，调用 AssetService 批量创建资产
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 显式调用 Service 层，返回 List[Asset]
        assets = AssetService.create_asset(
            serializer.validated_data,
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        # 使用详情序列化器返回列表（many=True）
        response_serializer = AssetDetailSerializer(assets, many=True)

        count = len(assets)
        message = f'创建成功，共创建 {count} 条资产记录' if count > 1 else '创建成功'

        return success_response(
            data=response_serializer.data,
            message=message,
            status_code=status.HTTP_201_CREATED
        )

    # 【AGENTS 规范 - P3-39】重写 update/partial_update，调用 AssetService.update_asset()
    # 实现字段白名单校验 + 操作日志记录
    def update(self, request, *args, **kwargs):
        """
        【AGENTS 规范 - P3-39】更新资产

        【修复内容】重写 update 方法，调用 AssetService.update_asset()，
        实现字段白名单校验和操作日志记录，替代 Mixin 默认的 ORM save。
        """
        asset_code = self.kwargs.get('asset_code')
        try:
            asset = AssetService.update_asset(
                asset_code=asset_code,
                update_data=request.data,
                operator_jobcode=request.user.auth_id,
                operator_name=request.user.auth_username,
            )
            serializer = AssetDetailSerializer(asset)
            return success_response(data=serializer.data, message='更新成功')
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except NotFoundError as e:
            return error_response(message=str(e), status_code=404)
        except Exception as e:
            logging.exception('资产更新失败')
            return error_response(message='更新失败，请稍后重试', status_code=500)

    def partial_update(self, request, *args, **kwargs):
        """【AGENTS 规范 - P3-39】部分更新资产，复用 update 逻辑"""
        return self.update(request, *args, **kwargs)

    # 【AGENTS 规范 - P3-38】重写 destroy，调用 AssetService.delete_asset()
    # 实现软删除 + 操作日志记录
    def destroy(self, request, *args, **kwargs):
        """
        【AGENTS 规范 - P3-38】删除资产（软删除）

        【修复内容】重写 destroy 方法，调用 AssetService.delete_asset()，
        实现软删除和操作日志记录，替代 Mixin 默认的物理删除。
        """
        asset_code = self.kwargs.get('asset_code')
        try:
            AssetService.delete_asset(
                asset_code=asset_code,
                operator_jobcode=request.user.auth_id,
                operator_name=request.user.auth_username,
            )
            return success_response(message='删除成功')
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except NotFoundError as e:
            return error_response(message=str(e), status_code=404)
        except Exception as e:
            logging.exception('资产删除失败')
            return error_response(message='删除失败，请稍后重试', status_code=500)

    @extend_schema(
        parameters=[OpenApiParameter(name='name', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)],
        responses={200: AssetDetailSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='getassetbyname/(?P<name>[^/.]+)')
    def get_asset_by_name(self, request, name=None) -> Response:
        """
        【AGENTS 规范 - P1-05】按资产名称模糊查询

        【修复内容】使用 AssetSelector.search_assets() 替代直接 ORM 查询，
        自动过滤 is_deleted=False + 预加载关联信息。
        """
        if not name:
            return success_response(data={'count': 0, 'results': []})

        # 【AGENTS 规范】通过 Selector 查询，keyword 参数会匹配 asset_name
        assets = AssetSelector.search_assets(keyword=name)
        serializer = AssetDetailSerializer(assets, many=True)
        return success_response(data={
            'count': assets.count(),
            'results': serializer.data
        })

    @action(detail=False, methods=['get'], url_path='getassetbyrecordcode/(?P<asset_recordcode>[^/.]+)')
    def get_asset_by_recordcode(self, request, asset_recordcode=None) -> Response:
        code = request.query_params.get('asset_recordcode')
        if not code:
            return error_response(message='缺少 asset_recordcode 参数', status_code=400)

        assets = self.queryset.filter(asset_recordcode=code)
        serializer = self.get_serializer(assets, many=True)
        return success_response(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='search')
    def search_assets(self, request) -> Response:
        """
        【AGENTS 规范 - P3-01】全局搜索资产

        【修复内容】使用 AssetSelector.search_assets() 替代直接 return self.list()，
        传递 keyword/status/asset_type_code/storage_code/contract_code 参数，
        自动过滤 is_deleted=False + 预加载关联信息。
        """
        keyword = request.query_params.get('keyword', '').strip() or None
        status = request.query_params.get('status', '').strip() or None
        asset_type_code = request.query_params.get('asset_type_code', '').strip() or None
        storage_code = request.query_params.get('storage_code', '').strip() or None
        contract_code = request.query_params.get('contract_code', '').strip() or None

        # 【AGENTS 规范】通过 Selector 查询，支持多条件组合搜索
        assets = AssetSelector.search_assets(
            keyword=keyword,
            status=status,
            asset_type_code=asset_type_code,
            storage_code=storage_code,
            contract_code=contract_code,
        )

        page = self.paginate_queryset(assets)
        if page is not None:
            serializer = AssetDetailSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = AssetDetailSerializer(assets, many=True)
        return success_response(data={
            'count': assets.count(),
            'results': serializer.data
        }, message='查询成功')

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request) -> Response:
        stats = AssetService.get_asset_statistics()
        return success_response(data=stats, message='查询成功')

    @action(detail=False, methods=['get'], url_path='search_available',permission_classes=[permissions.IsAuthenticated])
    def search_available(self, request) -> Response:
        # available = Asset.objects.filter(Q(asset_current_status='in_store') | Q(asset_current_status='recycled_pending'))
        available = AssetSelector.get_available_assets()
        serializer = self.get_serializer(available, many=True)
        return success_response(data={
            'count': available.count(),
            'results': serializer.data
        })

    @action(detail=True, methods=['post'], url_path='change_status')
    def change_status(self, request, pk=None) -> Response:
        asset_code = self.kwargs.get('asset_code')
        new_status = request.data.get('status')
        description = request.data.get('description', '')
        try:
            asset = AssetService.change_asset_status(asset_code, new_status, description)
            serializer = AssetDetailSerializer(asset)
            return success_response(data={'asset': serializer.data},
                                    message=f'状态已更改为: {ASSET_STATUS_MAP.get(new_status, new_status)}')
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except NotFoundError as e:
            return error_response(message=str(e), status_code=404)

    @extend_schema(
        description="更新资产申请人和资产保管人信息",
        parameters=[OpenApiParameter(name="change_outasset_employee", description="更新资产申请人和资产保管人信息", required=False, type=str)],
    )
    @action(detail=True,methods=['POST'],url_path='change_outasset_employee')
    def change_outasset_employee(self, request, pk=None) -> Response:
        asset_code = self.kwargs.get('asset_code')
        applicant_jobcode = request.data.get('applicant_jobcode')
        manager_jobcode = request.data.get('manager_jobcode')

        try:
            asset = AssetService.change_outasset_employee(asset_code, applicant_jobcode, manager_jobcode)
            serializer = AssetDetailSerializer(asset)
            return success_response(data={'asset': serializer.data},
                                    message=f'资产 {asset_code} 已更新资产申请人 {applicant_jobcode} 和资产保管人 {manager_jobcode}')
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except NotFoundError as e:
            return error_response(message=str(e), status_code=404)

    @action(detail=False, methods=['get'], url_path='combined_details')
    def combined_details(self, request) -> Response:
        asset_code = request.query_params.get('asset_code')
        if not asset_code:
            return error_response(message='请提供资产编码', status_code=400)
        data = CombinedAssetSerializer.get_asset_details_data(asset_code)
        return success_response(data=data, message='查询成功')

    @action(detail=False, methods=['get'], url_path='contract_by_asset/(?P<asset_code>[^/.]+)')
    def contract_by_asset(self, request, asset_code=None) -> Response:
        """
        【AGENTS 规范】通过资产编码查询关联合同信息

        从资产出发，查询该资产关联的采购合同信息。
        仅返回合同数据，不返回资产数据。

        URL: GET /api/assets/contract_by_asset/{asset_code}/

        Args:
            asset_code: 资产编码（路径参数）

        Returns:
            成功: 合同详细信息（ContractSerializer 格式）
            失败: 404 - 资产不存在或未关联合同
        """
        if not asset_code:
            return error_response(message='请提供资产编码', status_code=400)

        asset = AssetSelector.get_asset_by_code(asset_code)
        if asset is None:
            return error_response(message=f'资产 {asset_code} 不存在', status_code=404)

        contract = asset.asset_contract_code
        if contract is None:
            return error_response(message=f'资产 {asset_code} 未关联合同', status_code=404)

        serializer = ContractDetailSerializer(contract)
        return success_response(data=serializer.data, message='查询成功')

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        """批量创建资产"""
        serializer = AssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AssetService.batch_create_asset(
            serializer.validated_data['items'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        success_serializer = AssetDetailSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量创建完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除资产"""
        serializer = AssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AssetService.batch_delete_asset(
            serializer.validated_data['ids'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )


class OutAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    # 【AGENTS 规范 - 去除冗余】select_related 改为通过 Asset FK 关联查询
    # 原：outasset_applicant_jobcode, outasset_manager_jobcode, outasset_contract_code 已删除
    # 现：通过 outasset_code__asset_xxx 关联查询
    queryset = OutAsset.objects.select_related(
        'outasset_code',
        'outasset_code__asset_type_code',
        'outasset_code__asset_contract_code',
        'outasset_code__asset_storage_code',
        'outasset_code__asset_applicant_jobcode',
        'outasset_code__asset_manager_jobcode',
    ).all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # 【AGENTS 规范 - 去除冗余】filterset_fields 改为通过 Asset FK 过滤
    # 如需按申请人/保管人过滤，需自定义 FilterSet 通过 outasset_code__asset_applicant_jobcode
    filterset_fields = ['outasset_type']
    ordering_fields = ['outasset_date']
    ordering = ['-outasset_date']
    lookup_field = 'outasset_recordcode'

    def get_serializer_class(self) -> Type:
        if self.action in ['retrieve', 'list']:
            return OutAssetDetailSerializer
        return OutAssetSerializer

    def get_queryset(self) -> QuerySet[OutAsset]:
        # 【AGENTS 规范 - 性能优化】列表页使用 for_list() 精简字段
        # 【AGENTS 规范 - 优化】非 list action 统一使用 with_asset_details() 预加载关联
        if self.action == 'list':
            qs = OutAsset.objects.for_list().all()
        else:
            qs = OutAsset.objects.with_asset_details().all()

        keyword = self.request.query_params.get('keyword', '').strip()
        search_type = self.request.query_params.get('searchType', 'all').lower()
        # 【AGENTS 规范 - 去除冗余】状态过滤改为通过 Asset FK
        status_filter = self.request.query_params.get('asset_current_status', '').strip()

        if keyword:
            asset_cond = Q(outasset_code__asset_code__icontains=keyword) | Q(
                outasset_code__asset_name__icontains=keyword)
            # 【AGENTS 规范 - 去除冗余】用户搜索改为通过 Asset FK
            user_cond = (
                Q(outasset_code__asset_applicant_jobcode__employee_jobcode__icontains=keyword) |
                Q(outasset_code__asset_applicant_jobcode__employee_name__icontains=keyword) |
                Q(outasset_code__asset_manager_jobcode__employee_jobcode__icontains=keyword) |
                Q(outasset_code__asset_manager_jobcode__employee_name__icontains=keyword)
            )
            if search_type == 'asset':
                qs = qs.filter(asset_cond)
            elif search_type == 'user':
                qs = qs.filter(user_cond)
            else:
                qs = qs.filter(asset_cond | user_cond)

        if status_filter:
            # 【AGENTS 规范 - 去除冗余】状态过滤改为通过 Asset FK
            qs = qs.filter(outasset_code__asset_current_status=status_filter)

        return qs.order_by('-outasset_date')

    @action(detail=False, methods=['get'], url_path='recyclable')
    def recyclable(self, request):
        """
        获取可回收资产列表（出库状态为 in_use）
        参数：
            - years: 出库时长（年数），返回出库日期距今 >= years 年的记录。例如 years=1 返回出库满1年及以上的资产。
            - search: 搜索关键词
            - searchType: 搜索类型（asset/user/all）
            - asset_code: 资产编码
            - employee_jobcode: 员工工号
            - department_code: 部门编码
            - ordering: 排序字段
        支持分页。
        """
        # 1. 解析查询参数
        filters = {}
        keyword = request.query_params.get('search', '').strip()
        if keyword:
            filters['keyword'] = keyword
            filters['search_type'] = request.query_params.get('searchType', 'all').lower()

        asset_code = request.query_params.get('asset_code', '').strip()
        if asset_code:
            filters['asset_code'] = asset_code

        employee_jobcode = request.query_params.get('employee_jobcode', '').strip()
        if employee_jobcode:
            filters['employee_jobcode'] = employee_jobcode

        department_code = request.query_params.get('department_code', '').strip()
        if department_code:
            filters['department_code'] = department_code

        years = request.query_params.get('years')
        if years and years.isdigit():
            filters['years'] = int(years)

        ordering = request.query_params.get('ordering', '').strip()
        if ordering:
            filters['ordering'] = ordering

        # 2. 调用 Selector 获取过滤后的查询集
        queryset = OutAssetSelector.get_recyclable_outassets(filters if filters else None)

        # 3. 可选的权限过滤（根据业务需求）
        # queryset = self.filter_by_permissions(queryset)

        # 4. 分页响应
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    # 使用 Mixin 默认 list 即可，但为了保证统一格式，保留自定义 list（混合分页处理）
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(data={
            'count': queryset.count(),
            'results': serializer.data
        })

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data.pop('outasset_recordcode', None)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        try:
            outasset = OutAssetService.create_outasset(serializer.validated_data)
            return success_response(data=OutAssetSerializer(outasset).data,
                                    message='出库成功', status_code=status.HTTP_201_CREATED)
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception as e:
            logging.exception('出库创建失败')
            return error_response(message='出库失败，服务器内部错误', status_code=500)

    # 【AGENTS 规范 - P3-40】重写 update/partial_update，调用 OutAssetService.update_outasset()
    # 实现字段白名单校验
    def update(self, request, *args, **kwargs):
        """
        【AGENTS 规范 - P3-40】更新出库记录

        【修复内容】重写 update 方法，调用 OutAssetService.update_outasset()，
        实现字段白名单校验，替代 Mixin 默认的 ORM save。
        """
        outasset_recordcode = self.kwargs.get('outasset_recordcode')
        try:
            outasset = OutAssetService.update_outasset(
                outasset_recordcode=outasset_recordcode,
                update_data=request.data,
            )
            return success_response(data=OutAssetDetailSerializer(outasset).data, message='更新成功')
        except AppValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception as e:
            logging.exception('出库记录更新失败')
            return error_response(message='更新失败，请稍后重试', status_code=500)

    def partial_update(self, request, *args, **kwargs):
        """【AGENTS 规范 - P3-40】部分更新出库记录，复用 update 逻辑"""
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        """批量创建出库记录"""
        serializer = OutAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = OutAssetService.batch_create_outasset(
            serializer.validated_data['items'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        success_serializer = OutAssetSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量出库完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除出库记录"""
        serializer = OutAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = OutAssetService.batch_delete_outasset(
            serializer.validated_data['ids'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @extend_schema(
        parameters=[OpenApiParameter(name='asset_code', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)],
        responses={200: OutAssetSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='by-asset/(?P<asset_code>[^/.]+)')
    def by_asset(self, request, asset_code=None) -> Response:
        """
        【AGENTS 规范】通过资产编码查询出库记录

        【修复 P0-01】AssetSelector.get_asset_by_code() 返回 None 而非抛异常，
        原代码使用 except Asset.DoesNotExist 捕获永远不会触发的异常（死代码）。
        改为显式判断 None，并调用 OutAssetSelector 获取出库记录（含预加载优化）。
        """
        # 【关键修复】使用 None 判断替代 except，修复死代码 Bug
        asset = AssetSelector.get_asset_by_code(asset_code)
        if asset is None:
            return error_response(message=f'资产 {asset_code} 不存在', status_code=404)

        # 【AGENTS 规范】通过 Selector 查询，自动过滤软删除 + 预加载关联
        records = OutAssetSelector.get_outassets_by_asset(asset_code)
        return self._paginate_and_respond(records)

    # 【AGENTS 规范 - P3-07】按申请人查出库记录
    @extend_schema(
        parameters=[OpenApiParameter(name='applicant_jobcode', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)],
        responses={200: OutAssetDetailSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='by-applicant/(?P<applicant_jobcode>[^/.]+)')
    def by_applicant(self, request, applicant_jobcode=None) -> Response:
        """
        【AGENTS 规范 - P3-07】按申请人工号查出库记录

        【修复内容】新增 action，调用 OutAssetSelector.get_outassets_by_applicant()，
        支持按申请人工号查询其提交的所有出库记录，自动预加载关联信息。
        """
        if not applicant_jobcode:
            return error_response(message='请提供申请人工号', status_code=400)

        records = OutAssetSelector.get_outassets_by_applicant(applicant_jobcode)
        return self._paginate_and_respond(records)

    @action(detail=False, methods=['get'])
    def statistics(self, request) -> Response:
        """
        【AGENTS 规范 - P3-10】出库统计

        【修复内容】使用 OutAssetSelector.get_outasset_statistics() 替代手写 ORM 统计逻辑，
        统一统计口径，包含按类型和按状态的分布。
        """
        stats = OutAssetSelector.get_outasset_statistics()
        return success_response(data=stats, message='查询成功')

    def _paginate_and_respond(self, queryset):
        """辅助方法：分页并返回统一响应"""
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)


class RecycleAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    # 【AGENTS 规范 - 去除冗余】select_related 改为通过 Asset FK 关联查询
    # 原：recycle_asset_storage_code, recycle_asset_using_person_jobcode, recycle_asset_recycle_person_jobcode 已删除
    # 现：通过 recycle_asset_code__asset_xxx 关联查询，operator_jobcode 替代 recycle_person
    queryset = RecycleAsset.objects.select_related(
        'outasset_recordcode',
        'recycle_asset_code',
        'recycle_asset_code__asset_type_code',
        'recycle_asset_code__asset_contract_code',
        'recycle_asset_code__asset_storage_code',
        'recycle_asset_code__asset_manager_jobcode',
        'operator_jobcode',
    ).all()
    serializer_class = RecycleAssetSerializer
    pagination_class = CustomPageNumberPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # 【AGENTS 规范 - 去除冗余】filterset_fields 改为通过 Asset FK 或 operator_jobcode
    filterset_fields = [
        'recycle_asset_code',
        'operator_jobcode',
        'recycle_record_code',
    ]
    # 【AGENTS 规范 - 去除冗余】search_fields 改为通过 Asset FK
    # 【AGENTS 规范 - 修复】operator_jobcode__user_name → operator_jobcode__employee_name
    # Employee 模型字段为 employee_name，非 user_name
    search_fields = [
        'recycle_asset_code__asset_name',
        'recycle_record_code',
        'operator_jobcode__employee_name',
    ]
    ordering_fields = ['recycle_asset_date', 'recycle_record_code']
    ordering = ['-recycle_asset_date']
    lookup_field = 'outasset_recordcode'

    def get_queryset(self) -> QuerySet[RecycleAsset]:
        # 【AGENTS 规范 - 性能优化】列表页使用 for_list() 精简字段
        # 【AGENTS 规范 - 优化】非 list action 统一使用 with_asset_details() 预加载关联
        if self.action == 'list':
            qs = RecycleAsset.objects.for_list().all()
        else:
            qs = RecycleAsset.objects.with_asset_details().all()

        date_from = self.request.query_params.get('recycle_date_from')
        date_to = self.request.query_params.get('recycle_date_to')
        if date_from:
            qs = qs.filter(recycle_asset_date__gte=date_from)
        if date_to:
            qs = qs.filter(recycle_asset_date__lte=date_to)
        return qs

    def get_object(self) -> RecycleAsset:
        """
        【AGENTS 规范 - 业务唯一编码】支持多字段查找：
        1. 数字 → 按 id 查找
        2. RECYCLE- 开头 → 按 recycle_record_code 查找
        3. 其他 → 按 outasset_recordcode 查找
        """
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        # 优先尝试 id（纯数字）
        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except RecycleAsset.DoesNotExist:
                pass

        # 尝试 recycle_record_code（RECYCLE- 开头）
        if lookup_value.startswith('RECYCLE-'):
            try:
                obj = queryset.get(recycle_record_code=lookup_value)
                self.check_object_permissions(self.request, obj)
                return obj
            except RecycleAsset.DoesNotExist:
                pass

        # 最后尝试 outasset_recordcode
        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except RecycleAsset.DoesNotExist:
            raise Http404(
                f"RecycleAsset with id/recycle_record_code/outasset_recordcode "
                f"'{lookup_value}' not found."
            )
        self.check_object_permissions(self.request, obj)
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            recycle = RecycleAssetService.create_recycle_asset(serializer.validated_data)
            return success_response(data=RecycleAssetSerializer(recycle).data,
                                    message='回收成功', status_code=status.HTTP_201_CREATED)
        except ValidationError as e:
            return error_response(message=str(e), status_code=400)
        except Exception as e:
            logging.exception('回收创建失败')
            return error_response(message='回收失败，服务器内部错误', status_code=500)

    @action(detail=False, methods=['get'], url_path='by-asset/(?P<recycle_asset_code>[^/.]+)')
    def by_asset(self, request, recycle_asset_code=None) -> Response:
        """
        【AGENTS 规范 - P1-01】通过资产编码查询回收记录

        【修复内容】
        1. 使用 AssetSelector 替代直接 ORM 查询，自动过滤 is_deleted=False
        2. 使用 RecycleAssetSelector 替代直接 queryset.filter，获得预加载优化
        3. AssetSelector.get_asset_by_code() 返回 None，使用 if 判断替代 try/except
        """
        # 【AGENTS 规范】通过 Selector 查询资产，自动过滤软删除
        asset = AssetSelector.get_asset_by_code(recycle_asset_code)
        if asset is None:
            return error_response(message=f'资产 {recycle_asset_code} 不存在', status_code=404)

        # 【AGENTS 规范】通过 Selector 查询回收记录，预加载 outasset_recordcode 和 recycle_recycle_asset_code
        records = RecycleAssetSelector.get_recycle_assets_by_asset(recycle_asset_code)
        return self._paginate_and_respond(records)

    # 【AGENTS 规范 - P3-18】通过出库记录编码查询回收记录
    @extend_schema(
        parameters=[OpenApiParameter(name='outasset_recordcode', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, required=True)],
        responses={200: RecycleAssetSerializer}
    )
    @action(detail=False, methods=['get'], url_path='by-outasset/(?P<outasset_recordcode>[^/.]+)')
    def by_outasset_code(self, request, outasset_recordcode=None) -> Response:
        """
        【AGENTS 规范 - P3-18】通过出库记录编码查询回收记录

        【修复内容】新增 action，调用 RecycleAssetSelector.get_recycle_asset_by_outasset_code()，
        支持通过出库记录编码精确查找对应的回收记录。
        """
        if not outasset_recordcode:
            return error_response(message='请提供出库记录编码', status_code=400)

        record = RecycleAssetSelector.get_recycle_asset_by_outasset_code(outasset_recordcode)
        if record is None:
            return error_response(message=f'未找到出库记录 {outasset_recordcode} 对应的回收记录', status_code=404)

        serializer = RecycleAssetSerializer(record)
        return success_response(data=serializer.data, message='查询成功')

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        """批量创建回收记录"""
        serializer = RecycleAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = RecycleAssetService.batch_create_recycle_asset(
            serializer.validated_data['items'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        success_serializer = RecycleAssetSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量回收完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除回收记录"""
        serializer = RecycleAssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = RecycleAssetService.batch_delete_recycle_asset(
            serializer.validated_data['ids'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )


class DamagedAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """
    待报废资产视图集

    提供待报废资产的 CRUD 操作和审批功能。
    【业务流程】待报废审批通过后，自动流转为已报废资产。
    """
    # 【AGENTS 规范 - 去除冗余】select_related 改为通过 Asset FK 关联查询
    # 原：damaged_asset_storage_code 已删除，现通过 damaged_asset_code__asset_storage_code 关联
    queryset = DamagedAsset.objects.select_related(
        'damaged_asset_code',
        'damaged_asset_code__asset_type_code',
        'damaged_asset_code__asset_contract_code',
        'damaged_asset_code__asset_storage_code',
        'damaged_asset_code__asset_manager_jobcode',
        'approver',
    ).all()
    serializer_class = DamagedAssetSerializer
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # 【AGENTS 规范 - 去除冗余】filterset_fields 移除已删除字段
    filterset_fields = ['approval_status']
    search_fields = ['damaged_asset_code__asset_name']
    ordering_fields = ['damaged_date']
    ordering = ['-damaged_date']
    lookup_field = 'damaged_asset_code'

    def get_queryset(self) -> QuerySet[DamagedAsset]:
        # 【AGENTS 规范 - 性能优化】列表页使用 for_list() 精简字段
        # 【AGENTS 规范 - 优化】非 list action 统一使用 with_asset_details() 预加载关联
        if self.action == 'list':
            return DamagedAsset.objects.for_list().all()
        return DamagedAsset.objects.with_asset_details().all()

    def get_object(self) -> DamagedAsset:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except DamagedAsset.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except DamagedAsset.DoesNotExist:
            raise Http404(f"DamagedAsset with id or damaged_asset_code '{lookup_value}' not found.")
        self.check_object_permissions(self.request, obj)
        return obj

    def destroy(self, request, *args, **kwargs):
        """
        取消待报废申请（软删除待报废记录并恢复状态）
        """
        damaged_asset_code = self.kwargs.get('damaged_asset_code')
        try:
            DamagedAssetService.cancel_damaged_asset(damaged_asset_code)
            return success_response(message='取消待报废申请成功', status_code=status.HTTP_200_OK)
        except AppValidationError as e:
            return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"取消待报废申请失败: {e}")
            return error_response(message='操作失败，请稍后重试', status_code=500)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, **kwargs) -> Response:
        """
        审批通过待报废申请

        【业务流程】审批通过后，自动创建已报废记录，资产状态变更为"已报废"。

        Args:
            request: 请求对象，可包含 approver_jobcode 和 operator_name

        Returns:
            Response: 包含待报废记录和已报废记录的响应
        """
        damaged_asset_code = self.kwargs.get('damaged_asset_code')

        # 获取审批人信息（优先从请求参数获取，否则从当前用户获取）
        approver_jobcode = request.data.get('approver_jobcode') or request.user.auth_id
        operator_name = request.data.get('operator_name') or request.user.auth_username

        try:
            result = DamagedAssetService.approve_damaged_asset(
                damaged_asset_code=damaged_asset_code,
                approver_jobcode=approver_jobcode,
                operator_name=operator_name
            )

            return success_response(
                data={
                    'damaged_asset': DamagedAssetSerializer(result['damaged_asset']).data,
                    'waste_asset': WasteAssetSerializer(result['waste_asset']).data
                },
                message='审批通过，已报废记录已创建'
            )
        except AppValidationError as e:
            return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"审批待报废申请失败: {e}")
            return error_response(message='审批失败，请稍后重试', status_code=500)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, **kwargs) -> Response:
        """
        拒绝待报废申请

        【业务流程】审批拒绝后，待报废记录状态变更为"已拒绝"。

        Args:
            request: 请求对象，可包含 approver_jobcode 和 operator_name

        Returns:
            Response: 包含更新后的待报废记录的响应
        """
        damaged_asset_code = self.kwargs.get('damaged_asset_code')

        # 获取审批人信息
        approver_jobcode = request.data.get('approver_jobcode') or request.user.auth_id
        operator_name = request.data.get('operator_name') or request.user.auth_username

        try:
            result = DamagedAssetService.reject_damaged_asset(
                damaged_asset_code=damaged_asset_code,
                approver_jobcode=approver_jobcode,
                operator_name=operator_name
            )

            return success_response(
                data=DamagedAssetSerializer(result).data,
                message='审批拒绝成功'
            )
        except AppValidationError as e:
            return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logging.exception(f"拒绝待报废申请失败: {e}")
            return error_response(message='审批失败，请稍后重试', status_code=500)

    @action(detail=False, methods=['get'], url_path='by-asset/(?P<damaged_asset_code>[^/.]+)')
    def by_asset(self, request, damaged_asset_code=None) -> Response:
        """
        【AGENTS 规范 - P1-02】通过资产编码查询待报废记录

        【修复内容】
        1. 使用 AssetSelector 替代直接 ORM 查询，自动过滤 is_deleted=False
        2. 使用 DamagedAssetSelector 替代直接 queryset.filter，获得预加载优化
        """
        # 【AGENTS 规范】通过 Selector 查询资产，自动过滤软删除
        asset = AssetSelector.get_asset_by_code(damaged_asset_code)
        if asset is None:
            return error_response(message=f'资产 {damaged_asset_code} 不存在', status_code=404)

        # 【AGENTS 规范】通过 Selector 查询待报废记录，预加载关联信息
        records = DamagedAssetSelector.get_damaged_assets_by_asset(damaged_asset_code)
        return self._paginate_and_respond(records)


class WasteAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """
    已报废资产视图集

    提供已报废资产的 CRUD 操作和查询功能。
    【查询规范】所有查询操作均通过 waste_asset_code（即 Asset.asset_code）进行。
    """
    # 【AGENTS 规范 - 去除冗余】select_related 改为通过 Asset FK 关联查询
    # 原：waste_asset_contract_code 已删除，现通过 waste_asset_code__asset_contract_code 关联
    queryset = WasteAsset.objects.select_related(
        'waste_asset_code',
        'waste_asset_code__asset_type_code',
        'waste_asset_code__asset_contract_code',
        'waste_asset_code__asset_storage_code',
        'waste_asset_code__asset_manager_jobcode',
        'source_damaged_asset',
    ).all()
    serializer_class = WasteAssetSerializer
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['waste_asset_date']
    search_fields = [
        'waste_asset_code__asset_name',
        'waste_asset_code__asset_code'
    ]
    ordering_fields = ['waste_asset_date']
    ordering = ['-waste_asset_date']
    lookup_field = 'waste_asset_code__asset_code'

    def get_queryset(self) -> QuerySet[WasteAsset]:
        # 【AGENTS 规范 - 性能优化】列表页使用 for_list() 精简字段
        # 【AGENTS 规范 - 优化】非 list action 统一使用 with_asset_details() 预加载关联
        if self.action == 'list':
            return WasteAsset.objects.for_list().all()
        return WasteAsset.objects.with_asset_details().all()

    def get_object(self) -> WasteAsset:
        """
        获取已报废记录对象

        【查询规范】支持通过以下方式查找：
        1. 主键ID（数字）
        2. 资产编码（Asset.asset_code）
        """
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        # 优先尝试通过主键查找
        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except WasteAsset.DoesNotExist:
                pass

        # 通过资产编码查找（waste_asset_code__asset_code）
        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except WasteAsset.DoesNotExist:
            raise Http404(f"WasteAsset with id or asset_code '{lookup_value}' not found.")
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=False, methods=['get'], url_path='by-asset/(?P<waste_asset_code>[^/.]+)')
    def by_asset(self, request, waste_asset_code=None) -> Response:
        """
        【AGENTS 规范 - P1-03】通过资产编码查询已报废记录

        【修复内容】
        1. 使用 AssetSelector 替代直接 ORM 查询，自动过滤 is_deleted=False
        2. 使用 WasteAssetSelector 替代直接 queryset.filter，获得预加载优化
        """
        # 【AGENTS 规范】通过 Selector 查询资产，自动过滤软删除
        asset = AssetSelector.get_asset_by_code(waste_asset_code)
        if asset is None:
            return error_response(message=f'资产 {waste_asset_code} 不存在', status_code=404)

        # 【AGENTS 规范】通过 Selector 查询已报废记录，预加载关联信息
        records = WasteAssetSelector.get_waste_assets_by_asset(waste_asset_code)
        return self._paginate_and_respond(records)

    @action(detail=False, methods=['get'])
    def statistics(self, request) -> Response:
        """
        【AGENTS 规范 - P3-25】报废统计

        【修复内容】使用 WasteAssetSelector.get_waste_asset_statistics() 替代手写 ORM 统计逻辑，
        统一统计口径，包含总数、当年报废数和月度分布。
        """
        stats = WasteAssetSelector.get_waste_asset_statistics()
        return success_response(data=stats, message='查询成功')

    # 【AGENTS 规范 - P3-24】按日期范围查询报废记录
    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=OpenApiTypes.DATE, location=OpenApiParameter.QUERY, description='开始日期（YYYY-MM-DD）'),
            OpenApiParameter(name='end_date', type=OpenApiTypes.DATE, location=OpenApiParameter.QUERY, description='结束日期（YYYY-MM-DD）'),
        ],
        responses={200: WasteAssetSerializer(many=True)}
    )
    @action(detail=False, methods=['get'], url_path='by-date-range')
    def by_date_range(self, request) -> Response:
        """
        【AGENTS 规范 - P3-24】按日期范围查询已报废记录

        【修复内容】新增 action，调用 WasteAssetSelector.get_waste_assets_by_date_range()，
        支持通过开始日期和结束日期筛选报废记录。
        """
        from datetime import datetime as dt

        start_date_str = request.query_params.get('start_date', '').strip()
        end_date_str = request.query_params.get('end_date', '').strip()

        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = dt.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return error_response(message='开始日期格式错误，应为 YYYY-MM-DD', status_code=400)

        if end_date_str:
            try:
                end_date = dt.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return error_response(message='结束日期格式错误，应为 YYYY-MM-DD', status_code=400)

        # 【AGENTS 规范】通过 Selector 查询，自动预加载关联信息
        records = WasteAssetSelector.get_waste_assets_by_date_range(
            start_date=start_date,
            end_date=end_date,
        )
        return self._paginate_and_respond(records)


class HardDiskSNViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    queryset = HardDiskSN.objects.select_related('asset_code').all()
    serializer_class = HardDiskSNSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['harddisk_status']
    search_fields = ['harddisk_sn_code', 'harddisk_sn_description']
    ordering_fields = ['id', 'harddisk_number']
    ordering = ['-id']
    lookup_field = 'asset_code'

    def get_object(self) -> HardDiskSN:
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                return queryset.get(pk=lookup_value)
            except HardDiskSN.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except HardDiskSN.DoesNotExist:
            raise Http404(f"HardDiskSN with id or asset_code '{lookup_value}' not found.")
        self.check_object_permissions(self.request, obj)
        return obj

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(data=serializer.data, message='创建成功', status_code=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def search_by_serial_number(self, request) -> Response:
        """
        【AGENTS 规范 - P3-26】通过硬盘序列号查询

        【修复内容】使用 HardDiskSNSelector.get_harddisk_sn_by_code() 替代直接 ORM 查询，
        自动预加载关联资产信息。
        """
        # print(f"request.data: {request.data}")
        serial = request.data.get('harddisk_sn_code')
        if not serial:
            return error_response(message='请提供硬盘序列号', status_code=400)
        # print(f"查询硬盘序列号: {serial}")
        # 【AGENTS 规范】通过 Selector 查询，自动预加载 asset_code 关联
        record = HardDiskSNSelector.get_harddisk_sn_by_code(serial)
        if record is None:
            # 未找到时返回 404 或空数据（根据前端约定）
            return error_response(message='硬盘序列号不存在', status_code=404)

        serializer = self.get_serializer(record)
        # print(f"查询硬盘序列号成功: {serializer.data}")
        return success_response(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='by-asset/(?P<asset_code>[^/.]+)')
    def by_asset(self, request, asset_code=None) -> Response:
        """
        【AGENTS 规范 - P1-04】通过资产编码查询硬盘序列号记录

        【修复内容】
        1. 使用 AssetSelector 替代直接 ORM 查询，自动过滤 is_deleted=False
        2. 使用 HardDiskSNSelector 替代直接 queryset.filter，获得预加载优化
        """
        # 【AGENTS 规范】通过 Selector 查询资产，自动过滤软删除
        asset = AssetSelector.get_asset_by_code(asset_code)
        if asset is None:
            return error_response(message=f'资产 {asset_code} 不存在', status_code=404)

        # 【AGENTS 规范】通过 Selector 查询硬盘序列号记录
        records = HardDiskSNSelector.get_harddisk_sns_by_asset(asset_code)
        return self._paginate_and_respond(records)

    @action(detail=False, methods=['post'], url_path='batch')
    def batch_save(self, request) -> Response:
        """
        【AGENTS 规范】批量保存硬盘序列号记录

        统一处理新增和编辑场景，接收前端提交的 asset_code + disks 数组。
        采用"先验证后执行"策略，所有校验通过后才写入数据库。
        使用数据库事务确保批量操作的原子性。

        请求格式：
            POST /assets/harddisk-sn/batch/
            {
                "asset_code": "ASSET-ZDDN-000004",
                "disks": [
                    { "harddisk_no": 1, "harddisk_sn_code": "SN001", "harddisk_type": "SSD", ... },
                    { "id": 5, "harddisk_no": 2, "harddisk_sn_code": "SN002", ... }
                ]
            }

        响应格式：
            {
                "code": 200,
                "message": "批量保存成功",
                "data": {
                    "created": 1,
                    "updated": 1,
                    "total": 2,
                    "asset_code": "ASSET-ZDDN-000004",
                    "harddisk_number": 2
                }
            }
        """
        # 【AGENTS 规范】使用专用批量序列化器进行数据校验
        serializer = HardDiskSNBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 【AGENTS 规范】校验通过后，调用 Service 层执行业务逻辑
        try:
            result = HardDiskSNService.batch_save(serializer.validated_data)
        except AppValidationError as e:
            return error_response(message=str(e.detail), status_code=400)

        return success_response(
            data=result,
            message=f"批量保存成功，新增 {result['created']} 条，更新 {result['updated']} 条",
            status_code=status.HTTP_200_OK
        )


class DashboardViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ViewSet):
    """
    【AGENTS 规范 - P1-08】仪表盘视图

    【修复内容】所有统计查询改用 DashboardSelector，View 仅负责返回 Response。
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DashboardStatSerializer

    @action(detail=False, methods=['get'])
    def overview(self, request) -> Response:
        """
        仪表盘概览统计

        【AGENTS 规范】通过 DashboardSelector 获取统计数据，View 不直接调用 ORM。
        """
        # 【关键修复】统计查询统一通过 Selector，自动过滤 is_deleted=False
        stats = DashboardSelector.get_overview_statistics()
        return success_response(data=stats)

    @action(detail=False, methods=['get'])
    def recent_out_assets(self, request) -> Response:
        """
        最近出库记录

        【AGENTS 规范】通过 DashboardSelector 获取数据，View 不直接调用 ORM。
        """
        limit = min(int(request.query_params.get('limit', 10) or 10), 100)
        # 【AGENTS 规范】数据格式化在 Selector 中完成，View 仅返回 Response
        result = DashboardSelector.get_recent_out_assets(limit=limit)
        return success_response(data=result)

    @action(detail=False, methods=['get'])
    def recent_recycle_assets(self, request) -> Response:
        """
        最近回收记录

        【AGENTS 规范】通过 DashboardSelector 获取数据，View 不直接调用 ORM。
        """
        limit = min(int(request.query_params.get('limit', 10) or 10), 100)
        # 【AGENTS 规范】数据格式化在 Selector 中完成，View 仅返回 Response
        result = DashboardSelector.get_recent_recycle_assets(limit=limit)
        return success_response(data=result)
