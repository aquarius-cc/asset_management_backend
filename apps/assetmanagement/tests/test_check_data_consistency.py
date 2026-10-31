"""
[M-12] check_data_consistency --strict 退出码语义测试

背景：巡检原仅打印 issues，接入 CI/定时任务无法据此告警。--strict 下
issues 非空必须抛 CommandError（manage.py 下退出码 1）；非 strict 行为逐字节不变。
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.assetmanagement.models import Asset


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
