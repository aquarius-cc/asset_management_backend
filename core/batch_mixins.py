"""
批量操作通用 Mixin

提供批量创建/删除/更新的公共执行框架,统一处理:
- MAX_BATCH_SIZE 前置校验
- 逐条独立执行(单条失败不影响其他记录)
- 异常分类捕获(AppValidationError → error_code,其他 → INTERNAL_ERROR)
- 统一返回格式(total, success_count, fail_count, success_items, fail_items)

使用方式:
    class AssetService(BatchOperationMixin):
        @staticmethod
        def batch_create_asset(asset_data_list, ...):
            def _create_item(idx, asset_data):
                result = AssetService.create_asset(asset_data=asset_data, ...)
                return result  # 成功返回对象

            return BatchOperationMixin.batch_execute(
                items=asset_data_list,
                process_fn=_create_item,
                max_batch_size=100,
                use_transaction=False,  # 创建方法自身已有 @transaction.atomic
            )
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError
from utils.response_utils import success_response
from utils.user_utils import resolve_operator


logger = logging.getLogger(__name__)
T = TypeVar("T")


class BatchOperationMixin:
    """
    批量操作通用 Mixin

    【设计原则】
    - 只提取"执行框架"公共逻辑,不涉及具体业务校验
    - 业务校验(如状态检查、关联检查)仍由各 Service 自行实现
    - 支持创建(返回对象)和删除(返回 ID)两种模式
    """

    # DR-1: 常量单一来源(core/constants.py), 保留类属性作为向后兼容的 fallback 入口
    DEFAULT_MAX_BATCH_SIZE = MAX_BATCH_SIZE

    @classmethod
    def batch_execute(
        cls,
        items: list[Any],
        process_fn: Callable[[int, Any], T],
        max_batch_size: int | None = None,
        use_transaction: bool = False,
        item_key: str = "index",
    ) -> dict[str, Any]:
        """
        批量执行通用框架

        【P2-优化】提取所有批量方法的公共循环+异常处理逻辑,减少代码重复。

        Args:
            items: 待处理的条目列表
            process_fn: 单条处理函数,签名 fn(index, item) -> result
                       成功时返回结果对象,失败时抛出 AppValidationError
            max_batch_size: 最大批量大小,默认 100
            use_transaction: 是否为每条记录包裹 transaction.atomic
            item_key: fail_items 中用于标识条目的键名('index' 或 'id')

        Returns:
            Dict[str, Any]: 统一格式的批量操作结果
                {
                    "total": int,
                    "success_count": int,
                    "fail_count": int,
                    "success_items": List[T],
                    "fail_items": List[Dict]
                }

        Raises:
            AppValidationError: 列表长度超过 max_batch_size 时抛出 BATCH_SIZE_EXCEEDED
        """
        max_size = max_batch_size or cls.DEFAULT_MAX_BATCH_SIZE

        if len(items) > max_size:
            raise AppValidationError(detail=f"单次批量操作不能超过 {max_size} 条", error_code="BATCH_SIZE_EXCEEDED")

        success_items: list[T] = []
        fail_items: list[dict[str, Any]] = []

        for idx, item in enumerate(items):
            try:
                if use_transaction:
                    from django.db import transaction

                    with transaction.atomic():
                        result = process_fn(idx, item)
                else:
                    result = process_fn(idx, item)
                success_items.append(result)
            except AppValidationError as e:
                fail_item = {
                    item_key: idx if item_key == "index" else (item.get(item_key) if isinstance(item, dict) else item),
                    "error_code": e.error_code or "VALIDATION_ERROR",
                    "error_message": str(e.detail),
                }
                # 如果 item 是字典,始终记录 row_number 和 input_data(保持与原有行为一致)
                if isinstance(item, dict):
                    fail_item["row_number"] = item.get("row_number")
                    # 【B-8 防御层】validated_data 中 SlugRelatedField 字段是模型实例, 归一化后方可 JSON 序列化
                    fail_item["input_data"] = cls._normalize_input_data(item)
                fail_items.append(fail_item)
            except serializers.ValidationError as e:
                # 【D-1 收敛】process_fn 内执行 serializer.is_valid(raise_exception=True) 时抛出
                # 的 DRF ValidationError, 此前落入 Exception 分支被吞为 INTERNAL_ERROR;
                # 现路由为 VALIDATION_ERROR, 与 AppValidationError 分支同构组装。
                fail_item = {
                    item_key: idx if item_key == "index" else (item.get(item_key) if isinstance(item, dict) else item),
                    "error_code": "VALIDATION_ERROR",
                    "error_message": str(e.detail),
                }
                if isinstance(item, dict):
                    fail_item["row_number"] = item.get("row_number")
                    # 【B-8 防御层】validated_data 中 SlugRelatedField 字段是模型实例, 归一化后方可 JSON 序列化
                    fail_item["input_data"] = cls._normalize_input_data(item)
                fail_items.append(fail_item)
            except Exception as e:
                # 【P1-39 修复】记录异常日志,便于生产环境排查
                logger.error(f"批量操作第 {idx} 条异常: {e}", exc_info=True)
                fail_item = {
                    item_key: idx if item_key == "index" else (item.get(item_key) if isinstance(item, dict) else item),
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误,请稍后重试",
                }
                if isinstance(item, dict):
                    fail_item["row_number"] = item.get("row_number")
                    # 【B-8 防御层】validated_data 中 SlugRelatedField 字段是模型实例, 归一化后方可 JSON 序列化
                    fail_item["input_data"] = cls._normalize_input_data(item)
                fail_items.append(fail_item)

        return {
            "total": len(items),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items,
        }

    @classmethod
    def batch_delete_execute(
        cls,
        ids: list[str],
        process_fn: Callable[[str], None],
        max_batch_size: int | None = None,
    ) -> dict[str, Any]:
        """
        批量删除专用框架

        与 batch_execute 的区别:
        - process_fn 无返回值(None)
        - fail_items 使用 "id" 作为键
        - 默认启用 transaction.atomic 包裹单条删除

        Args:
            ids: 待删除的 ID 列表
            process_fn: 单条删除函数,签名 fn(id) -> None
                       成功时无返回,失败时抛出 AppValidationError
            max_batch_size: 最大批量大小,默认 100

        Returns:
            Dict[str, Any]: 统一格式的批量删除结果
                {
                    "total": int,
                    "success_count": int,
                    "fail_count": int,
                    "success_ids": List[str],
                    "fail_items": List[Dict]
                }
        """
        max_size = max_batch_size or cls.DEFAULT_MAX_BATCH_SIZE

        if len(ids) > max_size:
            raise AppValidationError(detail=f"单次批量删除不能超过 {max_size} 条", error_code="BATCH_SIZE_EXCEEDED")

        success_ids: list[str] = []
        fail_items: list[dict[str, Any]] = []

        for item_id in ids:
            try:
                from django.db import transaction

                with transaction.atomic():
                    process_fn(item_id)
                success_ids.append(item_id)
            except AppValidationError as e:
                fail_items.append(
                    {"id": item_id, "error_code": e.error_code or "VALIDATION_ERROR", "error_message": str(e.detail)}
                )
            except Exception as e:
                # 【P1-39 修复】记录异常日志,便于生产环境排查
                logger.error(f"批量删除第 {item_id} 条异常: {e}", exc_info=True)
                fail_items.append(
                    {"id": item_id, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误,请稍后重试"}
                )

        return {
            "total": len(ids),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items,
        }

    @staticmethod
    def _normalize_input_data(value: Any) -> Any:
        """
        递归归一化失败条目 input_data, 保证 JSON 可序列化(B-8 防御层)

        SlugRelatedField(source=...) 校验后, validated_data 中的关联字段是模型实例,
        原样进入 fail_items 会导致响应渲染抛 TypeError(500)。此处递归处理嵌套
        dict/list, 将模型实例降级为其 pk 字符串(启发式还原), 其余类型原样透传。

        【与 BatchResponseHelper.create_response 的分工】View 层传入 request_items 时,
        input_data 以用户原始输入整条回写(无损还原业务编码); 本方法仅兜底
        未传 request_items 的调用路径(如 employee/department 批量创建), 防止 500。
        """
        if isinstance(value, dict):
            return {key: BatchOperationMixin._normalize_input_data(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [BatchOperationMixin._normalize_input_data(val) for val in value]
        # Django 模型实例必有 pk 属性, 借此判定并降级为 pk 字符串
        if hasattr(value, "pk"):
            return str(value.pk)
        return value


class BatchResponseHelper:
    """
    View 层批量响应组装辅助(DR-1 收敛)

    【契约保护】message 必须由调用方显式传入原格式化文案——
    各接口的 message 是动态文案(如 "批量创建完成,成功 X 条,失败 Y 条"),
    本 Helper 不提供默认兜底, 防止文案漂移破坏前端展示。
    """

    @staticmethod
    def create_response(
        result: dict[str, Any],
        serializer_class: Any,
        message: str,
        request_items: list[dict[str, Any]] | None = None,
    ) -> Response:
        """批量创建: 将 Service 返回的 success_items 对象列表二次序列化后响应

        result 需包含 total/success_count/fail_count/success_items(对象)/fail_items。

        【B-8 修复】request_items: 用户原始提交条目(通常为 serializer.initial_data["items"])。
        提供时, 失败条目的 input_data 以原始输入回写——键名/值与用户提交逐字一致且
        天然 JSON 可序列化。原因: validated_data 中的 SlugRelatedField 字段是模型实例,
        原样进入 fail_items 会导致响应渲染抛 TypeError(500); 而 pk/str 启发式转换又无法
        还原用户提交的业务编码(slug)。按 index 与 request_items 对齐回显是唯一无损方案。
        """
        serialized = serializer_class(result["success_items"], many=True).data
        data = {
            "total": result["total"],
            "success_count": result["success_count"],
            "fail_count": result["fail_count"],
            "success_items": serialized,
            "fail_items": result["fail_items"],
        }
        if request_items is not None:
            for fail_item in data["fail_items"]:
                idx = fail_item.get("index")
                if isinstance(idx, int) and 0 <= idx < len(request_items):
                    fail_item["input_data"] = request_items[idx]
        return success_response(data=data, message=message)

    @staticmethod
    def delete_response(result: dict[str, Any], message: str) -> Response:
        """批量删除: Service 返回 dict 原样透传(success_ids 形态)"""
        return success_response(data=result, message=message)


class BatchDeleteValidationMixin:
    """
    批量删除序列化器通用 validate_ids (DR-1 收敛)

    11 个 BatchDeleteSerializer 拥有完全相同的 validate_ids:
    ① 校验列表长度 ≤ MAX_BATCH_SIZE
    ② 校验 ids 无重复
    本 Mixin 消除该重复, 子类只需声明 MAX_BATCH_SIZE 和 ids 字段即可。
    """

    MAX_BATCH_SIZE: int  # 子类必须声明

    def validate_ids(self, value: list[str]) -> list[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value


class BaseBatchDeleteSerializer(BatchDeleteValidationMixin, serializers.Serializer):  # type: ignore[type-arg]
    """
    批量删除请求序列化器公共基类(DR-1 收敛, A-15 框架代谢)

    MAX_BATCH_SIZE 上限 + ids 长度/去重校验 + 通用 ids 字段收敛于此。
    11 个存量子类仅保留各自带业务语义 help_text 的 ids 字段(OpenAPI 描述零回归)；
    校验行为逐字继承, 子类声明 ids 覆盖即可。
    """

    MAX_BATCH_SIZE = MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    ids = serializers.ListField(child=serializers.CharField(), required=True)


class BatchDeleteViewMixin:
    """
    批量删除视图层公共骨架(DR-1 收敛, 批次③)

    全仓 13 个域的手写 batch_delete action 收敛于此: 序列化器校验 →
    (可选)ids 预筛 → resolve_operator → Service 编排 → delete_response。
    子类仅声明差异类属性:
        batch_delete_serializer          - 批量删除请求序列化器(BaseBatchDeleteSerializer 子类)
        batch_delete_service             - Service 静态/类方法
                                         (默认签名 ids, *, operator_jobcode, operator_name, user)
        batch_delete_passes_operator     - 是否计算并传给 operator(employee/department = False)
        batch_delete_passes_user         - 是否传 user=request.user(damaged/repair/lifecycle/asset = True)

    【差异钩子】
        batch_delete_prefilter(ids, request) - ids 预筛,默认恒等(asset 覆写为部门作用域预筛)
        batch_delete_invoke(ids, **kwargs)   - Service 编排,默认直调 batch_delete_service
                                             (lifecycle 覆写注入 delete_service_method 字符串)
    【契约保护】message 模板与响应键集沿用 BatchResponseHelper.delete_response,
    由 test_b5_baseline_snapshot / test_batch_contract_snapshot 全仓锁定, 改动需先改快照。
    """

    batch_delete_serializer: Any = None
    batch_delete_service: Any = None
    batch_delete_passes_operator = True
    batch_delete_passes_user = False

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request: Any) -> Response:
        """批量删除(全仓统一骨架, 差异仅 serializer/service/operator·user 开关)"""
        serializer = self.batch_delete_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = self.batch_delete_prefilter(serializer.validated_data["ids"], request)
        kwargs: dict[str, Any] = {}
        if self.batch_delete_passes_operator:
            kwargs["operator_jobcode"], kwargs["operator_name"] = resolve_operator(request.user)
        if self.batch_delete_passes_user:
            kwargs["user"] = request.user
        result = self.batch_delete_invoke(ids, **kwargs)
        return BatchResponseHelper.delete_response(
            result,
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    def batch_delete_prefilter(self, ids: list[str], request: Any) -> list[str]:
        """ids 预筛钩子(默认恒等); asset 覆写为部门作用域预筛(RBAC 视图层防线)"""
        return ids

    def batch_delete_invoke(self, ids: list[str], **kwargs: Any) -> dict[str, Any]:
        """Service 编排钩子(默认直调 batch_delete_service); lifecycle 覆写注入 delete_service_method"""
        service: Any = self.batch_delete_service
        if service is None:
            raise TypeError("batch_delete_service 未配置")
        # 类属性存普通函数时, 实例访问会被绑定到 ViewSet(self), 解绑还原 Service 静态方法
        if hasattr(service, "__func__"):
            service = service.__func__
        return cast(dict[str, Any], service(ids, **kwargs))
