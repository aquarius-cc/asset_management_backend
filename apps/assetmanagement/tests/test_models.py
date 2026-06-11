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
        assert asset.asset_code == 'A001'
        assert asset.asset_name == '测试资产'
        assert asset.asset_current_status == 'in_store'
        # 【修复】asset_type_code 是 ForeignKey，需通过 .asset_type_code 访问编码
        assert asset.asset_type_code.asset_type_code == 'AT001'

    def test_asset_str(self, asset):
        """
        测试资产字符串表示

        Asset.__str__ 返回 f"{self.asset_name}({self.asset_code})"
        """
        assert str(asset) == '测试资产(A001)'

    def test_asset_unique_code(self, asset, storage, asset_type):
        """
        测试资产编码唯一性

        【修复】添加 asset_type_code 必填外键
        """
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Asset.objects.create(
                asset_code='A001',  # 重复编码
                asset_name='另一个资产',
                asset_purchase_price=2000.00,
                asset_purchase_date='2024-01-01',
                asset_entry_date='2024-01-15',
                asset_storage_code=storage,
                asset_type_code=asset_type,
            )
