# d:\CodeDemo\Python\asset_management_backend\utils\response_utils.py
"""
统一响应格式工具

提供符合 AGENTS.md 规范的统一响应格式：
{"code": 业务码, "msg": "", "data": {}}

【修复 H7】code 字段使用独立的业务错误码，与 HTTP 状态码解耦
"""

from rest_framework.response import Response
from rest_framework import status
from typing import Any, Optional, Dict
from django.conf import settings


# 【修复 H7】定义业务错误码常量
class BusinessCode:
    """业务响应码"""
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500


def success_response(
    data: Any = None,
    message: str = '操作成功',
    status_code: int = status.HTTP_200_OK,
    business_code: Optional[int] = None
) -> Response:
    """
    成功响应 - 统一返回格式 {"code": 业务码, "msg": "", "data": {}}

    【修复 H7】添加 business_code 参数，与 HTTP 状态码解耦

    Args:
        data: 响应数据，可为任意类型，None时返回空字典
        message: 成功消息，默认为"操作成功"
        status_code: HTTP状态码，默认为200
        business_code: 业务码，可选，默认200

    Returns:
        Response: 符合规范的成功响应对象
    """
    response_data = {
        # 【修复 H7】使用 business_code 或默认值
        'code': business_code if business_code is not None else BusinessCode.SUCCESS,
        'msg': message,
        'data': data if data is not None else {}
    }
    return Response(response_data, status=status_code)


def error_response(
    message: str = '操作失败',
    business_code: Optional[int] = None,
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST
) -> Response:
    """
    错误响应 - 统一返回格式 {"code": 业务码, "msg": "", "data": {}}

    【修复 H6】生产环境不返回详细错误信息
    【修复 H7】business_code 与 HTTP 状态码解耦

    Args:
        message: 错误消息，默认为"操作失败"
        business_code: 业务错误码，可选
        errors: 详细错误信息，可选，仅在 DEBUG 模式返回
        status_code: HTTP状态码，默认为400

    Returns:
        Response: 符合规范的错误响应对象
    """
    # 【修复 H7】映射 HTTP 状态码到业务码（如果未指定）
    if business_code is None:
        business_code_map = {
            status.HTTP_400_BAD_REQUEST: BusinessCode.BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED: BusinessCode.UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN: BusinessCode.FORBIDDEN,
            status.HTTP_404_NOT_FOUND: BusinessCode.NOT_FOUND,
            status.HTTP_500_INTERNAL_SERVER_ERROR: BusinessCode.INTERNAL_ERROR,
        }
        business_code = business_code_map.get(status_code, BusinessCode.BAD_REQUEST)

    response_data: Dict[str, Any] = {
        'code': business_code,
        'msg': message,
        'data': {}
    }

    # 【修复 H6】仅在 DEBUG 模式返回详细错误信息
    if errors is not None and settings.DEBUG:
        response_data['errors'] = errors

    return Response(response_data, status=status_code)


def paginated_response(
    queryset,
    serializer,
    request,
    page_size: int = 20
) -> Response:
    """
    分页响应 - 返回包含分页信息的统一格式

    Args:
        queryset: 查询集
        serializer: 序列化器
        request: 请求对象
        page_size: 每页数量，默认为20

    Returns:
        Response: 包含分页信息的成功响应
    """
    from rest_framework.pagination import PageNumberPagination

    paginator = PageNumberPagination()
    paginator.page_size = page_size
    page_items = paginator.paginate_queryset(queryset, request)
    serialized = serializer(page_items, many=True)

    paginated_data = paginator.get_paginated_response(serialized.data).data

    return success_response(
        data={
            'count': paginated_data['count'],
            'next': paginated_data['next'],
            'previous': paginated_data['previous'],
            'results': paginated_data['results']
        }
    )


"""
最终返回的结果
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "count": 总数量,
    "next": 下一页URL或null,
    "previous": 上一页URL或null,
    "results": [ ... 对象列表 ... ]
  }
}
code：业务码，与 HTTP 状态码解耦
msg：固定 "操作成功"（分页接口默认消息）
data：分页信息对象
    count：数据总条数（满足查询条件的全部记录数）
    next：下一页的完整 URL，若当前为最后一页则为 null
    previous：上一页的完整 URL，若当前为第一页则为 null
    results：当前页的数据列表，每个元素都是经过序列化后的对象
"""
