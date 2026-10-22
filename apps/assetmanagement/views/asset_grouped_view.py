"""
资产分组汇总端点视图

`GET /api/v1/assets/grouped/` —— 资产台账「分组展开表格」的汇总端点。

分页与补码的先后顺序是本视图唯一的技术要点：
`asset_codes` 必须**在分页切片之后**补齐，否则要把每组明细全量载入内存。
`PaginateAndRespondMixin._post_paginate_hook` 正是为此提供的扩展点，
故分页+响应序列只有一份实现（DR-1），本视图不重写。

未挂 `LoggingMixin` / `ResponseWrapperMixin`：二者只钩 `perform_create/update/destroy`
（写操作），对只读端点无收益，且其 `super()` 依赖 ModelViewSet，在 GenericViewSet 上不存在。
统一信封由分页器 `get_paginated_response` 直接产出，无需额外包装。
"""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors.asset_grouped_selector import AssetGroupedSelector
from apps.assetmanagement.serializers.asset_grouped_serializers import (
    AssetGroupQuerySerializer,
    AssetGroupSummarySerializer,
)
from core.mixins import PaginateAndRespondMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove, request_method, resolve_viewset_permissions


SUMMARY_FILTER_PARAMETERS: list[OpenApiParameter] = [
    OpenApiParameter(
        "asset_current_status",
        OpenApiTypes.STR,
        description="状态精确过滤（复用既有键）",
        required=False,
    ),
    OpenApiParameter(
        "asset_type_recordcode",
        OpenApiTypes.STR,
        description="类型 recordcode 精确过滤（复用既有键）",
        required=False,
    ),
    OpenApiParameter(
        "asset_storage_recordcode",
        OpenApiTypes.STR,
        description="仓库 recordcode 精确过滤（复用既有键）",
        required=False,
    ),
    OpenApiParameter(
        "contract_code",
        OpenApiTypes.STR,
        description="合同编码精确过滤（新增）",
        required=False,
    ),
    OpenApiParameter(
        "no_contract",
        OpenApiTypes.BOOL,
        description="true 时仅返回无合同哨兵组（新增）；与 contract_code 互斥，同传返回 400",
        required=False,
    ),
    # --- C 批新增 6 键：模糊 5（`*__icontains`，与主列表 combine_search 同口径）+ 分类 1 ---
    OpenApiParameter(
        "asset_code",
        OpenApiTypes.STR,
        description="资产编码模糊过滤（新增，`icontains`）",
        required=False,
    ),
    OpenApiParameter(
        "asset_name",
        OpenApiTypes.STR,
        description="资产名称模糊过滤（新增，`icontains`）",
        required=False,
    ),
    OpenApiParameter(
        "asset_brand",
        OpenApiTypes.STR,
        description="资产品牌模糊过滤（新增，`icontains`）",
        required=False,
    ),
    OpenApiParameter(
        "asset_specification",
        OpenApiTypes.STR,
        description="资产规格模糊过滤（新增，`icontains`）",
        required=False,
    ),
    OpenApiParameter(
        "asset_contract_name",
        OpenApiTypes.STR,
        description="合同名称模糊过滤（新增，走 `asset_contract_recordcode__contract_name`）",
        required=False,
    ),
    OpenApiParameter(
        "asset_type_category",
        OpenApiTypes.STR,
        description=(
            "资产类型分类精确过滤（新增）。值取 `AssetType.type_code`，"
            "展开为该分类下全部类型的 `asset_type_recordcode__in`；分类不存在时返回空集"
        ),
        required=False,
    ),
]


def _parse_filters(request: Request) -> dict[str, Any]:
    """query 参数 -> Selector 层 filters

    形状与取值合法性交给 `AssetGroupQuerySerializer`，实际过滤统一在 Selector 层（DR-3）。
    空串视为未传（与既有 `_apply_summary_filters` 的口径一致）；
    `page` / `page_size` 等未声明参数被序列化器忽略，交由分页器处理。
    """
    payload = {key: value for key, value in request.query_params.items() if value != ""}
    serializer = AssetGroupQuerySerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class AssetGroupedViewSet(PaginateAndRespondMixin, viewsets.GenericViewSet):  # type: ignore[type-arg]
    """资产分组汇总"""

    # 非模型端点：聚合结果是 dict 而非模型实例。占位 queryset 仅用于避免
    # GenericAPIView.get_queryset() 的 None 断言（OpenAPI 生成期可能触达），不参与任何查询。
    queryset: QuerySet[Asset] = Asset.objects.none()
    serializer_class = AssetGroupSummarySerializer
    pagination_class = CustomPageNumberPagination

    # 全局 DEFAULT_FILTER_BACKENDS 含 SearchFilter/OrderingFilter（config/settings/base.py:188），
    # drf-spectacular 会据此为每个 viewset 追加 search/ordering 参数。但本端点不调用
    # filter_queryset —— 筛选唯一入口是 Selector 的 _apply_summary_filters（DR-3），
    # 且排序由契约固定。故显式置空，避免 schema 宣称运行时并不支持的参数。
    filter_backends: list[Any] = []

    # DRF 每请求新建视图实例，此处暂存当次请求的筛选参数供补码钩子复用，
    # 避免重复解析与校验（DRY）
    _summary_filters: dict[str, Any]

    def get_permissions(self) -> list[BasePermission]:
        """只读端点：读权限与既有资产列表一致（认证即可）

        行级数据隔离不在此层，而在 Selector 的 `AssetSelector.apply_user_scope`。
        """
        return resolve_viewset_permissions(self.action, [], IsAssetAdminOrAbove, method=request_method(self))

    @extend_schema(
        summary="资产分组汇总",
        description=(
            "按 `[contract_code, asset_name, asset_specification, asset_brand]` 四元组聚合。"
            "`data.count` 是**分组总数**，与 `results[i].asset_count`（组内资产条数）不是同一概念。"
            "排序：`asset_count` 降序（主键）→ 合同号升序（null 置末）→ 名称/规格/品牌。"
        ),
        parameters=SUMMARY_FILTER_PARAMETERS,
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """分组汇总列表"""
        self._summary_filters = _parse_filters(request)
        queryset = AssetGroupedSelector.build_summary_queryset(
            user=request.user,
            filters=self._summary_filters,
        )
        return self._paginate_and_respond(queryset)

    def _post_paginate_hook(self, page: Any) -> None:
        """分页切片后、序列化前补当页各组的 asset_codes

        只对当页取数；复用与聚合完全相同的筛选集与权限范围，
        故组内编码数必然等于该组 `asset_count`（契约不变量 I-1）。
        """
        AssetGroupedSelector.attach_asset_codes(
            user=self.request.user,
            filters=self._summary_filters,
            rows=page,
        )
