"""仓库管理服务测试"""

import pytest

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.assetmanagement.services.storage_service import StorageService
from core.exceptions import AppValidationError
from core.models_audit import AuditLog


def _storage_data(**overrides):
    defaults = {
        "storage_code": "SC001",
        "storage_name": "测试仓库",
        "storage_address": "测试地址",
        "storage_capacity": 100,
        "sort_order": 0,
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.django_db
class TestCreateStorage:
    def test_create_success(self):
        result = StorageService.create_storage(_storage_data())
        assert result.storage_code == "SC001"
        assert result.storage_name == "测试仓库"

    def test_create_duplicate_code_raises(self):
        StorageService.create_storage(_storage_data())
        with pytest.raises(AppValidationError) as exc_info:
            StorageService.create_storage(_storage_data(storage_code="SC001", storage_name="另一个"))
        assert exc_info.value.error_code == "DUPLICATE_STORAGE_CODE"

    def test_create_duplicate_name_raises(self):
        StorageService.create_storage(_storage_data())
        with pytest.raises(AppValidationError) as exc_info:
            StorageService.create_storage(_storage_data(storage_code="SC002", storage_name="测试仓库"))
        assert exc_info.value.error_code == "DUPLICATE_STORAGE_NAME"


@pytest.mark.django_db
class TestDeleteStorage:
    def test_delete_success(self):
        StorageService.create_storage(_storage_data())
        StorageService.delete_storage("SC001")
        assert Storage.all_objects.filter(storage_code="SC001", is_deleted=True).exists()

    def test_delete_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            StorageService.delete_storage("NOPE")
        assert exc_info.value.error_code == "STORAGE_NOT_FOUND"

    def test_delete_already_deleted_raises(self):
        StorageService.create_storage(_storage_data())
        StorageService.delete_storage("SC001")
        with pytest.raises(AppValidationError):
            StorageService.delete_storage("SC001")

    def test_delete_with_related_assets_raises(self):
        s = StorageService.create_storage(_storage_data())
        at = AssetType.objects.create(type_code="AT_S", type_name="AT_S")
        Asset.objects.create(
            asset_code="A_S",
            asset_name="A_S",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=s,
            asset_type_recordcode=at,
        )
        with pytest.raises(AppValidationError) as exc_info:
            StorageService.delete_storage("SC001")
        assert exc_info.value.error_code == "HAS_RELATED_ASSETS"


@pytest.mark.django_db
class TestBatchCreateStorage:
    def test_batch_create_success(self):
        data = [
            _storage_data(storage_code="BS1", storage_name="批量1"),
            _storage_data(storage_code="BS2", storage_name="批量2"),
        ]
        result = StorageService.batch_create_storage(data)
        assert result["total"] == 2
        assert result["success_count"] == 2

    def test_batch_create_with_duplicate(self):
        StorageService.create_storage(_storage_data())
        data = [
            _storage_data(storage_code="SC001", storage_name="Dup"),
            _storage_data(storage_code="BSNEW", storage_name="BSNew"),
        ]
        result = StorageService.batch_create_storage(data)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1

    def test_batch_create_exceeds_limit_raises(self):
        data = [_storage_data(storage_code=f"S{i}", storage_name=f"S{i}") for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            StorageService.batch_create_storage(data)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestBatchDeleteStorage:
    def test_batch_delete_success(self):
        StorageService.create_storage(_storage_data(storage_code="BD1", storage_name="BD1"))
        StorageService.create_storage(_storage_data(storage_code="BD2", storage_name="BD2"))
        result = StorageService.batch_delete_storage(["BD1", "BD2"])
        assert result["success_count"] == 2

    def test_batch_delete_with_nonexistent(self):
        StorageService.create_storage(_storage_data(storage_code="BD3", storage_name="BD3"))
        result = StorageService.batch_delete_storage(["BD3", "NOPE"])
        assert result["success_count"] == 1
        assert result["fail_count"] == 1


@pytest.mark.django_db
class TestStorageAuditLogOperator:
    def test_create_records_operator(self):
        StorageService.create_storage(
            _storage_data(),
            operator_jobcode="OP001",
            operator_name="操作员A",
        )
        log = AuditLog.objects.filter(
            record_code="SC001",
            operation_type="create",
            app_label="storage",
        ).first()
        assert log is not None
        assert log.operator_jobcode == "OP001"
        assert log.operator_name == "操作员A"

    def test_delete_records_operator(self):
        StorageService.create_storage(_storage_data())
        StorageService.delete_storage("SC001", operator_jobcode="OP002", operator_name="操作员B")
        log = AuditLog.objects.filter(
            record_code="SC001",
            operation_type="delete",
            app_label="storage",
        ).first()
        assert log is not None
        assert log.operator_jobcode == "OP002"
        assert log.operator_name == "操作员B"

    def test_batch_create_records_operator(self):
        data = [_storage_data(storage_code="BA1", storage_name="BA1")]
        StorageService.batch_create_storage(data, operator_jobcode="OP003", operator_name="操作员C")
        log = AuditLog.objects.filter(
            record_code="BA1",
            operation_type="create",
            app_label="storage",
        ).first()
        assert log is not None
        assert log.operator_jobcode == "OP003"

    def test_batch_delete_records_operator(self):
        StorageService.create_storage(_storage_data(storage_code="BD_A", storage_name="BD_A"))
        StorageService.batch_delete_storage(["BD_A"], operator_jobcode="OP004", operator_name="操作员D")
        log = AuditLog.objects.filter(
            record_code="BD_A",
            operation_type="delete",
            app_label="storage",
        ).first()
        assert log is not None
        assert log.operator_jobcode == "OP004"
