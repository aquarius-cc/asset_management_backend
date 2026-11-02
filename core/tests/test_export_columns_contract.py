"""导出列契约护栏: export_columns[*].field 必须能沿模型关系逐段解析(CT-4)。

M-04 的根因是字段名拼写错误(damaged_asset_date)被 workbook.get_nested_value 的
getattr(..., None) 静默吞成空列——运行期零报错, 只有用户看到空列才暴露。
本用例把该类错误前移为测试期红灯, 覆盖 3 个 app router 上全部带 export_columns 的
ViewSet(2026-10-31 实测: 9 个 ViewSet / 61 列, 均声明 queryset)。

为何置于 core/tests: 契约跨 assetmanagement / usermanagement / unregisteredasset
三个 app, 按 DR-4 工具单一仓库不归属于任一业务 app。
"""

import importlib

import pytest
from django.core.exceptions import FieldDoesNotExist


MODULES = (
    "apps.assetmanagement.urls",
    "apps.usermanagement.urls",
    "apps.unregisteredasset.urls",
)

_MIN_CHECKED = 78  # 实测 82 列(2026-11-02 D-4: 四生命周期端点补 21 列, 61→82); 下限防枚举失效后护栏恒绿


def _iter_export_views():
    """遍历各 app router 上带 export_columns 的 ViewSet。"""
    for mod_name in MODULES:
        registry = importlib.import_module(mod_name).router.registry
        for _prefix, view_cls, _basename in registry:
            columns = getattr(view_cls, "export_columns", None)
            if columns:
                yield view_cls, columns


@pytest.mark.django_db
def test_export_columns_resolve_to_model_fields():
    errors: list[str] = []
    checked = 0
    for view_cls, columns in _iter_export_views():
        queryset = getattr(view_cls, "queryset", None)
        if queryset is None:
            continue  # 未声明 queryset 的 ViewSet 不在本契约覆盖范围(当前实测为空集)
        model = queryset.model
        for col in columns:
            current = model
            parts = col["field"].split("__")
            for idx, part in enumerate(parts):
                try:
                    field = current._meta.get_field(part)
                except FieldDoesNotExist:
                    errors.append(
                        f"{view_cls.__name__} 导出列「{col['header']}」字段 "
                        f"{col['field']} 在 {current.__name__} 上不存在: {part}"
                    )
                    break
                if idx == len(parts) - 1:
                    break
                if not field.is_relation:
                    # 非关系字段后仍有路径段: 上游 getattr(..., None) 会静默吞掉后续段, 必须判红
                    errors.append(
                        f"{view_cls.__name__} 导出列「{col['header']}」字段 "
                        f"{col['field']}: {current.__name__}.{part} 非关系字段, 之后还有路径段"
                    )
                    break
                current = field.related_model
            checked += 1
    assert checked >= _MIN_CHECKED, f"仅校验 {checked} 列, 低于下限 {_MIN_CHECKED}, 枚举可能已失效"
    assert not errors, "导出列契约违约 {} 处:\n{}".format(len(errors), "\n".join(errors))
