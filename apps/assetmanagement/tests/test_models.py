# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\test_models.py
"""
资产模型测试
"""

import pytest

from apps.assetmanagement.models import Asset


@pytest.mark.django_db
class TestAssetModel:
    """
    资产模型测试
    """

    def test_create_asset(self, asset):
        """
        测试创建资产
        """
        assert asset.asset_code == "A001"
        assert asset.asset_name == "测试资产"
        assert asset.asset_current_status == "in_store"
        # asset_type_recordcode 是 ForeignKey,需通过 .asset_type_recordcode 访问关联对象
        assert asset.asset_type_recordcode.type_code == "AT001"

    def test_asset_str(self, asset):
        """
        测试资产字符串表示

        Asset.__str__ 返回 f"{self.asset_name}({self.asset_code})"
        """
        assert str(asset) == "测试资产(A001)"

    def test_asset_soft_delete_and_reuse_code(self, asset, storage, asset_type):
        """
        测试资产软删除后可复用编码

        【说明】PostgreSQL 会执行条件唯一约束(仅未软删除记录),此测试验证软删除后的编码复用功能
        """
        # 软删除资产
        asset.is_deleted = True
        asset.save(update_fields=["is_deleted"])

        # 创建相同编码的新资产(软删除后应允许)
        new_asset = Asset.objects.create(
            asset_code="A001",  # 相同编码
            asset_name="新资产",
            asset_purchase_price=2000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
        )
        assert new_asset.asset_code == "A001"
        assert new_asset.asset_name == "新资产"
