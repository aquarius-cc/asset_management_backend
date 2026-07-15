"""资产类型管理服务测试"""

import pytest
from unittest.mock import patch, MagicMock

from apps.assetmanagement.models import AssetType, MAX_ASSET_TYPE_LEVEL
from apps.assetmanagement.services.asset_type_service import AssetTypeService
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestAssetTypeServiceGeneratePath:
    def test_generate_path(self):
        result = AssetTypeService._generate_path("/AT001", "AT002")
        assert result == "/AT001/AT002"

    def test_generate_path_root(self):
        result = AssetTypeService._generate_path("/", "ROOT")
        assert result == "//ROOT"


@pytest.mark.django_db
class TestCreateAssetType:
    def test_create_root_type(self):
        data = {"type_code": "NEW_TYPE", "type_name": "新类型"}
        result = AssetTypeService.create_asset_type(data)
        assert result.type_code == "NEW_TYPE"
        assert result.type_name == "新类型"
        assert result.level == 0
        assert result.path == "/NEW_TYPE"
        assert result.parent is None

    def test_create_duplicate_code_raises(self):
        AssetTypeService.create_asset_type({"type_code": "DUP", "type_name": "Dup"})
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.create_asset_type({"type_code": "DUP", "type_name": "Dup2"})
        assert exc_info.value.error_code == "DUPLICATE_ASSET_TYPE_CODE"

    def test_create_with_parent_by_type_code(self):
        parent = AssetTypeService.create_asset_type({"type_code": "PARENT", "type_name": "父级"})
        child = AssetTypeService.create_asset_type(
            {"type_code": "CHILD", "type_name": "子级", "parent_type_code": "PARENT"}
        )
        assert child.level == 1
        assert child.parent == parent
        assert "CHILD" in child.path

    def test_create_with_nonexistent_parent_type_code_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.create_asset_type(
                {"type_code": "ORPHAN", "type_name": "孤儿", "parent_type_code": "NONEXIST"}
            )
        assert exc_info.value.error_code == "PARENT_ASSET_TYPE_NOT_FOUND"

    def test_create_with_parent_by_recordcode(self):
        parent = AssetTypeService.create_asset_type({"type_code": "P2", "type_name": "父2"})
        child = AssetTypeService.create_asset_type(
            {"type_code": "C2", "type_name": "子2", "parent": parent.recordcode}
        )
        assert child.level == 1
        assert child.parent == parent

    def test_create_with_nonexistent_parent_rc_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.create_asset_type(
                {"type_code": "X", "type_name": "X", "parent": "NONEXIST_RC"}
            )
        assert exc_info.value.error_code == "PARENT_ASSET_TYPE_NOT_FOUND"

    @patch("apps.assetmanagement.services.asset_type_service.MAX_ASSET_TYPE_LEVEL", 0)
    def test_create_exceeds_max_level_raises(self):
        parent = AssetTypeService.create_asset_type({"type_code": "L0", "type_name": "L0"})
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.create_asset_type(
                {"type_code": "L1", "type_name": "L1", "parent_type_code": "L0"}
            )
        assert exc_info.value.error_code == "ASSET_TYPE_LEVEL_EXCEEDED"

    def test_create_removes_parent_code_field(self):
        data = {"type_code": "PC", "type_name": "PC", "parent_code": "OLD_CODE"}
        result = AssetTypeService.create_asset_type(data)
        assert result.type_code == "PC"


@pytest.mark.django_db
class TestDeleteAssetType:
    def test_delete_success(self):
        at = AssetTypeService.create_asset_type({"type_code": "DEL", "type_name": "删除"})
        AssetTypeService.delete_asset_type("DEL")
        assert AssetType.all_objects.filter(type_code="DEL", is_deleted=True).exists()

    def test_delete_nonexistent_raises(self):
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.delete_asset_type("NOPE")
        assert exc_info.value.error_code == "ASSET_TYPE_NOT_FOUND"

    def test_delete_already_deleted_raises(self):
        at = AssetTypeService.create_asset_type({"type_code": "DEL2", "type_name": "Del2"})
        AssetTypeService.delete_asset_type("DEL2")
        with pytest.raises(AppValidationError):
            AssetTypeService.delete_asset_type("DEL2")

    def test_delete_with_related_assets_raises(self, db):
        from apps.assetmanagement.models import Asset, Storage
        at = AssetTypeService.create_asset_type({"type_code": "USED", "type_name": "Used"})
        storage = Storage.objects.create(
            storage_code="S_DEL", storage_name="Del仓库",
            storage_address="addr", storage_capacity=100, sort_order=0,
        )
        Asset.objects.create(
            asset_code="A_DEL", asset_name="测试", asset_purchase_price=100,
            asset_purchase_date="2024-01-01", asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage, asset_type_recordcode=at,
        )
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.delete_asset_type("USED")
        assert exc_info.value.error_code == "HAS_RELATED_ASSETS"


@pytest.mark.django_db
class TestBatchCreateAssetType:
    def test_batch_create_success(self):
        data = [
            {"type_code": "B1", "type_name": "批量1"},
            {"type_code": "B2", "type_name": "批量2"},
        ]
        result = AssetTypeService.batch_create_asset_type(data)
        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["fail_count"] == 0

    def test_batch_create_with_duplicate(self):
        AssetTypeService.create_asset_type({"type_code": "BDUP", "type_name": "BDup"})
        data = [
            {"type_code": "BDUP", "type_name": "BDup2"},
            {"type_code": "BNEW", "type_name": "BNew"},
        ]
        result = AssetTypeService.batch_create_asset_type(data)
        assert result["success_count"] == 1
        assert result["fail_count"] == 1

    def test_batch_create_exceeds_limit_raises(self):
        data = [{"type_code": f"T{i}", "type_name": f"T{i}"} for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            AssetTypeService.batch_create_asset_type(data)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestBatchDeleteAssetType:
    def test_batch_delete_success(self):
        at1 = AssetTypeService.create_asset_type({"type_code": "BD1", "type_name": "BD1"})
        at2 = AssetTypeService.create_asset_type({"type_code": "BD2", "type_name": "BD2"})
        result = AssetTypeService.batch_delete_asset_type(["BD1", "BD2"])
        assert result["success_count"] == 2

    def test_batch_delete_with_nonexistent(self):
        at = AssetTypeService.create_asset_type({"type_code": "BD3", "type_name": "BD3"})
        result = AssetTypeService.batch_delete_asset_type(["BD3", "NOPE"])
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
