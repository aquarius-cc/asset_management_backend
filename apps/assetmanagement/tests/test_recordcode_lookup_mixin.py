"""
RecordcodeLookupMixin.get_object 单元测试（M-AUD-4）

覆盖 pk 未命中回落 recordcode 查找路径的 debug 日志留痕（M-47 家族）：
- 正例：digit 值 pk 未中 → 回落 recordcode 命中 → debug 日志一条
- 反例：digit 值 pk 直中 → 不产生日志
- 回落 404：digit 值两者皆未中 → Http404 且日志已留痕
- 回归屏障：非 digit 值不进 pk 分支 → 无日志（不误报）

Stub 依赖契约：queryset（供 .model.DoesNotExist/__name__）、
get_queryset()、kwargs、check_object_permissions（pk 命中与回落成功
两条路径均会调用）。模型选 AssetType（type_code/type_name 两字段建行，
含 BaseModel recordcode），避免三重 FK 建行负担。
"""

import logging
from typing import Any

import pytest
from django.http import Http404

from apps.assetmanagement.models import AssetType
from apps.assetmanagement.views._mixins import RecordcodeLookupMixin


mixins_logger_name = "apps.assetmanagement.views._mixins"


class _StubLookupView(RecordcodeLookupMixin):
    """测试替身：满足 get_object 的全部成员依赖（真实模型 + no-op 权限钩子）"""

    queryset = AssetType.objects.all()
    lookup_field: str = "recordcode"
    lookup_url_kwarg: str | None = None

    def __init__(self, lookup_value: str, request: Any = None) -> None:
        self.kwargs = {"recordcode": lookup_value}
        self.request = request

    def get_queryset(self) -> Any:
        return AssetType.objects.all()

    def check_object_permissions(self, request: Any, obj: Any) -> None: ...


@pytest.fixture
def asset_type_row(db) -> AssetType:
    return AssetType.objects.create(type_code="AT001", type_name="服务器")


@pytest.mark.django_db
class TestRecordcodeLookupDebugLog:
    """【M-AUD-4】pk 未命中回落路径的 debug 留痕（正反例 + 回归屏障）"""

    def test_pk_miss_falls_back_to_recordcode_logs_debug(self, asset_type_row, caplog) -> None:
        """digit 值 pk 未中 → 回落 recordcode 命中 → 恰一条 debug 日志"""
        # recordcode 置为 digit 串（非 pk）：pk 查未中 → recordcode 回落命中
        digit_code = "9000000001"
        asset_type_row.recordcode = digit_code
        asset_type_row.save(update_fields=["recordcode"])
        view = _StubLookupView(digit_code)
        with caplog.at_level(logging.DEBUG, logger=mixins_logger_name):
            obj = view.get_object()

        assert obj.recordcode == digit_code
        hits = [r for r in caplog.records if "pk 未命中" in r.getMessage()]
        assert len(hits) == 1
        assert digit_code in hits[0].getMessage()

    def test_pk_hit_direct_no_log(self, asset_type_row, caplog) -> None:
        """digit 值 pk 直中 → 不产生回落日志（不误报）"""
        view = _StubLookupView(str(asset_type_row.pk))
        with caplog.at_level(logging.DEBUG, logger=mixins_logger_name):
            obj = view.get_object()

        assert obj.pk == asset_type_row.pk
        assert not [r for r in caplog.records if "pk 未命中" in r.getMessage()]

    def test_both_miss_raises_404_after_log(self, asset_type_row, caplog) -> None:
        """digit 值两者皆未中 → 留痕后抛 Http404"""
        view = _StubLookupView("999999999")
        with caplog.at_level(logging.DEBUG, logger=mixins_logger_name):
            with pytest.raises(Http404):
                view.get_object()

        assert [r for r in caplog.records if "pk 未命中" in r.getMessage()]

    def test_non_digit_skips_pk_branch_no_log(self, asset_type_row, caplog) -> None:
        """回归屏障：纯字符串走 recordcode 直查 → 无 pk 回落日志（分支不误入）"""
        view = _StubLookupView(asset_type_row.recordcode)
        with caplog.at_level(logging.DEBUG, logger=mixins_logger_name):
            obj = view.get_object()

        assert obj.recordcode == asset_type_row.recordcode
        assert not [r for r in caplog.records if "pk 未命中" in r.getMessage()]
