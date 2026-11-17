"""【MA-13】时区口径回归——localdate()（CST 日历日）取代 now().date()（UTC 日历日）。

先红后绿口径（冻结 timezone.now = 2026-11-15T16:30:00Z = CST 2026-11-16 00:30）:
- 修复前：`timezone.now().date()` / `date.today()`（UTC/进程日历日）得 2026-11-15 → 用例红
- 修复后：`timezone.localdate()` 得 2026-11-16 → 用例绿
- patch 点为 django.utils.timezone.now（localdate → localtime → 模块级 now 查找链），
  date.today() 是 C 层类方法不受 patch 影响——旧口径对照断言用 datetime.now(UTC) 等价呈现。

服务级样点取 repair_asset_service.complete_repair（actual_return_date 兜底分支，
位于 mutmut source_paths 变异范围内，双重门禁覆盖）；选择器/处理器与其同构
（11 处统一 localdate，测试同步见 test_dashboard_alert_window / test_repair_service_gaps）。
"""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.assetmanagement.models import RepairAsset
from apps.assetmanagement.services.repair_asset_service import RepairAssetService


FIXED_UTC_NOW = datetime(2026, 11, 15, 16, 30, 0, tzinfo=UTC)


def test_localdate_yields_cst_calendar_date():
    """localdate() = CST 日历日 11-16；旧口径 UTC 日历日 11-15（缺陷 demonstratio）。"""
    with patch("django.utils.timezone.now", return_value=FIXED_UTC_NOW):
        assert timezone.now().date() == date(2026, 11, 15)  # 旧口径（now().date() = UTC 日历日）
        assert timezone.localdate() == date(2026, 11, 16)  # 新口径


@pytest.mark.django_db
def test_complete_repair_fallback_uses_localdate(asset, user):
    """actual_return_date 兜底分支走 localdate：CST 00:30 时点应为 11-16 而非 11-15。"""
    asset.asset_current_status = "repairing"
    asset.save()
    RepairAsset.objects.create(
        asset_recordcode=asset,
        repair_date="2026-06-01",
        repair_reason="主板故障",
        repair_status="in_progress",
    )
    with patch("django.utils.timezone.now", return_value=FIXED_UTC_NOW):
        RepairAssetService.complete_repair(
            asset_code=asset.asset_code,
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
    record = RepairAsset.objects.get(asset_recordcode=asset)
    assert record.actual_return_date == date(2026, 11, 16)
