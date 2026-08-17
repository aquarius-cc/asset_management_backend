# d:\CodeDemo\Python\asset_management_backend\utils\response_utils.py
"""
统一响应格式工具

提供符合 AGENTS.md 规范的统一响应格式:
{"code": 0, "message": "", "data": {}}

成功 code=0(AGENTS.md §3 跨端契约),错误 code=HTTP 状态码。
"""

from typing import Any

from rest_framework import status
from rest_framework.response import Response


class BusinessCode:
    """响应码常量"""

    SUCCESS = 0


def success_response(
    data: Any = None, message: str = "操作成功", status_code: int = status.HTTP_200_OK
) -> Response:
    """
    成功响应 - 统一返回格式 {"code": 0, "message": "", "data": {}}

    成功时 code=0(AGENTS.md §3 跨端契约)
    """
    response_data = {
        "code": BusinessCode.SUCCESS,
        "message": message,
        "data": data if data is not None else {},
    }
    return Response(response_data, status=status_code)


def error_response(
    message: str = "操作失败",
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    错误响应 - 统一返回格式 {"code": HTTP状态码, "message": "", "data": {}}

    错误时 code=HTTP 状态码
    """
    response_data: dict[str, Any] = {
        "code": status_code,
        "message": message,
        "data": errors if errors is not None else {},
    }

    return Response(response_data, status=status_code)
