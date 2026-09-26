"""Excel 导出的资源守卫、limit/offset 语义与流式响应编排。

【临时目录生命周期】
``FileResponse`` 惰性读取文件，响应体在 ``build_excel_export_response``
返回之后才被消费，故临时目录**不能**用 ``with`` 上下文管理（会在返回
前删除文件）。改由 :class:`StreamingExcelResponse.close()` 清理——
Django 的 WSGI/ASGI 处理器与 test client 均会在响应消费完毕后调用
``close()``。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import FileResponse

from .widths import apply_column_widths
from .workbook import DEFAULT_ITER_CHUNK_SIZE, write_export_workbook


__all__ = [
    "DEFAULT_EXPORT_MAX_ROWS",
    "XLSX_CONTENT_TYPE",
    "ExportPaginationError",
    "ExportTooLargeError",
    "MissingColumnsError",
    "StreamingExcelResponse",
    "build_excel_export_response",
    "parse_export_bounds",
    "resolve_max_rows",
]

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEFAULT_EXPORT_MAX_ROWS = 10000

HEADER_EXPORT_MAX_ROWS = "X-Export-Max-Rows"
HEADER_EXPORT_TOTAL_COUNT = "X-Export-Total-Count"


class MissingColumnsError(ValueError):
    """未配置导出列。"""


class ExportTooLargeError(Exception):
    """导出总行数超过 ``EXPORT_MAX_ROWS`` 安全上限。"""

    def __init__(self, total: int, max_rows: int) -> None:
        self.total = total
        self.max_rows = max_rows
        super().__init__(self.message)

    @property
    def message(self) -> str:
        return f"导出数据量({self.total})超过上限{self.max_rows}，请缩小筛选范围"


class ExportPaginationError(ValueError):
    """导出用 ``limit``/``offset`` 参数非法。"""

    @property
    def message(self) -> str:
        return str(self)


class StreamingExcelResponse(FileResponse):
    """在响应关闭时清理临时目录的 xlsx 响应。

    文件句柄无需在此处理：Django 的 ``FileResponse._set_streaming_content``
    已把 ``filelike.close`` 注册进 ``_resource_closers``，``super().close()``
    会先释放句柄（本类在 ``super().close()`` **之后**才删目录），因此
    Windows 上也不会出现"文件被占用导致删除失败"。
    """

    def __init__(self, *args: Any, temp_dir: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._temp_dir = temp_dir

    def close(self) -> None:
        try:
            super().close()
        finally:
            shutil.rmtree(self._temp_dir, ignore_errors=True)


def resolve_max_rows() -> int:
    """读取当前生效的导出行数上限（每次调用时读取，以支持 override_settings）。"""
    return int(getattr(settings, "EXPORT_MAX_ROWS", DEFAULT_EXPORT_MAX_ROWS))


def _parse_bound(raw: Any, name: str, minimum: int) -> int | None:
    """解析单个非负整数参数；``None``/空串视为未提供。"""
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ExportPaginationError(f"参数 {name} 必须为整数") from exc
    if value < minimum:
        raise ExportPaginationError(f"参数 {name} 必须大于等于 {minimum}")
    return value


def parse_export_bounds(params: Mapping[str, Any], max_rows: int) -> tuple[int | None, int | None]:
    """解析导出用 ``limit``/``offset``，返回 ``(limit, offset)``。

    语义：

    - 两者均缺省 -> ``(None, None)``，表示全量导出，仍受
      ``EXPORT_MAX_ROWS`` 总量守卫（超限抛 :class:`ExportTooLargeError`）。
    - 任一提供 -> 调用方显式限流/分批，跳过总量拒绝；``limit`` 仍钳制到
      ``max_rows``，保证单次导出不会突破安全上限。

    Raises:
        ExportPaginationError: 参数非整数或小于下限。
    """
    limit = _parse_bound(params.get("limit"), "limit", minimum=1)
    offset = _parse_bound(params.get("offset"), "offset", minimum=0)
    if limit is None and offset is None:
        return None, None
    if limit is not None and limit > max_rows:
        limit = max_rows
    return limit, offset


def apply_export_bounds(rows: Any, limit: int | None, offset: int | None) -> Any:
    """对 queryset 施加 limit/offset（保持惰性，不物化）。"""
    if limit is None and offset is None:
        return rows
    bounded = rows[offset:] if offset else rows
    return bounded[:limit] if limit else bounded


def build_excel_export_response(
    *,
    rows: Any,
    columns: Sequence[Mapping[str, Any]],
    filename: str,
    sheet_name: str,
    limit: int | None = None,
    offset: int | None = None,
    params: Mapping[str, Any] | None = None,
    iter_chunk_size: int = DEFAULT_ITER_CHUNK_SIZE,
) -> StreamingExcelResponse:
    """构建流式 xlsx 下载响应。

    流程：资源守卫 -> write_only 落盘 -> zip XML 注入列宽 -> 流式发送。

    Args:
        params: 若提供（通常是 ``request.query_params``），则由本函数统一
            解析 ``limit``/``offset``，并**覆盖**显式传入的 limit/offset。
            这样 Mixin 与各 APIView 共用同一套分批语义（DR-1）。

    Raises:
        MissingColumnsError: ``columns`` 为空。
        ExportPaginationError: ``limit``/``offset`` 非法。
        ExportTooLargeError: 全量导出且总行数超过 ``EXPORT_MAX_ROWS``。
    """
    if not columns:
        raise MissingColumnsError("未配置导出列")

    max_rows = resolve_max_rows()
    if params is not None:
        limit, offset = parse_export_bounds(params, max_rows)
    bounded = apply_export_bounds(rows, limit, offset)
    throttled = limit is not None or offset is not None

    total = bounded.count()
    if not throttled and total > max_rows:
        raise ExportTooLargeError(total, max_rows)

    temp_dir = tempfile.mkdtemp(prefix="excel_export_")
    try:
        raw_path = Path(temp_dir) / "raw.xlsx"
        final_path = Path(temp_dir) / "export.xlsx"
        widths = write_export_workbook(
            target_path=raw_path,
            rows=bounded,
            columns=columns,
            sheet_name=sheet_name,
            iter_chunk_size=iter_chunk_size,
        )
        apply_column_widths(raw_path, final_path, widths)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    response = StreamingExcelResponse(
        final_path.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=XLSX_CONTENT_TYPE,
        temp_dir=temp_dir,
    )
    response[HEADER_EXPORT_MAX_ROWS] = str(max_rows)
    response[HEADER_EXPORT_TOTAL_COUNT] = str(total)
    return response
