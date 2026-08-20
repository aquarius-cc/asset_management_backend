"""
批量创建资产 API 测试

测试 AssetBatchCreateSerializer 和 AssetBatchItemSerializer 的正确性:
1. slug_field 正确使用业务编码(asset_type_code/storage_code/contract_code/employee_jobcode)
2. DRF 自动将业务编码转换为 recordcode
3. 删除了不存在的字段(asset_remark/asset_department_code)
4. asset_entry_person 字段名正确
"""

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.assetmanagement.serializers.asset_batch_serializers import (
    AssetBatchCreateSerializer,
    AssetBatchItemSerializer,
)
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.tests import TEST_PASSWORD


@pytest.fixture
def batch_data(db):
    """批量创建测试所需的基础数据"""
    department = Department.objects.create(department_code="DEPT001", department_name="技术部")
    asset_type = AssetType.objects.create(type_code="AT001", type_name="台式机")
    storage = Storage.objects.create(storage_code="ST001", storage_name="新货仓库")
    contract = Contract.objects.create(
        contract_code="CT001",
        contract_name="采购合同-001",
        contract_type="tender_procurement",
        contract_amount=100000,
        supplier_name="供应商A",
    )
    employee = Employee.objects.create(
        employee_jobcode="E001",
        employee_name="张三",
        employee_status="active",
        employee_department=department,
        employee_phone="13800138000",
    )
    return {
        "department": department,
        "asset_type": asset_type,
        "storage": storage,
        "contract": contract,
        "employee": employee,
    }


@pytest.fixture
def admin_client(db):
    """管理员认证客户端"""
    user = AuthUser.objects.create_superuser(auth_username="testadmin", password=TEST_PASSWORD)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestAssetBatchItemSerializer:
    """AssetBatchItemSerializer 序列化器测试"""

    def test_serializer_should_accept_asset_type_code(self, batch_data):
        """序列化器应接受 asset_type_code 并自动转换为 recordcode"""
        data = {
            "asset_name": "台式机-001",
            "asset_type": "AT001",
            "asset_storage": "ST001",
            "asset_contract": "CT001",
            "asset_entry_person": "E001",
            "asset_purchase_price": 5000.00,
            "asset_purchase_date": "2026-06-27",
            "asset_entry_date": "2026-06-27",
        }
        serializer = AssetBatchItemSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

        validated = serializer.validated_data
        assert validated["asset_type_recordcode"].recordcode == batch_data["asset_type"].recordcode
        assert validated["asset_storage_recordcode"].recordcode == batch_data["storage"].recordcode
        assert validated["asset_contract_recordcode"].recordcode == batch_data["contract"].recordcode
        assert validated["asset_entry_person_recordcode"].recordcode == batch_data["employee"].recordcode

    def test_serializer_should_reject_nonexistent_asset_type_code(self):
        """序列化器应拒绝不存在的 asset_type_code"""
        data = {"asset_name": "台式机-002", "asset_type": "NONEXIST"}
        serializer = AssetBatchItemSerializer(data=data)
        assert not serializer.is_valid()
        assert "asset_type" in serializer.errors

    def test_serializer_should_accept_optional_fields(self, batch_data):
        """序列化器应接受可选字段"""
        data = {
            "asset_name": "台式机-003",
            "asset_type": "AT001",
            "asset_specification": "i7/16GB/512GB",
            "asset_brand": "联想",
            "asset_unit": "台",
        }
        serializer = AssetBatchItemSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_serializer_should_not_have_asset_remark_field(self):
        """序列化器不应包含 asset_remark 字段"""
        data = {"asset_name": "台式机-004", "asset_type": "AT001"}
        serializer = AssetBatchItemSerializer(data=data)
        assert "asset_remark" not in serializer.fields


