
"""
自定义分页类

功能：
- 有 page/page_size 参数时启用分页
- 无参数时返回全部数据
- 所有分页响应均通过 success_response 包装，确保统一格式
"""

# from rest_framework.utils.urls import replace_query_param

from rest_framework.pagination import PageNumberPagination

from core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from utils.response_utils import success_response


class CustomPageNumberPagination(PageNumberPagination):
    """
    自定义分页类：
    - 有 page/page_size 参数时：启用分页
    特性：
    - 默认每页 20 条
    - 前端可通过 page_size 参数自定义（最大 100，与 constants.py 保持一致）
    - 无分页参数时返回全部数据（不分页）

    【修复 H8】使用 constants.py 中的常量，确保配置一致性
    """
    # 【修复 H8】使用 constants.py 中的常量
    page_size = DEFAULT_PAGE_SIZE  # 默认每页数量
    page_size_query_param = 'page_size'  # 前端传参名
    max_page_size = MAX_PAGE_SIZE  # 安全上限，与 constants.py 保持一致
    page_query_param = 'page'  # 页码参数名（默认即为'page'，显式声明更清晰）
    # last_page_strings = ('last',)  # 最后一页参数名（默认即为'last'，显式声明更清晰）

    def paginate_queryset(
        self, queryset, request, view=None
    ) -> object | None:
        """
        根据请求参数决定是否分页

        Returns:
            - 如果有分页参数 → 返回当前页的查询集
            - 如果无分页参数 → 返回第一页（强制分页，防止大数据量内存溢出）
        """
        # 【修复】无分页参数时默认返回第一页，而非全部数据
        # 防止大数据量下内存溢出和响应超时
        page_param = request.query_params.get(self.page_query_param)
        page_size_param = request.query_params.get(self.page_size_query_param)

        # 【P2-28 修复】使用 DRF 的 replace_query_param 替代直接修改 _request.GET
        # 避免依赖 Django 内部实现，兼容 ASGI/异步视图
        if not page_param and not page_size_param:
            from rest_framework.utils.urls import replace_query_param
            request._full_path = replace_query_param(
                request._request.get_full_path(), self.page_query_param, '1'
            )

        # 执行分页逻辑
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        """
        返回统一格式的分页响应

        响应格式：
        {
            "code": 0,
            "message": "查询成功",
            "data": {
                "count": 100,           # 总记录数
                "total_pages": 5,       # 总页数
                "page": 1,              # 当前页码
                "page_size": 20,        # 每页大小
                "next": "http://...",   # 下一页链接
                "previous": null,       # 上一页链接
                "results": [...]        # 当前页数据
            }
        }
        """
        return success_response(
            data={
            'count': self.page.paginator.count,  # 总记录数
            'total_pages': self.page.paginator.num_pages,  # 总页数（使用 num_pages 属性）
            'page': self.page.number,  # 当前页码
            'page_size': self.get_page_size(self.request),  # 每页大小
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        },
        message='查询成功'
    )

    def get_paginated_response_schema(self, schema):
        """生成 OpenAPI 文档中的分页响应 schema"""
        return {
            'type': 'object',
            'properties': {
                'code': {'type': 'integer', 'example': 0},
                'message': {'type': 'string', 'example': '查询成功'},
                'data': {
                    'type': 'object',
                    'properties': {
                        'count': {'type': 'integer', 'example': 100},
                        'total_pages': {'type': 'integer', 'example': 5},
                        'page': {'type': 'integer', 'example': 1},
                        'page_size': {'type': 'integer', 'example': 20},
                        'next': {
                            'type': 'string',
                            'nullable': True,
                            'example': 'http://api.example.com/users/?page=2&page_size=20'
                        },
                        'previous': {
                            'type': 'string',
                            'nullable': True,
                            'example': None
                        },
                        'results': schema,
                    }
                }
            },
        }
    # def get_paginated_response(self, data):
    #     """返回包含总页数的分页响应"""
    #     return Response({
    #         'count': self.page.paginator.count,  # 总记录数
    #         'total_pages': self.page.paginator.num_pages,  # 👈 总页数
    #         'page': self.page.number,  # 👈 当前页码
    #         'page_size': self.get_page_size(self.request),  # 👈 每页大小
    #         'next': self.get_next_link(),
    #         'previous': self.get_previous_link(),
    #         'results': data
    #     })

    # def get_next_link(self):
    #     if not self.page.has_next():
    #         return None
    #     url = self.request.build_absolute_uri()
    #     page_number = self.page.next_page_number()
    #     return replace_query_param(url, self.page_query_param, page_number)

    # def get_previous_link(self):
    #     if not self.page.has_previous():
    #         return None
    #     url = self.request.build_absolute_uri()
    #     page_number = self.page.previous_page_number()
    #     return replace_query_param(url, self.page_query_param, page_number)
