"""
AssetService 单元测试

覆盖 update_asset, delete_asset, batch_delete_asset,
change_asset_status, change_outasset_employee, get_asset_statistics,
generate_qr_code_image。
"""

from decimal import Decimal
from typing import Any

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    DamagedAsset,
    Storage,
)
from apps.assetmanagement.services.asset_service import AssetService
from apps.usermanagement.models import Employee
from core.exceptions import AppValidationError, NotFoundError


@pytest.mark.django_db
class TestUpdateAsset:
    """update_asset 测试"""

    def test_update_asset_success(self, asset, admin_auth_user):
        result = AssetService.update_asset(
            asset_code="A001",
            update_data={"asset_name": "更新后名称"},
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_name == "更新后名称"

    def test_update_asset_not_found(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(
                asset_code="NOT_EXIST", update_data={"asset_name": "x"}, user=admin_auth_user
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_update_asset_disallowed_field(self, asset, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(
                asset_code="A001",
                update_data={"asset_code": "HACKED"},
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "FIELD_NOT_ALLOWED"

    def test_update_asset_rejects_status_change(self, asset, admin_auth_user):
        """asset_current_status 变更所有权归 FSM,不可经通用更新接口直改(CT-3)"""
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(
                asset_code="A001",
                update_data={"asset_current_status": "in_store"},
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "FIELD_NOT_ALLOWED"

    def test_update_asset_fk_instance(self, asset, asset_type, admin_auth_user):
        """validated_data 中 FK 字段为模型实例,setattr 更新成功且审计快照归一化"""
        from apps.assetmanagement.models import AssetType

        new_type = AssetType.objects.create(
            type_code="AT-T-002",
            type_name="测试类型B",
            parent=None,
        )
        result = AssetService.update_asset(
            asset_code="A001",
            update_data={
                "asset_type_recordcode": new_type,
                "asset_purchase_price": Decimal("2000.00"),
            },
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_type_recordcode == new_type
        assert result.asset_purchase_price == Decimal("2000.00")
        log = AssetOperationLog.objects.get(
            asset_code="A001", operation_type=AssetOperationLog.OperationType.UPDATE
        )
        # CT-4 归一化锚点: 快照归一委托 _to_json_safe 收口(幂等),FK 实例→recordcode 字符串、
        # Decimal→str,保证 JSONField 可序列化——与删除流内 _normalize 前行为逐字符一致
        assert log.before_data["asset_type_recordcode"] == str(asset_type.recordcode)
        assert log.before_data["asset_purchase_price"] == "1000.00"
        assert log.after_data["asset_type_recordcode"] == str(new_type.recordcode)
        assert log.after_data["asset_purchase_price"] == "2000.00"

    def test_update_asset_multiple_fields(self, asset, admin_auth_user):
        result = AssetService.update_asset(
            asset_code="A001",
            update_data={
                "asset_name": "名称B",
                "asset_brand": "品牌B",
                "asset_specification": "规格B",
            },
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_name == "名称B"
        assert result.asset_brand == "品牌B"
        assert result.asset_specification == "规格B"


@pytest.mark.django_db
class TestDeleteAsset:
    """delete_asset 测试"""

    def test_delete_asset_success(self, asset, admin_auth_user):
        AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert Asset.all_objects.filter(asset_code="A001", is_deleted=True).exists()

    def test_delete_asset_not_found(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="NOT_EXIST", user=admin_auth_user)
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_delete_asset_not_in_store(self, asset, admin_auth_user):
        asset.asset_current_status = "in_use"
        asset.save()
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc_info.value.error_code == "ASSET_IN_USE"

    def test_delete_asset_has_outasset(self, asset, admin_auth_user):
        """有关联出库记录时不允许删除(outasset fixture 会改变状态,需手动创建)"""
        from apps.assetmanagement.models import OutAsset

        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc_info.value.error_code == "ASSET_HAS_OUTASSET"

    def test_delete_asset_has_damaged_record(self, asset, admin_auth_user):
        """有待报废记录时不允许删除"""
        DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
        )
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc_info.value.error_code == "HAS_DAMAGED_RECORDS"


@pytest.mark.django_db
class TestBatchDeleteAsset:
    """batch_delete_asset 测试"""

    def test_batch_delete_success(self, asset, admin_auth_user):
        result = AssetService.batch_delete_asset(asset_codes=["A001"], user=admin_auth_user)
        assert result["success_count"] == 1
        assert result["fail_count"] == 0

    def test_batch_delete_exceeds_limit(self, admin_auth_user):
        codes = [f"CODE_{i}" for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.batch_delete_asset(asset_codes=codes, user=admin_auth_user)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_mixed_results(self, asset, admin_auth_user):
        """部分成功部分失败"""
        result = AssetService.batch_delete_asset(asset_codes=["A001", "NOT_EXIST"], user=admin_auth_user)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert "NOT_EXIST" in result["fail_items"][0]["id"]

    def test_batch_delete_not_in_store(self, asset, admin_auth_user):
        asset.asset_current_status = "in_use"
        asset.save()
        result = AssetService.batch_delete_asset(asset_codes=["A001"], user=admin_auth_user)
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_IN_USE"

    def test_batch_delete_has_outasset(self, asset, admin_auth_user):
        """有关联出库记录时批量删除失败,错误码与单条路径统一(CT-4 回归护栏)"""
        from apps.assetmanagement.models import OutAsset

        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        result = AssetService.batch_delete_asset(asset_codes=["A001"], user=admin_auth_user)
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_HAS_OUTASSET"

    def test_batch_delete_mixed_success_and_outasset(self, asset, storage, asset_type, admin_auth_user):
        """逐条独立: A001 成功删除, A002 因出库记录失败, 互不影响"""
        from apps.assetmanagement.models import OutAsset

        other = Asset.objects.create(
            asset_code="A002",
            asset_name="其它资产",
            asset_purchase_price=1000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
        )
        OutAsset.objects.create(asset_recordcode=other, outasset_date="2024-01-01")
        result = AssetService.batch_delete_asset(asset_codes=["A001", "A002"], user=admin_auth_user)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert "A001" in result["success_ids"]
        assert result["fail_items"][0]["id"] == "A002"
        assert result["fail_items"][0]["error_code"] == "ASSET_HAS_OUTASSET"

    def test_batch_delete_toctou_invisible_maps_to_not_found(self, asset, admin_auth_user, monkeypatch):
        """TOCTOU 锁内可见性失败统一归入 NOT_FOUND,不泄漏底层错误码且不误伤守卫(B12)"""
        from apps.assetmanagement.selectors import AssetSelector

        def _raise_invisible(asset_obj, user):
            raise AppValidationError(detail="资产不可见", error_code="ASSET_NOT_FOUND")

        monkeypatch.setattr(AssetSelector, "ensure_asset_visible", _raise_invisible)
        result = AssetService.batch_delete_asset(asset_codes=["A001"], user=admin_auth_user)
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
        assert Asset.all_objects.filter(asset_code="A001", is_deleted=False).exists()

    def test_batch_delete_empty_list(self, admin_auth_user):
        result = AssetService.batch_delete_asset(asset_codes=[], user=admin_auth_user)
        assert result["total"] == 0
        assert result["success_count"] == 0


@pytest.mark.django_db
class TestChangeAssetStatus:
    """change_asset_status 测试"""

    def test_change_status_success(self, asset, admin_auth_user):
        result = AssetService.change_asset_status(
            asset_code="A001",
            new_status="in_use",
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_current_status == "in_use"

    def test_change_status_invalid_transition(self, asset, admin_auth_user):
        """in_store -> scrapped 是非法转换,FSM 异常映射为业务校验异常(#38)"""
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status(
                asset_code="A001",
                new_status="scrapped",
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"

    def test_change_status_asset_not_found(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status(
                asset_code="NOT_EXIST",
                new_status="in_use",
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"

    def test_change_status_invalid_status_value(self, asset, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_asset_status(
                asset_code="A001",
                new_status="fake_status",
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "INVALID_ASSET_STATUS"


@pytest.mark.django_db
class TestChangeOutassetEmployee:
    """change_outasset_employee 测试"""

    def test_change_employee_success(self, asset, user, admin_auth_user):
        manager = Employee.objects.create(
            employee_jobcode="U002",
            employee_name="保管人",
            employee_department=user.employee_department,
            employee_phone="13800133001",
        )
        # jobcode→recordcode 映射: 传 jobcode 字符串, Service 经 EmployeeSelector 解析为 Employee 实例
        result = AssetService.change_outasset_employee(
            asset_code="A001",
            applicant_jobcode=user.employee_jobcode,
            manager_jobcode=manager.employee_jobcode,
            operator_jobcode=admin_auth_user.auth_username,
            operator_name=admin_auth_user.auth_username,
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_applicant_recordcode == user
        assert result.asset_manager_recordcode == manager
        log = AssetOperationLog.objects.get(
            asset_code="A001", operation_type=AssetOperationLog.OperationType.UPDATE
        )
        assert log.operator_jobcode == admin_auth_user.auth_username
        assert log.operator_name == admin_auth_user.auth_username

    def test_change_employee_jobcode_not_found(self, asset, admin_auth_user):
        with pytest.raises(NotFoundError):
            AssetService.change_outasset_employee(
                asset_code="A001",
                applicant_jobcode="U999",
                manager_jobcode="U002",
                user=admin_auth_user,
            )

    def test_change_employee_asset_not_found(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc_info:
            AssetService.change_outasset_employee(
                asset_code="NOT_EXIST",
                applicant_jobcode="X",
                manager_jobcode="Y",
                user=admin_auth_user,
            )
        assert exc_info.value.error_code == "ASSET_NOT_FOUND"


@pytest.mark.django_db
class TestTransferAssetToStorage:
    """transfer_asset_to_storage 测试(B7 审计 operator 透传)"""

    def test_transfer_to_storage_tracks_operator(self, asset, storage, admin_auth_user):
        new_storage = Storage.objects.create(
            storage_code="S002",
            storage_name="目标仓库",
            storage_address="测试地点",
            storage_location="测试地点",
            storage_capacity=100,
            sort_order=1,
        )
        result = AssetService.transfer_asset_to_storage(
            asset_code="A001",
            storage_code=new_storage.storage_code,
            operator_jobcode=admin_auth_user.auth_username,
            operator_name=admin_auth_user.auth_username,
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.asset_storage_recordcode == new_storage
        log = AssetOperationLog.objects.get(
            asset_code="A001", operation_type=AssetOperationLog.OperationType.UPDATE
        )
        assert log.operator_jobcode == admin_auth_user.auth_username
        assert log.operator_name == admin_auth_user.auth_username


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
