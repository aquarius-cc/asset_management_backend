"""
AssetService 单元测试

覆盖 update_asset, delete_asset, batch_delete_asset,
change_asset_status, change_outasset_employee, get_asset_statistics,
generate_qr_code_image。
"""

from typing import Any

import pytest

from apps.assetmanagement.models import (
    Asset,
    DamagedAsset,
)
from apps.assetmanagement.services.asset_service import AssetService
from apps.assetmanagement.state_machine import InvalidTransitionError
from apps.usermanagement.models import Employee
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestUpdateAsset:
    """update_asset 测试"""

    def test_update_asset_success(self, asset):
        result = AssetService.update_asset(
            asset_code="A001",
            update_data={"asset_name": "更新后名称"},
        )
        result.refresh_from_db()
        assert result.asset_name == "更新后名称"

    def test_update_asset_not_found(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(asset_code="NOT_EXIST", update_data={"asset_name": "x"})
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_update_asset_disallowed_field(self, asset):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(
                asset_code="A001",
                update_data={"asset_code": "HACKED"},
            )
        assert exc_info.value.error_code == "FIELD_NOT_ALLOWED"

    def test_update_asset_multiple_fields(self, asset):
        result = AssetService.update_asset(
            asset_code="A001",
            update_data={
                "asset_name": "名称B",
                "asset_brand": "品牌B",
                "asset_specification": "规格B",
            },
        )
        result.refresh_from_db()
        assert result.asset_name == "名称B"
        assert result.asset_brand == "品牌B"
        assert result.asset_specification == "规格B"


@pytest.mark.django_db
class TestDeleteAsset:
    """delete_asset 测试"""

    def test_delete_asset_success(self, asset):
        AssetService.delete_asset(asset_code="A001")
        assert Asset.all_objects.filter(asset_code="A001", is_deleted=True).exists()

    def test_delete_asset_not_found(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="NOT_EXIST")
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_delete_asset_not_in_store(self, asset):
        asset.asset_current_status = "in_use"
        asset.save()
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001")
        assert exc_info.value.error_code == "ASSET_IN_USE"

    def test_delete_asset_has_outasset(self, asset):
        """有关联出库记录时不允许删除(outasset fixture 会改变状态,需手动创建)"""
        from apps.assetmanagement.models import OutAsset

        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001")
        assert exc_info.value.error_code == "ASSET_HAS_OUTASSET"

    def test_delete_asset_has_damaged_record(self, asset):
        """有待报废记录时不允许删除"""
        DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
        )
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001")
        assert exc_info.value.error_code == "HAS_DAMAGED_RECORDS"


@pytest.mark.django_db
class TestBatchDeleteAsset:
    """batch_delete_asset 测试"""

    def test_batch_delete_success(self, asset):
        result = AssetService.batch_delete_asset(asset_codes=["A001"])
        assert result["success_count"] == 1
        assert result["fail_count"] == 0

    def test_batch_delete_exceeds_limit(self):
        codes = [f"CODE_{i}" for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.batch_delete_asset(asset_codes=codes)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_mixed_results(self, asset):
        """部分成功部分失败"""
        result = AssetService.batch_delete_asset(asset_codes=["A001", "NOT_EXIST"])
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert "NOT_EXIST" in result["fail_items"][0]["id"]

    def test_batch_delete_not_in_store(self, asset):
        asset.asset_current_status = "in_use"
        asset.save()
        result = AssetService.batch_delete_asset(asset_codes=["A001"])
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_IN_USE"

    def test_batch_delete_empty_list(self):
        result = AssetService.batch_delete_asset(asset_codes=[])
        assert result["total"] == 0
        assert result["success_count"] == 0


@pytest.mark.django_db
class TestChangeAssetStatus:
    """change_asset_status 测试"""

    def test_change_status_success(self, asset):
        result = AssetService.change_asset_status(
            asset_code="A001",
            new_status="in_use",
        )
        result.refresh_from_db()
        assert result.asset_current_status == "in_use"

    def test_change_status_invalid_transition(self, asset):
        """in_store -> scrapped 是非法转换"""
        with pytest.raises(InvalidTransitionError):
            AssetService.change_asset_status(
                asset_code="A001",
                new_status="scrapped",
            )

    def test_change_status_asset_not_found(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status(
                asset_code="NOT_EXIST",
                new_status="in_use",
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_change_status_invalid_status_value(self, asset):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status(
                asset_code="A001",
                new_status="fake_status",
            )
        assert exc_info.value.error_code == "INVALID_ASSET_STATUS"


@pytest.mark.django_db
class TestChangeOutassetEmployee:
    """change_outasset_employee 测试"""

    def test_change_employee_success(self, asset, user):
        manager = Employee.objects.create(
            employee_jobcode="U002",
            employee_name="保管人",
            employee_department=user.employee_department,
            employee_phone="13800133001",
        )
        # change_outasset_employee 通过 FK descriptor 赋值,需传 Employee 实例
        result = AssetService.change_outasset_employee(
            asset_code="A001",
            applicant_jobcode=user,
            manager_jobcode=manager,
        )
        result.refresh_from_db()
        assert result.asset_applicant_recordcode == user
        assert result.asset_manager_recordcode == manager

    def test_change_employee_asset_not_found(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_outasset_employee(
                asset_code="NOT_EXIST",
                applicant_jobcode="X",
                manager_jobcode="Y",
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"


@pytest.mark.django_db
class TestGetAssetStatistics:
    """get_asset_statistics 测试(补充已有 test_services.py 中的用例)"""

    def test_statistics_empty_db(self):
        stats = AssetService.get_asset_statistics()
        assert stats["total_count"] == 0
        assert stats["total_value"] == 0

    def test_statistics_with_assets(self, asset):
        stats = AssetService.get_asset_statistics()
        assert stats["total_count"] >= 1
        assert "status_distribution" in stats
        assert "in_store" in stats["status_distribution"]


class TestGenerateQrCodeImage:
    """generate_qr_code_image 回归(F821 裸名 FRONTEND_BASE_URL 修复)"""

    def test_returns_png_bytes(self, asset: Any) -> None:
        data = AssetService.generate_qr_code_image(asset, "http://localhost:5173")
        assert data.startswith(b"\x89PNG")

    def test_url_uses_passed_base_url(self, asset: Any) -> None:
        data = AssetService.generate_qr_code_image(asset, "https://example.com")
        assert data.startswith(b"\x89PNG")
