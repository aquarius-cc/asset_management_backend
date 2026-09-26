"""导出端点的 OpenAPI 复用片段。

【为什么需要本模块】
``ExportExcelMixin.export_excel`` 是全部 11 个导出端点（10 个资产类 +
员工）的唯一实现，故 schema 声明必须挂在 Mixin 上，否则每个 ViewSet 都要
复制一份 ``@extend_schema``（DR-1 违反）。操作日志端点不走 Mixin（在
APIView 中自行编排 queryset），因此把可复用片段抽到本模块，两侧共用。

【关于 200 响应 media type】
drf-spectacular 0.29 的 ``responses`` 字典中，tuple 键 ``(code, media_type)``
表示"该 media type 的响应"，其值按 **schema** 解析；直接传
``OpenApiResponse(content=...)`` 会被当作 schema 而报
``SchemaValidationError``。故此处写字面 schema 字典。
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse

from .streaming import XLSX_CONTENT_TYPE


__all__ = [
    "EXPORT_PAGINATION_PARAMETERS",
    "XLSX_EXPORT_RESPONSES",
]

#: xlsx 二进制体。客户端须按二进制下载，不可当 JSON 解析。
XLSX_BINARY_SCHEMA: dict[str, str] = {"type": "string", "format": "binary"}

#: 分批导出参数。两个均缺省表示全量，仍受 ``EXPORT_MAX_ROWS`` 总量守卫。
EXPORT_PAGINATION_PARAMETERS = [
    OpenApiParameter(
        name="limit",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="单批条数上限(缺省为全量)",
        required=False,
    ),
    OpenApiParameter(
        name="offset",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="跳过前 N 条(缺省为全量)",
        required=False,
    ),
]

#: 导出端点的标准响应集合：二进制 200 + 参数错误 400 + 无权限 403。
XLSX_EXPORT_RESPONSES = {
    (200, XLSX_CONTENT_TYPE): XLSX_BINARY_SCHEMA,
    400: OpenApiResponse(description="参数错误或超出导出行数上限"),
    403: OpenApiResponse(description="无导出权限"),
}
