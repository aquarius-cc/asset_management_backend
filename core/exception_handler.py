"""
全局异常处理器

统一处理所有未捕获的异常,确保响应格式一致。
"""

import logging
from typing import Any

from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from utils.response_utils import error_response


logger = logging.getLogger(__name__)

# IntegrityError 子类型 → 用户可读消息映射
_INTEGRITY_ERROR_MAP: dict[str, str] = {
    "unique": "数据已存在,请勿重复提交",
    "foreign_key": "关联数据不存在,请检查引用",
    "not_null": "必填字段缺失",
    "check": "数据校验失败",
}


def _parse_integrity_error(exc: IntegrityError) -> str:
    """从 IntegrityError 中提取用户可读消息"""
    msg = str(exc).lower()
    for keyword, user_msg in _INTEGRITY_ERROR_MAP.items():
        if keyword in msg:
            return user_msg
    return "数据完整性冲突,请检查输入"


def custom_exception_handler(exc: Any, context: Any) -> Response:
    """
    自定义全局异常处理器

    1. 先调用 DRF 默认异常处理器
    2. 如果是 DRF 已处理的异常,转换为统一格式返回
    3. 如果是未处理的异常,统一包装为标准格式

    Args:
        exc: 异常对象
        context: 上下文(包含 request, view 等)

    Returns:
        Response: 统一格式的错误响应
    """
    response = exception_handler(exc, context)

    if response is not None:
        # 将 DRF 原生响应转换为统一格式
        data = response.data
        message = "请求失败"

        # 提取错误信息
        if isinstance(data, dict):
            # 单字段错误:{"field": ["error msg"]} 或 {"detail": "error msg"}
            if "detail" in data:
                message = str(data["detail"])
            elif "non_field_errors" in data:
                errors = data["non_field_errors"]
                message = errors[0] if isinstance(errors, list) and errors else str(errors)
            else:
                # 字段级错误,保留原始 data 作为 errors
                message = "参数验证失败"
        elif isinstance(data, list):
            message = data[0] if data else "请求失败"

        return error_response(
            message=message,
            status_code=response.status_code,
            errors=data if isinstance(data, dict) and "detail" not in data and "non_field_errors" not in data else None,
        )

    # 捕获 PermissionError(如 AssetOperationLog 只读保护),返回 403
    # 不返回 str(exc),防止内部实现细节泄露
    if isinstance(exc, PermissionError):
        logger.warning(f"权限错误: {exc}")
        return error_response(message="权限不足,无法执行此操作", status_code=status.HTTP_403_FORBIDDEN)

    # 捕获数据库 IntegrityError(唯一约束/外键/非空),返回 400 + 用户可读消息
    if isinstance(exc, IntegrityError):
        logger.warning(f"数据库完整性冲突: {exc}", exc_info=True)
        return error_response(message=_parse_integrity_error(exc), status_code=status.HTTP_400_BAD_REQUEST)

    # 未处理的异常
    # 【观测性修复】exc_info 常开(原 settings.DEBUG 使生产日志/Sentry 事件丢失堆栈)
    logger.error(f"未处理异常: {type(exc).__name__}: {exc}", exc_info=True)

    return error_response(message="服务器内部错误,请稍后重试", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
