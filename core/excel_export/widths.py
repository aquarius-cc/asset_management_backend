"""xlsx 列宽计算与工作表 XML ``<cols>`` 注入。

【为什么必须手工改写 XML】
openpyxl 3.1.5 的 ``WriteOnlyWorksheet`` 不暴露 ``column_dimensions`` /
``set_column_width``，其写出的工作表 XML 中不含 ``<cols>``（均已实测）。
故真流式导出无法使用 openpyxl 原生 API 设置列宽，只能在文件落盘后
改写 zip 内的工作表 XML。

【内存代价（如实说明，勿夸大）】
改写时 ``ZipFile.read(item)`` 会把单个 XML 部件整体读入内存，峰值内存
约等于最大的 XML 部件体积。相较"完整 Workbook 对象图 + BytesIO"仍是
数量级下降，但并非零内存。

【Excel 列宽单位】
Excel 的 ``width`` 以默认字体 0 号字符宽度为单位。全角字符约占 2 个
单位，故 :func:`calculate_display_width` 对 East Asian Wide/Fullwidth
字符记 2，其余记 1。
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


__all__ = [
    "COLUMN_PADDING",
    "MAX_COLUMN_WIDTH",
    "apply_column_widths",
    "build_cols_xml",
    "calculate_display_width",
    "resolve_worksheet_part",
]

MAX_COLUMN_WIDTH = 60
COLUMN_PADDING = 2

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_SHEET_DATA_RE = re.compile(r"<sheetData(\s[^>]*)?>")


def _char_width(char: str) -> int:
    """单字符显示宽度：East Asian Wide/Fullwidth 记 2，其余记 1。"""
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def calculate_display_width(value: Any) -> int:
    """按显示宽度计算字符串长度（全角记 2，None 记 0）。"""
    text = "" if value is None else str(value)
    return sum(_char_width(char) for char in text)


def build_cols_xml(widths: Mapping[int, int]) -> str:
    """由 {列序号: 实测最大显示宽度} 生成 ``<cols>`` 片段。

    宽度统一加 :data:`COLUMN_PADDING` 留白，并钳制在
    :data:`MAX_COLUMN_WIDTH` 以内。
    """
    if not widths:
        return ""
    parts = ["<cols>"]
    for col_idx in sorted(widths):
        width = min(widths[col_idx] + COLUMN_PADDING, MAX_COLUMN_WIDTH)
        parts.append(f'<col min="{col_idx}" max="{col_idx}" width="{width}" customWidth="1"/>')
    parts.append("</cols>")
    return "".join(parts)


def resolve_worksheet_part(archive: zipfile.ZipFile) -> str:
    """解析工作簿首个工作表在 zip 内的实际 part 名（不硬编码 sheet1.xml）。

    路径：``xl/workbook.xml`` 取 ``<sheet>`` 的 ``r:id`` → 在
    ``xl/_rels/workbook.xml.rels`` 中查得 ``Target``。

    Raises:
        ValueError: 缺少 workbook.xml / 关系文件 / ``<sheet>`` / ``r:id``，
            或关系文件中无对应条目。
    """
    try:
        workbook_xml = archive.read("xl/workbook.xml")
        rels_xml = archive.read("xl/_rels/workbook.xml.rels")
    except KeyError as exc:
        raise ValueError("xlsx 缺少 xl/workbook.xml 或 xl/_rels/workbook.xml.rels") from exc

    workbook_root = ElementTree.fromstring(workbook_xml)
    sheets_elem = workbook_root.find(f"{{{_MAIN_NS}}}sheets")
    sheet_elem = None if sheets_elem is None else sheets_elem.find(f"{{{_MAIN_NS}}}sheet")
    if sheet_elem is None:
        raise ValueError("xlsx 的 xl/workbook.xml 中未找到 <sheet>")

    rel_id = sheet_elem.get(f"{{{_REL_NS}}}id")
    if not rel_id:
        raise ValueError("xlsx 的 <sheet> 缺少 r:id 属性")

    target = _lookup_relationship_target(rels_xml, rel_id)
    if target is None:
        raise ValueError(f"xlsx 关系文件中未找到 {rel_id} 对应的 Target")
    return target


def _lookup_relationship_target(rels_xml: bytes, rel_id: str) -> str | None:
    """在 workbook.xml.rels 中按 Id 查 Target，归一化为 zip 内绝对路径。"""
    rels_root = ElementTree.fromstring(rels_xml)
    for rel in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        if rel.get("Id") != rel_id:
            continue
        target = (rel.get("Target") or "").strip()
        if not target:
            return None
        if target.startswith("/"):
            return target.lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    return None


def _inject_cols(sheet_xml: bytes, cols_xml: str) -> bytes:
    """在工作表 XML 的 ``<sheetData>`` 之前插入 ``<cols>``。

    已有 ``<cols>`` 时保持原样（openpyxl write_only 不会产出，此分支
    仅为防御性保留，避免重复注入产生非法 XML）。
    """
    text = sheet_xml.decode("utf-8")
    if "<cols" in text:
        return sheet_xml
    match = _SHEET_DATA_RE.search(text)
    if match is None:
        return sheet_xml
    return (text[: match.start()] + cols_xml + text[match.start() :]).encode("utf-8")


def apply_column_widths(source: Path, target: Path, widths: Mapping[int, int]) -> None:
    """把 ``source`` xlsx 的列宽注入后另存为 ``target``。

    ``widths`` 为空时直接复制字节（无需改写 XML）。
    """
    cols_xml = build_cols_xml(widths)
    if not cols_xml:
        target.write_bytes(source.read_bytes())
        return

    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        worksheet_part = resolve_worksheet_part(src)
        for item in src.infolist():
            payload = src.read(item.filename)
            if item.filename == worksheet_part:
                payload = _inject_cols(payload, cols_xml)
            dst.writestr(item, payload)
