"""write_only 工作簿构建：边迭代边写行，同时累计各列显示宽度。

【write_only 的两个实测约束】
1. ``Workbook(write_only=True)`` **不创建默认工作表**，必须显式
   ``create_sheet()``。
2. write_only 工作簿 **单次可用**：``save()`` 之后其内部临时文件已被
   消费，再次 ``save()`` 抛 ``FileNotFoundError``。故本模块只负责
   "落盘一次"，列宽改写由 :mod:`.widths` 在文件层面完成。

openpyxl 依赖在函数内延迟导入，以保留"缺少 openpyxl 依赖"的优雅降级
路径（与迁移前 Mixin 的行为一致）。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from django.utils import timezone

from .widths import calculate_display_width


__all__ = [
    "DEFAULT_ITER_CHUNK_SIZE",
    "get_nested_value",
    "resolve_cell_value",
    "write_export_workbook",
]

DEFAULT_ITER_CHUNK_SIZE = 1000

_HEADER_FONT_COLOR = "FFFFFF"
_HEADER_FILL_COLOR = "409EFF"


def get_nested_value(obj: Any, field_path: str) -> Any:
    """支持嵌套字段访问，如 ``asset_recordcode__asset_code``。"""
    value = obj
    for part in field_path.split("__"):
        if value is None:
            return None
        value = getattr(value, part, None)
    return value


def coerce_excel_value(value: Any) -> Any:
    """把取值转换为 Excel 可接受的标量。

    Excel 不支持带时区的 datetime——openpyxl 会直接抛
    ``TypeError: Excel does not support timezones in datetimes``。项目
    ``USE_TZ=True``，故所有 DateTimeField 取值都是 aware datetime，
    必须在写入前统一降级为本地时区的 naive 字符串。
    """
    if isinstance(value, datetime) and value.tzinfo is not None:
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")
    return value


def resolve_cell_value(obj: Any, col_config: Mapping[str, Any]) -> Any:
    """按列配置取值，并应用 ``display_map`` 映射；空值统一为 ``""``。"""
    value = get_nested_value(obj, col_config["field"])
    display_map = col_config.get("display_map")
    if display_map and value in display_map:
        value = display_map[value]
    return coerce_excel_value(value) or ""


def _iter_rows(rows: Any, iter_chunk_size: int) -> Iterator[Any]:
    """优先走 ``QuerySet.iterator(chunk_size=...)``；否则退化为普通迭代。

    DRF/Django 要求 prefetch_related 之后必须提供 chunk_size。
    为便于测试，亦兼容仅可迭代对象（如 list）。
    """
    iterator = getattr(rows, "iterator", None)
    if callable(iterator):
        return cast("Iterator[Any]", iterator(chunk_size=iter_chunk_size))
    return iter(rows)


def _write_header(sheet: Any, columns: Sequence[Mapping[str, Any]], new_cell: Any) -> list[Any]:
    """写表头行并返回单元格对象列表，同时返回各列表头宽度。"""
    from openpyxl.styles import Alignment, Font, PatternFill

    font = Font(bold=True, color=_HEADER_FONT_COLOR)
    fill = PatternFill(start_color=_HEADER_FILL_COLOR, end_color=_HEADER_FILL_COLOR, fill_type="solid")
    alignment = Alignment(horizontal="center")

    cells = []
    for col_config in columns:
        cell = new_cell(sheet, col_config["header"])
        cell.font = font
        cell.fill = fill
        cell.alignment = alignment
        cells.append(cell)
    return cells


def _accumulate_widths(widths: dict[int, int], col_idx: int, value: Any) -> None:
    """按显示宽度累计第 ``col_idx`` 列的最大值。"""
    display_width = calculate_display_width(value)
    if display_width > widths.get(col_idx, 0):
        widths[col_idx] = display_width


def write_export_workbook(
    *,
    target_path: Path,
    rows: Any,
    columns: Sequence[Mapping[str, Any]],
    sheet_name: str,
    iter_chunk_size: int = DEFAULT_ITER_CHUNK_SIZE,
) -> dict[int, int]:
    """把 ``rows`` 流式写入 ``target_path``，返回 {列序号: 实测最大显示宽度}。

    Args:
        target_path: 输出 xlsx 路径（openpyxl 只允许 save 一次）。
        rows: 提供 ``iterator(chunk_size=...)`` 的 queryset，或可迭代对象。
        columns: 列配置序列，每项含 ``header``/``field``，可选 ``display_map``。
        sheet_name: 工作表名。
        iter_chunk_size: ``iterator`` 的分块大小。

    Returns:
        各列实测最大显示宽度，供 :func:`~.widths.apply_column_widths` 注入。
    """
    import openpyxl
    from openpyxl.cell import WriteOnlyCell

    def new_cell(sheet: Any, value: Any) -> Any:
        return WriteOnlyCell(sheet, value=value)

    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet(title=sheet_name)

    widths: dict[int, int] = {}
    for col_idx, col_config in enumerate(columns, 1):
        _accumulate_widths(widths, col_idx, col_config["header"])
    sheet.append(_write_header(sheet, columns, new_cell))

    for obj in _iter_rows(rows, iter_chunk_size):
        cells = []
        for col_idx, col_config in enumerate(columns, 1):
            value = resolve_cell_value(obj, col_config)
            _accumulate_widths(widths, col_idx, value)
            cells.append(new_cell(sheet, value))
        sheet.append(cells)

    workbook.save(target_path)
    return widths
