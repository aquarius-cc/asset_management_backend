"""
[M-12] check_data_consistency --strict 退出码语义测试

背景：巡检原仅打印 issues，接入 CI/定时任务无法据此告警。--strict 下
issues 非空必须抛 CommandError（manage.py 下退出码 1）；非 strict 行为逐字节不变。
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.assetmanagement.models import Asset, OutAsset


pytestmark = pytest.mark.django_db


@pytest.fixture
def broken_asset(asset):
    """broken 状态且无维修记录的一致性违规资产"""
    asset.asset_current_status = Asset.AssetStatus.BROKEN
    asset.save(update_fields=["asset_current_status"])
    return asset


class TestCheckDataConsistencyStrict:
    def test_strict_raises_on_issues(self, broken_asset):
        with pytest.raises(CommandError, match="数据一致性检查发现 1 个问题"):
            call_command("check_data_consistency", "--strict")

    def test_strict_clean_exit_zero(self, asset):
        # in_store 且无出库记录 = 一致性干净
        call_command("check_data_consistency", "--strict")

    def test_no_strict_keeps_nonzero_exit_free_behavior(self, broken_asset, capsys):
        # 非 strict：issues 仅打印，不抛错（行为逐字节不变）
        call_command("check_data_consistency")
        captured = capsys.readouterr()
        assert "一致性问题" in captured.err
        assert "broken 但无进行中维修记录" in captured.out


class TestPerfAndNullFK:
    """M-PERF-04：3N+3→5 查询数恒定 + K-2 null FK 不误报"""

    def test_query_count_constant_with_more_assets(self, asset, django_assert_num_queries):
        """热身 + 两轮计数：数据增长后查询数恒定（新实现恒 5）"""
        asset.asset_current_status = Asset.AssetStatus.BROKEN
        asset.save(update_fields=["asset_current_status"])
        call_command("check_data_consistency")  # 热身

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            call_command("check_data_consistency")
        first = len(ctx.captured_queries)

        # 再造一批 broken 资产
        for i in range(3):
            extra = Asset.objects.get(pk=asset.pk)
            extra.pk = None
            extra.recordcode = None
            extra.asset_code = f"APF{i:03d}"
            extra.save()
            Asset.objects.filter(pk=extra.pk).update(asset_current_status=Asset.AssetStatus.BROKEN)

        with CaptureQueriesContext(connection) as ctx2:
            call_command("check_data_consistency")
        assert len(ctx2.captured_queries) == first, f"查询数漂移: {first} → {len(ctx2.captured_queries)}"

    def test_null_fk_not_false_positive(self, asset):
        """K-2：OutAsset.asset_recordcode 为 NULL 时不得误报/崩溃（--strict 不抛错）"""
        Asset.objects.filter(pk=asset.pk).update(recordcode=None)
        OutAsset.objects.create(asset_recordcode=None, outasset_number=1)

        call_command("check_data_consistency", "--strict")  # 不得抛 CommandError