@pytest.mark.django_db
class TestAssetBatchCreateSerializer:
    """AssetBatchCreateSerializer 序列化器测试"""

    def test_batch_serializer_should_validate_items(self, batch_data):
        """批量序列化器应验证 items 列表"""
        data = {
            "items": [
                {"asset_name": "台式机-001", "asset_type": "AT001"},
                {"asset_name": "台式机-002", "asset_type": "AT001"},
            ]
        }
        serializer = AssetBatchCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_batch_serializer_should_reject_empty_items(self):
        """批量序列化器应拒绝空 items"""
        serializer = AssetBatchCreateSerializer(data={"items": []})
        assert not serializer.is_valid()

    def test_batch_serializer_should_reject_duplicate_names(self, batch_data):
        """批量序列化器应拒绝重复的资产名称"""
        data = {
            "items": [
                {"asset_name": "台式机-001", "asset_type": "AT001"},
                {"asset_name": "台式机-001", "asset_type": "AT001"},
            ]
        }
        serializer = AssetBatchCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "items" in serializer.errors


@pytest.mark.django_db
class TestAssetBatchCreateAPI:
    """批量创建资产 API 集成测试"""

    def test_batch_create_should_work_with_business_codes(self, admin_client, batch_data):
        """批量创建 API 应正确处理业务编码"""
        data = {
            "items": [
                {
                    "asset_name": "台式机-001",
                    "asset_type": "AT001",
                    "asset_storage": "ST001",
                    "asset_contract": "CT001",
                    "asset_entry_person": "E001",
                    "asset_purchase_price": 5000.00,
                    "asset_purchase_date": "2026-06-27",
                    "asset_entry_date": "2026-06-27",
                    "asset_purchase_number": 1,
                }
            ]
        }
        response = admin_client.post("/api/v1/assets/assets/batch-create/", data, format="json")
        assert response.status_code == 200
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1
        assert response.data["data"]["fail_count"] == 0

        asset = Asset.objects.first()
        assert asset is not None
        assert asset.asset_name == "台式机-001"
        assert asset.asset_type_recordcode.recordcode == batch_data["asset_type"].recordcode
        assert asset.asset_storage_recordcode.recordcode == batch_data["storage"].recordcode
        assert asset.asset_contract_recordcode.recordcode == batch_data["contract"].recordcode
        assert asset.asset_entry_person_recordcode.recordcode == batch_data["employee"].recordcode

    def test_batch_create_should_create_multiple_assets(self, admin_client, batch_data):
        """批量创建 API 应支持批量创建"""
        data = {
            "items": [
                {
                    "asset_name": "台式机-001",
                    "asset_type": "AT001",
                    "asset_storage": "ST001",
                    "asset_purchase_price": 5000.00,
                    "asset_purchase_date": "2026-06-27",
                    "asset_entry_date": "2026-06-27",
                    "asset_purchase_number": 1,
                },
                {
                    "asset_name": "台式机-002",
                    "asset_type": "AT001",
                    "asset_storage": "ST001",
                    "asset_purchase_price": 6000.00,
                    "asset_purchase_date": "2026-06-27",
                    "asset_entry_date": "2026-06-27",
                    "asset_purchase_number": 1,
                },
            ]
        }
        response = admin_client.post("/api/v1/assets/assets/batch-create/", data, format="json")
        assert response.status_code == 200
        assert response.data["data"]["success_count"] == 2
        assert Asset.objects.count() == 2

    def test_batch_create_should_reject_invalid_asset_type(self, admin_client):
        """批量创建 API 应拒绝无效的 asset_type"""
        data = {"items": [{"asset_name": "台式机-001", "asset_type": "NONEXIST"}]}
        response = admin_client.post("/api/v1/assets/assets/batch-create/", data, format="json")
        assert response.status_code == 400

    def test_batch_create_should_handle_purchase_number(self, admin_client, batch_data):
        """批量创建 API 应正确处理 purchase_number"""
        data = {
            "items": [
                {
                    "asset_name": "台式机-001",
                    "asset_type": "AT001",
                    "asset_storage": "ST001",
                    "asset_purchase_price": 5000.00,
                    "asset_purchase_date": "2026-06-27",
                    "asset_entry_date": "2026-06-27",
                    "asset_purchase_number": 3,
                }
            ]
        }
        response = admin_client.post("/api/v1/assets/assets/batch-create/", data, format="json")
        assert response.status_code == 200
        assert response.data["data"]["success_count"] == 1
        assert Asset.objects.count() == 3

        assets = Asset.objects.all()
        for asset in assets:
            assert asset.asset_code.startswith("AT001-")
