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

    @extend_schema(
        summary="导出当前列表数据为 Excel",
        parameters=EXPORT_PAGINATION_PARAMETERS,
        responses=XLSX_EXPORT_RESPONSES,
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_excel(self, request: Any) -> HttpResponseBase | Response:
        """导出当前列表数据为 Excel。

        可见性由 ``self.get_queryset()`` 决定，与列表接口完全一致——
        导出不会放大列表接口的可见范围（此不变量由各 app 的导出测试锁定）。

        支持 ``?limit=`` / ``?offset=`` 分批导出；缺省为全量，仍受
        ``EXPORT_MAX_ROWS`` 兜底保护。
        """
        try:
            return build_excel_export_response(
                rows=self.get_queryset(),  # type: ignore[attr-defined]
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
