"""
导出 Excel Mixin 单元测试(#40 EXPORT_MAX_ROWS 资源防护)

覆盖:
1. 超限:total > EXPORT_MAX_ROWS → 400 + 上限文案
2. 正常:total ≤ 上限 → 200 + xlsx MIME
3. 边界:total == 上限 → 允许导出
"""

from types import SimpleNamespace

import pytest
from django.test import override_settings

from apps.assetmanagement.views._export_mixin import ExportExcelMixin


class _FakeQueryset:
    """提供 count/iterator 语义的最小仿真 queryset"""

    def __init__(self, rows):
        self._rows = rows

    def count(self):
        return len(self._rows)

    def iterator(self, chunk_size=None):
        return iter(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeView(ExportExcelMixin):
    export_columns = [
        {"header": "编码", "field": "asset_code"},
        {"header": "状态", "field": "asset_current_status", "display_map": {"in_store": "在库"}},
    ]

    def __init__(self, rows):
        self.rows = rows

    def get_queryset(self):
        return _FakeQueryset(self.rows)


def _make_rows(n):
    return [SimpleNamespace(asset_code=f"A{i:03d}", asset_current_status="in_store") for i in range(n)]


@pytest.mark.parametrize("rows,limit", [(0, 2), (2, 2), (10, 10000)])
def test_export_within_limit_returns_xlsx(rows, limit):
    view = _FakeView(_make_rows(rows))
    with override_settings(EXPORT_MAX_ROWS=limit):
        resp = view.export_excel(request=None)
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/vnd.openxmlformats")


def test_export_over_limit_rejected():
    view = _FakeView(_make_rows(3))
    with override_settings(EXPORT_MAX_ROWS=2):
        resp = view.export_excel(request=None)
    assert resp.status_code == 400
    assert resp.data["code"] == 400
    assert "超过上限2" in resp.data["message"]
