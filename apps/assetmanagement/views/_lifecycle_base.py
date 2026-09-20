"""
资产生命周期事件视图集公共基类(DR-1 收敛)

BrokenAsset / LostAsset / FoundAsset 三个 ViewSet 的公共骨架。
子类仅声明差异化类属性; batch_create 因 FoundAsset 不提供而留在各子类(方案 A, 最保守)。

【契约保护】本文件所有响应键名、错误码、message 文案均由
test_batch_contract_snapshot.py 与 test_lifecycle_view_api.py 锁定,
修改前必须先更新对应快照断言。批量删除文案契约 2026-09-20 经 #17
定案为中文标准模板(与 test_b5_baseline_snapshot.py 全仓 8 端点同款)。
"""

from typing import Any

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.batch_mixins import BatchResponseHelper
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._export_mixin import ExportExcelMixin
from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class AssetLifecycleViewSetBase(  # type: ignore[misc]
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet[Any],
):
    """
    损坏/遗失/找回视图集的公共基类。

    子类必须声明以下类属性:
        model                        - 对应模型(BrokenAsset/LostAsset/FoundAsset)
        selector                     - 对应 Selector(BrokenAssetSelector/...)
        list_serializer              - 列表序列化器
        create_serializer            - 创建序列化器
        update_serializer            - 更新序列化器
        detail_serializer            - 详情序列化器(默认分支)
        delete_service_method        - AssetLifecycleMixin 上的单条删除方法名
        ordering_field               - 业务时间字段(broken_date/lost_date/found_date)
        search_fields_extra          - 额外搜索字段元组
    """

    # AI_REVIEW_NEEDED: 子类差异点以类属性注入, 新增子类时必须逐项核对以下声明
    model = None
    selector = None
    list_serializer = None
    create_serializer = None
    update_serializer = None
    detail_serializer = None
    delete_service_method = ""

    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    @property
    def search_fields(self) -> list[str]:
        return ["asset_recordcode__asset_name", *getattr(self, "search_fields_extra", ())]

    @property
    def ordering_fields(self) -> list[str]:
        return [self.ordering_field, "created_at"]  # type: ignore[attr-defined]

    @property
    def ordering(self) -> list[str]:
        return [f"-{self.ordering_field}"]  # type: ignore[attr-defined]

    def get_permissions(self) -> Any:
        if self.action in ("create", "update", "partial_update", "destroy", "batch_delete"):
            return [IsAssetAdminOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self) -> Any:
        return self.selector.get_queryset_for_user(self.request.user)  # type: ignore[attr-defined]

    def get_serializer_class(self) -> Any:
        if self.action == "list":
            return self.list_serializer
        elif self.action == "create":
            return self.create_serializer
        elif self.action in ["update", "partial_update"]:
            return self.update_serializer
        return self.detail_serializer

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request: Any) -> Response:
        """批量删除(三视图集完全一致, 仅 delete_service_method 字符串差异, 编排收敛至 Service)"""
        ids = request.data.get("ids", [])
        if not ids:
            return error_response(message="缺少 ids 参数", status_code=400)
        operator_jobcode, operator_name = resolve_operator(request.user)
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            ids, self.delete_service_method, operator_jobcode, operator_name,
        )
        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(键集/失败分类/message 模板逐字段对齐全仓 8 端点)
        return BatchResponseHelper.delete_response(
            result,
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @action(detail=False, methods=["get"], url_path="by-asset/(?P<asset_code>[^/.]+)")
    def by_asset(self, request: Any, asset_code: Any = None) -> Response:
        """按资产编码查询该生命周期事件(可见性校验与分页行为三视图集一致)"""
        visible = AssetSelector.get_queryset_for_user(request.user).filter(asset_code=asset_code).exists()
        if not visible:
            return error_response(message=f"资产 {asset_code} 不存在", status_code=404)
        records = self.selector.get_by_asset_code(asset_code, user=request.user)  # type: ignore[attr-defined]
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(records, many=True)
        return success_response(data=serializer.data, message="查询成功")
