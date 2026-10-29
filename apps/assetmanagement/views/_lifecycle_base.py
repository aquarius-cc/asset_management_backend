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
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.batch_mixins import BatchDeleteViewMixin
from core.excel_export import ExportExcelMixin
from core.mixins import LoggingMixin, PaginateAndRespondMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsAssetAdminOrAbove, request_method, resolve_viewset_permissions
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator

from ._mixins import AdminWritePermissionMixin, RecordcodeLookupMixin


class AssetLifecycleViewSetBase(  # type: ignore[misc]
    RecordcodeLookupMixin,
    AdminWritePermissionMixin,
    ExportExcelMixin,
    PaginateAndRespondMixin,
    BatchDeleteViewMixin,
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

    # 子类差异点以类属性注入, 新增子类时须逐项核对上方 docstring 声明清单
    model = None
    selector = None
    list_serializer = None
    # 【C-1 修复】Any 注解: 基类 None 占位、子类注入真实序列化器类(对齐 batch_delete_serializer)
    create_serializer: Any = None
    update_serializer = None
    detail_serializer = None
    delete_service_method = ""
    # 【C-1 修复】单条 create 委托的 AssetLifecycleMixin 方法名(子类注入:
    # mark_asset_broken / mark_asset_lost / find_and_return_asset),
    # 覆盖 DRF 默认 serializer.save() 直落库绕过 FSM/审计/行级隔离的缺口
    create_service_method: str = ""
    # 【M-RC-05】update 审计描述用的记录中文名(子类注入: 损坏资产/遗失资产/找回资产)
    update_label: str = ""
    batch_delete_serializer: Any = None
    batch_delete_service = AssetLifecycleMixin.batch_delete_lifecycle_asset
    batch_delete_passes_user = True

    pagination_class = CustomPageNumberPagination
    lookup_field = "recordcode"
    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "batch_create",
        "batch_delete",
    ]

    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]

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
        """RBAC: 写操作(含 batch_create)需 asset_admin+,读操作需认证"""
        return resolve_viewset_permissions(
            self.action, self.admin_actions, IsAssetAdminOrAbove, method=request_method(self)
        )

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

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """删除生命周期事件记录(软删, 与批量删除同语义; 镜像 repair_asset_view.destroy)"""
        obj = self.get_object()
        getattr(AssetLifecycleMixin, self.delete_service_method)(
            recordcode=obj.recordcode,
            operator_jobcode=resolve_operator(request.user)[0],
            operator_name=resolve_operator(request.user)[1],
            user=request.user,
        )
        return success_response(data={"recordcode": obj.recordcode}, message="删除成功")

    def build_create_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        """子类钩子: 从 validated_data 组装 create_service_method 的业务参数(不含 asset_code/operator/user)

        Broken/Lost 仅透传 reason/description/date; Found 额外做
        lost_asset_recordcode 一致性校验(防客户端传入他资产的遗失记录被静默忽略)。
        """
        raise NotImplementedError

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """【C-1 修复】单条 create 委托 AssetLifecycleMixin(与 destroy/batch_delete 委托模式一致)

        覆盖 DRF 默认 serializer.save() 直落库缺口: 现走 FSM 校验+资产状态流转+
        审计日志+BEQ-02 行级隔离, 与 batch_create 语义统一。
        响应契约不变: 201 + code=0 + CreateSerializer(记录).data。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        asset: Asset = validated["asset_recordcode"]
        operator_jobcode, operator_name = resolve_operator(request.user)
        record = getattr(AssetLifecycleMixin, self.create_service_method)(
            asset_code=asset.asset_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            user=request.user,
            **self.build_create_kwargs(validated),
        )
        return success_response(data=self.create_serializer(record).data, message="创建成功", status_code=201)

    def update(self, request: Any, *args: Any, partial: bool = False, **kwargs: Any) -> Response:
        """【M-RC-05】update/partial_update 委托 update_lifecycle_record(与 create/destroy 同范式)

        覆盖 DRF 默认 serializer.save() 直落库绕过行级隔离与审计的缺口:
        走 select_for_update + BEQ-02 行级隔离 + OperationLogService UPDATE 审计。
        响应契约不变: 200 + code=0 + UpdateSerializer(record).data + "更新成功"
        (对齐 ResponseWrapperMixin.update, partial kwarg 由 DRF partial_update 透传)。
        """
        partial = bool(kwargs.pop("partial", False)) or partial
        obj = self.get_object()
        serializer = self.update_serializer(obj, data=request.data, partial=partial)  # type: ignore[attr-defined]
        serializer.is_valid(raise_exception=True)
        operator_jobcode, operator_name = resolve_operator(request.user)
        record = AssetLifecycleMixin.update_lifecycle_record(
            model=self.model,  # type: ignore[attr-defined]
            recordcode=obj.recordcode,
            update_data=dict(serializer.validated_data),
            record_label=self.update_label,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            user=request.user,
        )
        return success_response(data=self.update_serializer(record).data, message="更新成功")  # type: ignore[attr-defined]

    def batch_delete_invoke(self, ids: list[str], **kwargs: Any) -> dict[str, Any]:
        """编排注入: 三子类差异仅 delete_service_method 字符串(子类属性注入)"""
        return AssetLifecycleMixin.batch_delete_lifecycle_asset(ids, self.delete_service_method, **kwargs)

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
