# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\test_selectors.py
"""
资产查询选择器测试
"""

import pytest

from apps.assetmanagement.selectors import AssetSelector


@pytest.mark.django_db
class TestAssetSelector:
    """
    资产查询选择器测试
    """

    def test_get_available_assets(self, asset):
        """
        测试获取可用资产

        【修复】asset_type_code 是 ForeignKey,需通过 .type_code 访问编码
        """
        available = AssetSelector.get_available_assets()

        assert available.count() >= 1
        assert available.first().asset_code == "A001"
        assert available.first().asset_type_recordcode.type_code == "AT001"

    def test_get_assets_by_status(self, asset):
        """
        测试按状态获取资产

        【修复】asset_type_code 是 ForeignKey,需通过 .type_code 访问编码
        """
        in_store_assets = AssetSelector.get_assets_by_status("in_store")

        assert in_store_assets.count() >= 1
        assert in_store_assets.first().asset_code == "A001"
        assert in_store_assets.first().asset_type_recordcode.type_code == "AT001"

    def test_get_asset_by_code(self, asset):
        """
        测试通过编码获取资产

        【修复】asset_type_code 是 ForeignKey,需通过 .type_code 访问编码
        """
        result = AssetSelector.get_asset_by_code("A001")

        assert result is not None
        assert result.asset_code == "A001"
        assert result.asset_type_recordcode.type_code == "AT001"

    def test_get_asset_by_code_not_found(self):
        """
        测试获取不存在的资产
        """
        result = AssetSelector.get_asset_by_code("NONEXISTENT")

        assert result is None

    def test_search_assets(self, asset):
        """
        测试搜索资产

        【修复】asset_type_code 是 ForeignKey,需通过 .type_code 访问编码
        """
        results = AssetSelector.search_assets(keyword="测试")

        assert results.count() >= 1
        assert results.first().asset_code == "A001"
        assert results.first().asset_type_recordcode.type_code == "AT001"

    def test_search_assets_by_status(self, asset):
        """
        测试按状态搜索资产

        【修复】asset_type_code 是 ForeignKey,需通过 .type_code 访问编码
        """
        results = AssetSelector.search_assets(status="in_store")

        assert results.count() >= 1
        assert all(a.asset_current_status == "in_store" for a in results)
        assert all(a.asset_type_recordcode.type_code == "AT001" for a in results)
