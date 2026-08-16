"""
硬盘序列号并发竞态兜底回归测试

锚定 DB 约束冲突 → DUPLICATE_SN_CODE 映射逻辑:
- create / update / batch_save 三个落库点在预检失效(并发窗口)时,
  由 DB 唯一约束兜底,IntegrityError 映射为业务错误而非 500
- 注:MySQL 不执行带 condition 的 UniqueConstraint(Django 静默跳过),
  故以 mock 模拟约束抛错,验证映射与事务保护逻辑
"""

from typing import Any
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from apps.assetmanagement.models import Asset, HardDiskSN
from apps.assetmanagement.services import HardDiskSNService
from core.exceptions import AppValidationError


_SN_VIOLATION = IntegrityError("UNIQUE constraint failed: assetmanagement_harddisksn.harddisk_sn_code")


@pytest.mark.django_db
class TestHardDiskSNIntegrityFallback:
    def test_create_race_maps_to_duplicate(self, db: Any, asset: Asset) -> None:
        data = {"harddisk_sn_code": "SN-DUP-1", "harddisk_type": "SSD", "asset_recordcode": asset}
        with patch.object(HardDiskSN.objects, "create", side_effect=_SN_VIOLATION):
            with pytest.raises(AppValidationError) as exc_info:
                HardDiskSNService.create(data=data)
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"

    def test_update_race_maps_to_duplicate(self, db: Any, asset: Asset) -> None:
        hd = HardDiskSN.objects.create(asset_recordcode=asset, harddisk_sn_code="SN-DUP-B", harddisk_type="SSD")
        with patch.object(HardDiskSN, "save", side_effect=_SN_VIOLATION):
            with pytest.raises(AppValidationError) as exc_info:
                HardDiskSNService.update(recordcode=hd.recordcode, update_data={"harddisk_sn_code": "SN-DUP-A"})
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"

    def test_batch_save_race_maps_to_duplicate(self, db: Any, asset: Asset) -> None:
        disks = [{"harddisk_sn_code": "SN-DUP-2", "harddisk_type": "SSD"}]
        with patch.object(HardDiskSN.objects, "create", side_effect=_SN_VIOLATION):
            with pytest.raises(AppValidationError) as exc_info:
                HardDiskSNService.batch_save(asset_recordcode=asset.recordcode, disks=disks)
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"

    def test_non_sn_integrity_error_propagates(self, db: Any, asset: Asset) -> None:
        """非 SN 的完整性错误不得误标为 DUPLICATE_SN_CODE"""
        data = {"harddisk_sn_code": "SN-DUP-4", "harddisk_type": "SSD", "asset_recordcode": asset}
        other = IntegrityError("UNIQUE constraint failed: assetmanagement_asset.asset_code")
        with patch.object(HardDiskSN.objects, "create", side_effect=other):
            with pytest.raises(IntegrityError):
                HardDiskSNService.create(data=data)

    def test_create_precheck_still_fast_fails(self, db: Any, asset: Asset) -> None:
        """预检未失效时,重复 SN 仍由预检拦截(消息一致)"""
        HardDiskSN.objects.create(asset_recordcode=asset, harddisk_sn_code="SN-DUP-3", harddisk_type="SSD")
        data = {"harddisk_sn_code": "SN-DUP-3", "harddisk_type": "SSD", "asset_recordcode": asset}
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.create(data=data)
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"
