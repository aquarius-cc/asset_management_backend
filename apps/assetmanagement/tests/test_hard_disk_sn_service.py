"""硬盘序列号服务测试"""

from typing import Any

import pytest

from apps.assetmanagement.models import Asset, HardDiskSN
from apps.assetmanagement.services.hard_disk_sn_service import HardDiskSNService
from core.exceptions import AppValidationError


@pytest.fixture
def disk_data(asset):
    return {
        "asset_recordcode": asset,
        "harddisk_sn_code": "SN001",
        "harddisk_type": "SSD",
        "harddisk_capacity": "500GB",
    }


@pytest.mark.django_db
class TestHardDiskSNCreate:
    def test_create_success(self, disk_data):
        result = HardDiskSNService.create(disk_data)
        assert result.harddisk_sn_code == "SN001"
        assert result.asset_recordcode is not None

    def test_create_empty_sn_raises(self, disk_data):
        disk_data["harddisk_sn_code"] = ""
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.create(disk_data)
        assert exc_info.value.error_code == "MISSING_SN_CODE"

    def test_create_whitespace_sn_raises(self, disk_data):
        disk_data["harddisk_sn_code"] = "   "
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.create(disk_data)
        assert exc_info.value.error_code == "MISSING_SN_CODE"

    def test_create_duplicate_sn_raises(self, disk_data):
        HardDiskSNService.create(disk_data)
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.create(disk_data.copy())
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"


@pytest.mark.django_db
class TestHardDiskSNUpdate:
    def test_update_success(self, disk_data):
        hd = HardDiskSNService.create(disk_data)
        result = HardDiskSNService.update(
            hd.recordcode,
            {"harddisk_type": "NVMe"},
        )
        assert result.harddisk_type == "NVMe"

    def test_update_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.update("NONEXIST", {"harddisk_type": "SSD"})
        assert exc_info.value.error_code == "HARD_DISK_NOT_FOUND"

    def test_update_sn_duplicate_raises(self, disk_data):
        _ = HardDiskSNService.create(disk_data)
        disk_data2 = disk_data.copy()
        disk_data2["harddisk_sn_code"] = "SN002"
        hd2 = HardDiskSNService.create(disk_data2)
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.update(hd2.recordcode, {"harddisk_sn_code": "SN001"})
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"

    def test_update_same_sn_no_error(self, disk_data):
        hd = HardDiskSNService.create(disk_data)
        result = HardDiskSNService.update(hd.recordcode, {"harddisk_sn_code": "SN001"})
        assert result.harddisk_sn_code == "SN001"

    def test_update_sn_strips_whitespace(self, disk_data):
        hd = HardDiskSNService.create(disk_data)
        result = HardDiskSNService.update(hd.recordcode, {"harddisk_sn_code": "  SN_TRIM  "})
        assert result.harddisk_sn_code == "SN_TRIM"


@pytest.mark.django_db
class TestHardDiskSNDelete:
    def test_delete_success(self, disk_data):
        hd = HardDiskSNService.create(disk_data)
        HardDiskSNService.delete(hd.recordcode)
        assert not HardDiskSN.objects.filter(recordcode=hd.recordcode, is_deleted=False).exists()

    def test_delete_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.delete("NONEXIST")
        assert exc_info.value.error_code == "HARD_DISK_NOT_FOUND"


