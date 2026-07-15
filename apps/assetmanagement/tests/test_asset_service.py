"""
AssetService 单元测试

覆盖 update_asset, delete_asset, batch_delete_asset,
change_asset_status, change_outasset_employee, get_asset_statistics,
以及 AssetLifecycleMixin 中的状态流转方法。
"""

from unittest.mock import patch

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    BrokenAsset,
    DamagedAsset,
    LostAsset,
    RepairAsset,
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
        """有关联出库记录时不允许删除（outasset fixture 会改变状态，需手动创建）"""
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
        result = AssetService.batch_delete_asset(
            asset_codes=["A001", "NOT_EXIST"]
        )
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
        )
        # change_outasset_employee 通过 FK descriptor 赋值，需传 Employee 实例
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
    """get_asset_statistics 测试（补充已有 test_services.py 中的用例）"""

    def test_statistics_empty_db(self):
        stats = AssetService.get_asset_statistics()
        assert stats["total_count"] == 0
        assert stats["total_value"] == 0

    def test_statistics_with_assets(self, asset):
        stats = AssetService.get_asset_statistics()
        assert stats["total_count"] >= 1
        assert "status_distribution" in stats
        assert "in_store" in stats["status_distribution"]


@pytest.mark.django_db
class TestMarkAssetBroken:
    """mark_asset_broken 测试"""

    def test_mark_broken_from_in_store(self, asset, user):
        result = AssetService.mark_asset_broken(
            asset_code="A001",
            broken_reason="硬件故障",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "broken"
        assert BrokenAsset.objects.filter(asset_recordcode=asset).exists()

    def test_mark_broken_already_broken(self, asset, user):
        """已损坏的资产再次标记应幂等返回"""
        asset.asset_current_status = "broken"
        asset.save()
        result = AssetService.mark_asset_broken(
            asset_code="A001",
            broken_reason="再次损坏",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result.asset_current_status == "broken"

    def test_mark_broken_invalid_transition(self, asset, user):
        """scrapped 状态不能标记为 broken"""
        asset.asset_current_status = "scrapped"
        asset.save()
        with pytest.raises(InvalidTransitionError):
            AssetService.mark_asset_broken(
                asset_code="A001",
                broken_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )


@pytest.mark.django_db
class TestMarkAssetLost:
    """mark_asset_lost 测试"""

    def test_mark_lost_from_in_store(self, asset, user):
        result = AssetService.mark_asset_lost(
            asset_code="A001",
            lost_reason="遗失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "lost"
        assert LostAsset.objects.filter(asset_recordcode=asset).exists()

    def test_mark_lost_already_lost(self, asset, user):
        """已遗失的资产再次标记应幂等返回"""
        asset.asset_current_status = "lost"
        asset.save()
        result = AssetService.mark_asset_lost(
            asset_code="A001",
            lost_reason="再次遗失",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert result.asset_current_status == "lost"

    def test_mark_lost_invalid_transition(self, asset, user):
        """scrapped 状态不能标记为 lost"""
        asset.asset_current_status = "scrapped"
        asset.save()
        with pytest.raises(InvalidTransitionError):
            AssetService.mark_asset_lost(
                asset_code="A001",
                lost_reason="x",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )


@pytest.mark.django_db
class TestFindAndReturnAsset:
    """find_and_return_asset 测试"""

    def _make_lost_asset(self, asset, user):
        """辅助：将资产标记为 lost 并创建 LostAsset 记录"""
        asset.asset_current_status = "lost"
        asset.save()
        return LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="遗失",
        )

    def test_find_and_return_success(self, asset, user):
        self._make_lost_asset(asset, user)
        result = AssetService.find_and_return_asset(
            asset_code="A001",
            found_location="仓库A",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "in_store"

    def test_find_and_return_no_lost_record(self, asset, user):
        """没有 LostAsset 记录时应报错"""
        asset.asset_current_status = "lost"
        asset.save()
        with pytest.raises(LostAsset.DoesNotExist):
            AssetService.find_and_return_asset(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )


@pytest.mark.django_db
class TestRepairAsset:
    """repair_asset 测试"""

    def _make_broken_asset(self, asset, user):
        """辅助：将资产标记为 broken"""
        asset.asset_current_status = "broken"
        asset.save()
        return asset

    def test_repair_asset_success(self, asset, user):
        self._make_broken_asset(asset, user)
        result = AssetService.repair_asset(
            asset_code="A001",
            repair_reason="主板故障",
            repair_date="2024-06-01",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        assert isinstance(result, RepairAsset)
        asset.refresh_from_db()
        assert asset.asset_current_status == "repairing"

    def test_repair_asset_invalid_transition(self, asset, user):
        """in_store 状态不能送修"""
        with pytest.raises(InvalidTransitionError):
            AssetService.repair_asset(
                asset_code="A001",
                repair_reason="x",
                repair_date="2024-06-01",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )


@pytest.mark.django_db
class TestRepairDone:
    """repair_done 测试"""

    def _make_repairing_asset(self, asset, user):
        """辅助：将资产标记为 repairing 并创建维修记录"""
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_repair_done_success(self, asset, user):
        self._make_repairing_asset(asset, user)
        result = AssetService.repair_done(
            asset_code="A001",
            actual_return_date="2024-06-10",
            physical_grade_after="良好",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.repair_status == "completed"
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"
        assert asset.physical_grade == "良好"

    def test_repair_done_no_in_progress_record(self, asset, user):
        """没有进行中的维修记录时应报错"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError):
            AssetService.repair_done(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )


@pytest.mark.django_db
class TestRepairFailed:
    """repair_failed 测试"""

    def _make_repairing_asset(self, asset, user):
        """辅助：将资产标记为 repairing 并创建维修记录"""
        asset.asset_current_status = "repairing"
        asset.save()
        return RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-06-01",
            repair_reason="主板故障",
            repair_status="in_progress",
            operator_employee=user,
        )

    def test_repair_failed_success(self, asset, user):
        self._make_repairing_asset(asset, user)
        result = AssetService.repair_failed(
            asset_code="A001",
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )
        result.refresh_from_db()
        assert result.repair_status == "failed"
        asset.refresh_from_db()
        assert asset.asset_current_status == "damaged"
        assert DamagedAsset.objects.filter(asset_recordcode=asset).exists()

    def test_repair_failed_no_in_progress_record(self, asset, user):
        """没有进行中的维修记录时应报错"""
        asset.asset_current_status = "repairing"
        asset.save()
        with pytest.raises(AppValidationError):
            AssetService.repair_failed(
                asset_code="A001",
                operator_jobcode=user.employee_jobcode,
                operator_name=user.employee_name,
            )
