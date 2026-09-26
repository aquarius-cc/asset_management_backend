"""Excel 导出公共内核。

模块职责（DR-4 工具单一仓库）：

- :mod:`.widths`   —— 列宽计算 + xlsx XML ``<cols>`` 注入
- :mod:`.workbook` —— write_only 工作簿构建（边迭代边写行）
- :mod:`.streaming`—— 资源守卫、limit/offset 语义、流式响应编排
- :mod:`.mixin`    —— 供 ViewSet 复用的 ``ExportExcelMixin``

【为什么需要 write_only + XML 改写】
``QuerySet.iterator()`` 只能让数据库侧流式，openpyxl 普通工作簿仍会把
全部单元格驻留在内存对象图中，超大导出易 OOM。``write_only=True`` 把行
直接刷进内部临时文件，但该模式无法设置列宽，故由 :mod:`.widths` 在文件
层面补齐。
"""

from .mixin import ExportExcelMixin
from .schema import EXPORT_PAGINATION_PARAMETERS, XLSX_EXPORT_RESPONSES
from .streaming import (
    DEFAULT_EXPORT_MAX_ROWS,
    HEADER_EXPORT_MAX_ROWS,
    HEADER_EXPORT_TOTAL_COUNT,
    XLSX_CONTENT_TYPE,
    ExportPaginationError,
    ExportTooLargeError,
    MissingColumnsError,
    StreamingExcelResponse,
    build_excel_export_response,
    parse_export_bounds,
    resolve_max_rows,
)
from .widths import (
    COLUMN_PADDING,
    MAX_COLUMN_WIDTH,
    apply_column_widths,
    build_cols_xml,
    calculate_display_width,
    resolve_worksheet_part,
)
from .workbook import DEFAULT_ITER_CHUNK_SIZE, write_export_workbook


__all__ = [
    "COLUMN_PADDING",
    "DEFAULT_EXPORT_MAX_ROWS",
    "DEFAULT_ITER_CHUNK_SIZE",
    "EXPORT_PAGINATION_PARAMETERS",
    "HEADER_EXPORT_MAX_ROWS",
    "HEADER_EXPORT_TOTAL_COUNT",
    "MAX_COLUMN_WIDTH",
    "XLSX_CONTENT_TYPE",
    "XLSX_EXPORT_RESPONSES",
    "ExportExcelMixin",
    "ExportPaginationError",
    "ExportTooLargeError",
    "MissingColumnsError",
    "StreamingExcelResponse",
    "apply_column_widths",
    "build_cols_xml",
    "build_excel_export_response",
    "calculate_display_width",
    "parse_export_bounds",
    "resolve_max_rows",
    "resolve_worksheet_part",
    "write_export_workbook",
]
