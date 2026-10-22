"""
资产分组明细端点视图

`GET /api/v1/assets/group_children/` —— 资产台账「分组展开表格」的明细端点。

与汇总端点（`asset_grouped_view.py`）的分工：
- 汇总端点给出「有哪些组、每组几条」
- 本端点按 `group_key` 精确取某一组的资产明细（分页）

**契约不变量 I-1**：同一次筛选下，本端点 `data.count` 必须 === 汇总端点对应组的
`asset_count`。这不是靠约定保证的，而是靠 `build_children_queryset` 与汇总端点
复用同一个 `_scoped_queryset`（同筛选集、同权限范围）+ 同一个 `_build_group_q`
（Selector 层唯一实现，见 `asset_grouped_selector.py`）。

未挂 `LoggingMixin` / `ResponseWrapperMixin`：二者只钩写操作，对只读端点无收益。
统一信封由分页器 `get_paginated_response` 直接产出。
"""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors.asset_grouped_selector import (
    AssetGroupedSelector,
    GroupKeyError,
)
from apps.assetmanagement.serializers.asset_crud_serializers import AssetDetailSerializer
from apps.assetmanagement.serializers.asset_grouped_serializers import (
    AssetGroupChildrenQuerySerializer,
)
from core.mixins import PaginateAndRespondMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove, request_method, resolve_viewset_permissions


CHILDREN_FILTER_PARAMETERS: list[OpenApiParameter] = [
    OpenApiParameter(
        "group_key",
        OpenApiTypes.STR,
        description=(
            "JSON 数组字符串，汇总端点 `group_key` 原样回传："
            '`["HT00001","笔记本电脑","14寸/i5","联想"]`。'
            "三个 null 位（合同/规格/品牌）须写 `null`，不可写空串。"
        ),
        required=True,
    ),
    OpenApiParameter(
        "asset_current_status",
        OpenApiTypes.STR,
        description="状态精确过滤，**必须与汇总端点的当前筛选一致**",
        required=False,
    ),
    OpenApiParameter(
        "asset_type_recordcode",
        OpenApiTypes.STR,
        description="类型 recordcode 精确过滤，必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_storage_recordcode",
        OpenApiTypes.STR,
        description="仓库 recordcode 精确过滤，必须与汇总端点一致",
        required=False,
    ),
    # --- C 批新增 6 键：必须与汇总端点同名字段、同一匹配口径（否则 I-1 漂移）---
    OpenApiParameter(
        "asset_code",
        OpenApiTypes.STR,
        description="资产编码模糊过滤（`icontains`），必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_name",
        OpenApiTypes.STR,
        description="资产名称模糊过滤（`icontains`），必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_brand",
        OpenApiTypes.STR,
        description="资产品牌模糊过滤（`icontains`），必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_specification",
        OpenApiTypes.STR,
        description="资产规格模糊过滤（`icontains`），必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_contract_name",
        OpenApiTypes.STR,
        description="合同名称模糊过滤，必须与汇总端点一致",
        required=False,
    ),
    OpenApiParameter(
        "asset_type_category",
        OpenApiTypes.STR,
        description="资产类型分类精确过滤（展开为 `asset_type_recordcode__in`），必须与汇总端点一致",
        required=False,
    ),
]


def _parse_children_params(request: Request) -> tuple[str, dict[str, Any]]:
    """query 参数 -> (group_key, 非组键筛选集)

    形状与取值合法性交给 `AssetGroupChildrenQuerySerializer`，实际过滤统一在 Selector 层（DR-3）。
    `page` / `page_size` 等未声明参数被序列化器忽略，交由分页器处理。
    """
    serializer = AssetGroupChildrenQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    validated = dict(serializer.validated_data)
    return str(validated.pop("group_key")), validated


class AssetGroupChildrenViewSet(PaginateAndRespondMixin, viewsets.GenericViewSet):  # type: ignore[type-arg]
    """资产分组明细（展开）"""

    # 占位 queryset（不参与任何查询）：分页与响应均由 `list` 经
    # `PaginateAndRespondMixin` 编排，与汇总端点同构。置 `.none()` 而非留空，
    # 以避免 GenericAPIView.get_queryset() 的 None 断言（OpenAPI 生成期可能触达）。
    queryset: QuerySet[Asset] = Asset.objects.none()
    serializer_class = AssetDetailSerializer
    pagination_class = CustomPageNumberPagination

    # 同汇总端点：不调用 filter_queryset（筛选唯一入口在 Selector，DR-3），
    # 故置空以免 drf-spectacular 追加运行时并不支持的 search/ordering 参数。
    filter_backends: list[Any] = []

    def get_permissions(self) -> list[BasePermission]:
        """只读端点：读权限与汇总端点一致（认证即可）

        行级数据隔离不在此层，而在 Selector 的 `AssetSelector.apply_user_scope` ——
        与汇总端点同一实现，故两端的可见范围天然一致（I-1 的前提之一）。
        """
        return resolve_viewset_permissions(self.action, [], IsAssetAdminOrAbove, method=request_method(self))

    @extend_schema(
        summary="资产分组明细",
        description=(
            "按 `group_key` 返回该组的资产明细（`AssetDetailSerializer`，含 `harddisk_sns`）。"
            "`data.count` **恒等于**汇总端点对应组的 `asset_count`（契约不变量 I-1）。"
            "各筛选参数须与汇总端点的当前 active 筛选原样透传。"
        ),
        parameters=CHILDREN_FILTER_PARAMETERS,
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """分组明细列表"""
        group_key, filters = _parse_children_params(request)
        try:
            queryset = AssetGroupedSelector.build_children_queryset(
                user=request.user,
                group_key=group_key,
                filters=filters,
            )
        except GroupKeyError as exc:
            # 非法 group_key 是客户端错误而非服务端故障：转 400 并保留原因为文案。
            # 不可 `filter(pk__in=[])` 静默返回空集 —— 那会让「参数写错」伪装成「该组为空」。
            raise serializers.ValidationError(str(exc)) from exc
        return self._paginate_and_respond(queryset)
