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
from typing import Any, TypeVar

from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError
from utils.response_utils import success_response


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
                    fail_item["input_data"] = item
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
                    fail_item["input_data"] = item
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
    ) -> Any:
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
    def delete_response(result: dict[str, Any], message: str) -> Any:
        """批量删除: Service 返回 dict 原样透传(success_ids 形态)"""
        return success_response(data=result, message=message)
