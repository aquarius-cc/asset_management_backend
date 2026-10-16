"""
资产生命周期事件视图集

包含 BrokenAsset(损坏)、LostAsset(遗失)、FoundAsset(找回)视图集。
这些视图集结构高度相似,统一管理。RepairAsset(维修)已拆分至 repair_asset_view.py。

【DR-1 收敛】公共骨架提取至 _lifecycle_base.AssetLifecycleViewSetBase,
子类仅声明差异化类属性; batch_create 因 FoundAsset 不提供而留在各子类(方案 A)。
"""

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.assetmanagement.models import BrokenAsset, FoundAsset, LostAsset
from apps.assetmanagement.selectors import (
    BrokenAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
)
from apps.assetmanagement.serializers import (
    BrokenAssetBatchCreateSerializer,
    BrokenAssetBatchDeleteSerializer,
    BrokenAssetCreateSerializer,
    BrokenAssetDetailSerializer,
    BrokenAssetListSerializer,
    BrokenAssetUpdateSerializer,
    FoundAssetBatchDeleteSerializer,
    FoundAssetCreateSerializer,
    FoundAssetDetailSerializer,
    FoundAssetListSerializer,
    FoundAssetUpdateSerializer,
    LostAssetBatchCreateSerializer,
    LostAssetBatchDeleteSerializer,
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
class BrokenAssetViewSet(AssetLifecycleViewSetBase):
    queryset = BrokenAsset.objects.for_list().all()
    model = BrokenAsset  # type: ignore[assignment]
    selector = BrokenAssetSelector  # type: ignore[assignment]
    list_serializer = BrokenAssetListSerializer  # type: ignore[assignment]
    create_serializer = BrokenAssetCreateSerializer
    update_serializer = BrokenAssetUpdateSerializer  # type: ignore[assignment]
    detail_serializer = BrokenAssetDetailSerializer  # type: ignore[assignment]
    delete_service_method = "delete_broken_asset"
    create_service_method = "mark_asset_broken"
    batch_delete_serializer = BrokenAssetBatchDeleteSerializer
    search_fields_extra = ("broken_reason",)
    ordering_field = "broken_date"

    def build_create_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "broken_reason": validated_data["broken_reason"],
            "broken_description": validated_data.get("broken_description", ""),
            "broken_date": validated_data.get("broken_date"),
        }

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: Any) -> Response:
        serializer = BrokenAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = AssetLifecycleMixin.batch_create_broken_assets(
            items=serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            user=request.user,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(message 显式传入, 契约不变)
        return BatchResponseHelper.create_response(
            result,
            BrokenAssetCreateSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )


@extend_schema(tags=["遗失资产"])
class LostAssetViewSet(AssetLifecycleViewSetBase):
    queryset = LostAsset.objects.for_list().all()
    model = LostAsset  # type: ignore[assignment]
    selector = LostAssetSelector  # type: ignore[assignment]
    list_serializer = LostAssetListSerializer  # type: ignore[assignment]
    create_serializer = LostAssetCreateSerializer
    update_serializer = LostAssetUpdateSerializer  # type: ignore[assignment]
    detail_serializer = LostAssetDetailSerializer  # type: ignore[assignment]
    delete_service_method = "delete_lost_asset"
    create_service_method = "mark_asset_lost"
    batch_delete_serializer = LostAssetBatchDeleteSerializer
    search_fields_extra = ("lost_reason",)
    ordering_field = "lost_date"

    def build_create_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "lost_reason": validated_data["lost_reason"],
            "last_known_location": validated_data.get("last_known_location", ""),
            "lost_description": validated_data.get("lost_description", ""),
            "lost_date": validated_data.get("lost_date"),
        }

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: Any) -> Response:
        serializer = LostAssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = AssetLifecycleMixin.batch_create_lost_assets(
            items=serializer.validated_data["items"],
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            user=request.user,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(message 显式传入, 契约不变)
        return BatchResponseHelper.create_response(
            result,
            LostAssetCreateSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )


@extend_schema(tags=["找回资产"])
class FoundAssetViewSet(AssetLifecycleViewSetBase):
    """FoundAsset 不提供批量创建(后端无对应 Service 方法), 其余行为与 Broken/Lost 一致"""

    queryset = FoundAsset.objects.for_list().all()
    model = FoundAsset  # type: ignore[assignment]
    selector = FoundAssetSelector  # type: ignore[assignment]
    list_serializer = FoundAssetListSerializer  # type: ignore[assignment]
    create_serializer = FoundAssetCreateSerializer
    update_serializer = FoundAssetUpdateSerializer  # type: ignore[assignment]
    detail_serializer = FoundAssetDetailSerializer  # type: ignore[assignment]
    delete_service_method = "delete_found_asset"
    create_service_method = "find_and_return_asset"
    batch_delete_serializer = FoundAssetBatchDeleteSerializer
    ordering_field = "found_date"

    def build_create_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        from core.exceptions import AppValidationError

        # 一致性校验: 客户端传入的遗失记录必须属于目标资产(service 内部按资产自查,
        # 不校验则错配的 lost_asset_recordcode 会被静默忽略)
        lost_record = validated_data["lost_asset_recordcode"]
        asset = validated_data["asset_recordcode"]
        # 【C-1 修复】LostAsset.asset_recordcode FK 声明 to_field="recordcode", 故
        # asset_recordcode_id 存的是 Asset.recordcode 字符串而非整数 pk——与 asset.pk
        # 比较恒不相等, 一致性校验对一切请求误触发 LOST_ASSET_MISMATCH(400)。
        # 改比较对象实例的 recordcode(FK to_field 的真值), 语义=「遗失记录确属于该资产」。
        if lost_record.asset_recordcode_id != asset.recordcode:
            raise AppValidationError(detail="遗失记录与资产不匹配", error_code="LOST_ASSET_MISMATCH")
        return {
            "found_location": validated_data.get("found_location", ""),
            "found_description": validated_data.get("found_description", ""),
            "found_date": validated_data.get("found_date"),
        }
