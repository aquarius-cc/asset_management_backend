# d:\CodeDemo\Python\asset_management_backend\utils\response_utils.py
"""
统一响应格式工具

提供符合 AGENTS.md 规范的统一响应格式:
{"code": 业务码, "message": "", "data": {}}

【修复 P0-3】code 字段使用独立的业务错误码,与 HTTP 状态码解耦
成功 code=0(AGENTS.md §3 跨端契约),错误 code=业务错误码
"""

from typing import Any

from rest_framework import status
from rest_framework.response import Response


# 【修复 P0-3】定义业务错误码常量(AGENTS.md §3 契约 + 规范 1xxx/2xxx/3xxx/4xxx 体系)
class BusinessCode:
    """业务响应码(遵循 AGENTS.md 跨端契约)"""

    SUCCESS = 0
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_ERROR = 500

    # 规范定义的业务错误码体系
    INVALID_TRANSITION = 1001  # 非法状态转换
    RESOURCE_CONFLICT = 1002  # 并发冲突
    ASSET_NOT_FOUND = 1003  # 资产不存在
    PERMISSION_DENIED = 3001  # 无操作权限
    BUSINESS_LOGIC_ERROR = 4001  # 业务规则违反


def success_response(
    data: Any = None, message: str = "操作成功", status_code: int = status.HTTP_200_OK, business_code: int | None = None
) -> Response:
    """
    成功响应 - 统一返回格式 {"code": 0, "message": "", "data": {}}

    【修复 P0-3】成功时 code=0(AGENTS.md §3 跨端契约),字段名 message
    """
    response_data = {
        "code": business_code if business_code is not None else BusinessCode.SUCCESS,
        "message": message,
        "data": data if data is not None else {},
    }
    return Response(response_data, status=status_code)


def error_response(
    message: str = "操作失败",
    business_code: int | None = None,
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    错误响应 - 统一返回格式 {"code": 业务码, "message": "", "data": {}}

    【修复 P0-3】字段名 message,成功时 code=0
    """
    if business_code is None:
        business_code_map = {
            status.HTTP_400_BAD_REQUEST: BusinessCode.BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED: BusinessCode.UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN: BusinessCode.FORBIDDEN,
            status.HTTP_404_NOT_FOUND: BusinessCode.NOT_FOUND,
            status.HTTP_409_CONFLICT: BusinessCode.CONFLICT,
            status.HTTP_500_INTERNAL_SERVER_ERROR: BusinessCode.INTERNAL_ERROR,
        }
        business_code = business_code_map.get(status_code, BusinessCode.BAD_REQUEST)

    response_data: dict[str, Any] = {
        "code": business_code,
        "message": message,
        "data": errors if errors is not None else {},
    }

    return Response(response_data, status=status_code)
