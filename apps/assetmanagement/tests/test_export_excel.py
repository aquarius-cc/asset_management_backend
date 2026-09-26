"""
导出 Excel Mixin 单元测试(#40 EXPORT_MAX_ROWS 资源防护)

覆盖:
1. 超限:total > EXPORT_MAX_ROWS → 400 + 上限文案
2. 正常:total ≤ 上限 → 200 + xlsx MIME
3. 边界:total == 上限 → 允许导出
4. 取行钩子:默认 get_export_queryset() 委托 get_queryset();子类覆写时导出走覆写口径
   (BF-047 引入钩子时的回归屏障——11 个未覆写的端点行为必须字节级不变)
"""

from types import SimpleNamespace

import pytest
from django.test import override_settings

from core.excel_export import ExportExcelMixin


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


class _OverriddenExportView(_FakeView):
    """模拟 EmployeeViewSet：覆写取行钩子以对齐自身列表口径"""

    def __init__(self, rows, export_rows):
        super().__init__(rows)
        self.export_rows = export_rows

    def get_export_queryset(self):
        return _FakeQueryset(self.export_rows)


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


def test_default_export_queryset_delegates_to_get_queryset():
    """默认实现必须原样返回 get_queryset()，不得引入任何额外收窄。"""
    rows = _make_rows(3)
    view = _FakeView(rows)
    assert list(view.get_export_queryset()) == list(view.get_queryset())


def test_export_uses_overridden_queryset_hook():
    """子类覆写钩子后，导出行集合取自覆写口径（BF-047 的扩展点契约）。"""
    export_rows = _make_rows(5)
    view = _OverriddenExportView(_make_rows(2), export_rows)
    assert list(view.get_export_queryset()) == list(export_rows)
    assert list(view.get_queryset()) != list(export_rows)


def test_export_limit_measured_on_hook_rows_not_list_rows():
    """上限判定基于钩子口径的行数：覆写后大集合也须被 EXPORT_MAX_ROWS 拦住。"""
    view = _OverriddenExportView(_make_rows(1), _make_rows(5))
    with override_settings(EXPORT_MAX_ROWS=2):
        resp = view.export_excel(request=None)
    assert resp.status_code == 400
    assert "超过上限2" in resp.data["message"]