@pytest.mark.django_db
class TestHardDiskSNBatchSave:
    def test_batch_save_exceeds_limit_raises(self, asset: Any) -> None:
        disks = [{"harddisk_sn_code": f"SN{i}", "harddisk_type": "SSD"} for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(asset.recordcode, disks)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_save_empty_disks_raises(self, asset: Any) -> None:
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(asset.recordcode, [])
        assert exc_info.value.error_code == "EMPTY_DISKS"

    def test_batch_save_asset_not_found_raises(self) -> None:
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save("NONEXIST", [{"harddisk_sn_code": "BSN_NA", "harddisk_type": "SSD"}])
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_batch_save_missing_sn_raises(self, asset: Any) -> None:
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(asset.recordcode, [{"harddisk_type": "SSD"}])
        assert exc_info.value.error_code == "MISSING_SN_CODE"

    def test_batch_save_create_success(self, db: Any, asset: Any) -> None:
        """批量保存创建路径(asset_recordcode 传字符串,由 Service 解析为实例)"""
        result = HardDiskSNService.batch_save(
            asset.recordcode,
            [{"harddisk_sn_code": "BSN_OK", "harddisk_type": "SSD"}],
        )
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["total"] == 1
        assert result["asset_recordcode"] == asset.recordcode
        saved = HardDiskSN.objects.get(harddisk_sn_code="BSN_OK")
        assert saved.asset_recordcode.recordcode == asset.recordcode

    def test_batch_save_create_applies_model_defaults(self, db: Any, asset: Any) -> None:
        result = HardDiskSNService.batch_save(asset.recordcode, [{"harddisk_sn_code": "BSN_DEF"}])
        assert result["created"] == 1
        saved = HardDiskSN.objects.get(harddisk_sn_code="BSN_DEF")
        assert saved.harddisk_type == "HDD"
        assert saved.harddisk_status == "active"
        assert saved.harddisk_capacity == ""

    def test_batch_save_update_with_own_sn_keeps_it(self, db: Any, asset: Any) -> None:
        """编辑模式回传自身 SN 不触发重复(锚定前端编辑功能修复)"""
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_UPD",
                "harddisk_type": "SSD",
            }
        )
        result = HardDiskSNService.batch_save(
            asset.recordcode,
            [{"recordcode": hd.recordcode, "harddisk_sn_code": "BSN_UPD", "harddisk_type": "NVMe"}],
        )
        assert result["created"] == 0
        assert result["updated"] == 1
        hd.refresh_from_db()
        assert hd.harddisk_sn_code == "BSN_UPD"
        assert hd.harddisk_type == "NVMe"

    def test_batch_save_update_without_sn_preserves_sn(self, db: Any, asset: Any) -> None:
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_UPD2",
                "harddisk_type": "SSD",
            }
        )
        result = HardDiskSNService.batch_save(
            asset.recordcode, [{"recordcode": hd.recordcode, "harddisk_type": "NVMe"}]
        )
        assert result["updated"] == 1
        hd.refresh_from_db()
        assert hd.harddisk_sn_code == "BSN_UPD2"
        assert hd.harddisk_type == "NVMe"

    def test_batch_save_update_without_capacity_preserves_capacity(self, db: Any, asset: Any) -> None:
        """更新载荷不含 capacity 时保留原值(锚定容量擦除修复)"""
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_CAP",
                "harddisk_type": "SSD",
                "harddisk_capacity": "1TB",
            }
        )
        result = HardDiskSNService.batch_save(
            asset.recordcode, [{"recordcode": hd.recordcode, "harddisk_status": "repair"}]
        )
        assert result["updated"] == 1
        hd.refresh_from_db()
        assert hd.harddisk_capacity == "1TB"
        assert hd.harddisk_status == "repair"

    def test_batch_save_update_capacity(self, db: Any, asset: Any) -> None:
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_CAP2",
                "harddisk_capacity": "500GB",
            }
        )
        result = HardDiskSNService.batch_save(
            asset.recordcode, [{"recordcode": hd.recordcode, "harddisk_capacity": "2TB"}]
        )
        assert result["updated"] == 1
        hd.refresh_from_db()
        assert hd.harddisk_capacity == "2TB"

    def test_batch_save_cross_collision_raises(self, db: Any, asset: Any) -> None:
        """更新改为他人 SN 仍须报重复(锚定精确豁免逻辑)"""
        HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_X",
                "harddisk_type": "SSD",
            }
        )
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_X2",
                "harddisk_type": "SSD",
            }
        )
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(
                asset.recordcode,
                [{"recordcode": hd.recordcode, "harddisk_sn_code": "BSN_X", "harddisk_type": "NVMe"}],
            )
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"

    def test_batch_save_reparent_raises(self, db: Any, asset: Any, storage: Any, asset_type: Any) -> None:
        """以其他资产调用更新他人硬盘须报错(锚定跨资产改挂禁止)"""
        hd = HardDiskSNService.create(
            {
                "asset_recordcode": asset,
                "harddisk_sn_code": "BSN_RE",
                "harddisk_type": "SSD",
            }
        )
        other = Asset.objects.create(
            asset_code="A002",
            asset_name="其他资产",
            asset_purchase_price=2000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
        )
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(
                other.recordcode,
                [{"recordcode": hd.recordcode, "harddisk_type": "NVMe"}],
            )
        assert exc_info.value.error_code == "ASSET_MISMATCH"

    def test_batch_save_duplicate_sn_raises(self, asset: Any) -> None:
        """已存在的 SN 应被拒绝"""
        HardDiskSN.objects.create(
            asset_recordcode=asset,
            harddisk_sn_code="EXISTING_SN",
            harddisk_type="SSD",
        )
        disks = [{"harddisk_sn_code": "EXISTING_SN", "harddisk_type": "HDD"}]
        with pytest.raises(AppValidationError) as exc_info:
            HardDiskSNService.batch_save(asset.recordcode, disks)
        assert exc_info.value.error_code == "DUPLICATE_SN_CODE"
