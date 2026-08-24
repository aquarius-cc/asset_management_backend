"""
资产生命周期事件视图集

包含 BrokenAsset(损坏)、LostAsset(遗失)、FoundAsset(找回)视图集。
这些视图集结构高度相似,统一管理。RepairAsset(维修)已拆分至 repair_asset_view.py。

【DR-1 收敛】公共骨架提取至 _lifecycle_base.AssetLifecycleViewSetBase,
子类仅声明差异化类属性; batch_create 因 FoundAsset 不提供而留在各子类(方案 A)。
"""

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from apps.assetmanagement.models import BrokenAsset, FoundAsset, LostAsset
from apps.assetmanagement.selectors import (
    BrokenAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
)
from apps.assetmanagement.serializers import (
    BrokenAssetBatchCreateSerializer,
    BrokenAssetCreateSerializer,
    BrokenAssetDetailSerializer,
    BrokenAssetListSerializer,
    BrokenAssetUpdateSerializer,
    FoundAssetCreateSerializer,
    FoundAssetDetailSerializer,
    FoundAssetListSerializer,
    FoundAssetUpdateSerializer,
    LostAssetBatchCreateSerializer,
    LostAssetCreateSerializer,
    LostAssetDetailSerializer,
    LostAssetListSerializer,
    LostAssetUpdateSerializer,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.batch_mixins import BatchResponseHelper
from utils.user_utils import resolve_operator

from ._lifecycle_base import AssetLifecycleViewSetBase


@extend_schema(tags=["损坏资产"])
class BrokenAssetViewSet(AssetLifecycleViewSetBase):  # type: ignore[assignment]
    queryset = BrokenAsset.objects.for_list().all()
    model = BrokenAsset
    selector = BrokenAssetSelector
    list_serializer = BrokenAssetListSerializer
    create_serializer = BrokenAssetCreateSerializer
    update_serializer = BrokenAssetUpdateSerializer
    detail_serializer = BrokenAssetDetailSerializer
    delete_service_method = "delete_broken_asset"
    search_fields_extra = ("broken_reason",)
    ordering_field = "broken_date"

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = BrokenAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = AssetLifecycleMixin.batch_create_broken_assets(
            items=serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(message 显式传入, 契约不变)
        return BatchResponseHelper.create_response(
            result,
            BrokenAssetCreateSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )


@extend_schema(tags=["遗失资产"])
class LostAssetViewSet(AssetLifecycleViewSetBase):  # type: ignore[assignment]
    queryset = LostAsset.objects.for_list().all()
    model = LostAsset
    selector = LostAssetSelector
    list_serializer = LostAssetListSerializer
    create_serializer = LostAssetCreateSerializer
    update_serializer = LostAssetUpdateSerializer
    detail_serializer = LostAssetDetailSerializer
    delete_service_method = "delete_lost_asset"
    search_fields_extra = ("lost_reason",)
    ordering_field = "lost_date"

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        serializer = LostAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = AssetLifecycleMixin.batch_create_lost_assets(
            items=serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(message 显式传入, 契约不变)
        return BatchResponseHelper.create_response(
            result,
            LostAssetCreateSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )


@extend_schema(tags=["找回资产"])
class FoundAssetViewSet(AssetLifecycleViewSetBase):  # type: ignore[assignment]
    """FoundAsset 不提供批量创建(后端无对应 Service 方法), 其余行为与 Broken/Lost 一致"""

    queryset = FoundAsset.objects.for_list().all()
    model = FoundAsset
    selector = FoundAssetSelector
    list_serializer = FoundAssetListSerializer
    create_serializer = FoundAssetCreateSerializer
    update_serializer = FoundAssetUpdateSerializer
    detail_serializer = FoundAssetDetailSerializer
    delete_service_method = "delete_found_asset"
    ordering_field = "found_date"
