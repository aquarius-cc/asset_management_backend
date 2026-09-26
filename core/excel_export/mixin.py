"""Excel 导出 Mixin（跨 app 公共能力）。

【为何从 ``apps/assetmanagement/views/_export_mixin.py`` 迁出】
``EmployeeViewSet`` 位于 ``apps/usermanagement``，直接 import
assetmanagement 的 Mixin 会制造跨 app 依赖。故与内核同置于
``core/excel_export/``（DR-4 工具单一仓库），assetmanagement 侧 7 个
ViewSet 仅改 1 行 import，行为由既有 ``test_export_excel`` /
``test_export_excel_rbac`` 回归保护。

导出 URL: ``/api/v1/{basename}/export/``
权限: 经类级 ``get_permissions`` -> ``resolve_viewset_permissions`` ->
``CanExportExcel``（矩阵 :148）。
"""

from __future__ import annotations

from typing import Any

from django.http import HttpResponseBase
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from utils.response_utils import error_response

from .schema import EXPORT_PAGINATION_PARAMETERS, XLSX_EXPORT_RESPONSES
from .streaming import (
    ExportPaginationError,
    ExportTooLargeError,
    MissingColumnsError,
    build_excel_export_response,
)
from .workbook import DEFAULT_ITER_CHUNK_SIZE


__all__ = ["ExportExcelMixin"]


class ExportExcelMixin:
    """Excel 导出 Mixin。

    子类定义 export_columns 配置:
    ```python
    export_columns = [
        {"header": "资产编码", "field": "asset_code"},
        {"header": "当前状态", "field": "asset_current_status", "display_map": ASSET_STATUS_MAP},
    ]
    ```
    """

    export_columns: list[dict[str, Any]] = []
    export_filename: str = "export.xlsx"
    export_sheet_name: str = "数据导出"

    # DRF: QuerySet.iterator() 在 prefetch_related 后必须提供 chunk_size
    _EXPORT_ITER_CHUNK_SIZE = DEFAULT_ITER_CHUNK_SIZE

    def get_export_queryset(self) -> Any:
        """导出取行口径钩子（默认与列表同源）。

        【不变量】导出行集合 = ``self.get_queryset()``，故导出不会放大
        列表接口的可见范围（各 app 的导出测试锁定此性质）。

        子类若列表口径与 ``get_queryset()`` 不同（如 ``EmployeeViewSet``
        的列表走 ``search_employees`` 语义），覆写本方法对齐自身列表口径，
        **不得**直接改本方法的默认实现——11 个导出端点的默认行为由此保持
        字节级不变（DR-1）。
        """
        return self.get_queryset()  # type: ignore[attr-defined]

    @extend_schema(
        summary="导出当前列表数据为 Excel",
        parameters=EXPORT_PAGINATION_PARAMETERS,
        responses=XLSX_EXPORT_RESPONSES,
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_excel(self, request: Any) -> HttpResponseBase | Response:
        """导出当前列表数据为 Excel。

        取行口径由 ``self.get_export_queryset()`` 决定，默认与列表接口
        完全一致；子类可覆写该钩子以对齐自身的列表口径。

        支持 ``?limit=`` / ``?offset=`` 分批导出；缺省为全量，仍受
        ``EXPORT_MAX_ROWS`` 兜底保护。
        """
        try:
            return build_excel_export_response(
                rows=self.get_export_queryset(),
                columns=self.export_columns,
                filename=self.export_filename,
                sheet_name=self.export_sheet_name,
                params=getattr(request, "query_params", None),
                iter_chunk_size=self._EXPORT_ITER_CHUNK_SIZE,
            )
        except MissingColumnsError:
            return error_response(message="未配置导出列", status_code=500)
        except (ExportPaginationError, ExportTooLargeError) as exc:
            return error_response(message=exc.message, status_code=400)
        except ImportError:
            return error_response(message="缺少 openpyxl 依赖", status_code=500)
