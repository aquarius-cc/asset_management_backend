"""
回收/待报废/已报废选择器测试
"""

import pytest

from apps.assetmanagement.models import DamagedAsset, OutAsset, RecycleAsset, WasteAsset
from apps.assetmanagement.selectors.outasset_selector import (
    DamagedAssetSelector,
    RecycleAssetSelector,
    WasteAssetSelector,
)
from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


@pytest.mark.django_db
class TestRecycleAssetSelector:
    """回收资产选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = RecycleAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_all_asset_recordcodes(self, asset, user):
        """获取所有资产记录码"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        queryset = RecycleAssetSelector.get_all_asset_recordcodes()
        assert queryset.count() == 1

    def test_get_asset_recordcode_by_record_code(self, asset, user):
        """按 recordcode 获取回收记录"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        recycle = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        result = RecycleAssetSelector.get_asset_recordcode_by_record_code(recycle.recordcode)
        assert result is not None
        assert result.recordcode == recycle.recordcode

    def test_get_asset_recordcode_by_record_code_not_found(self):
        """按 recordcode 获取不存在的回收记录"""
        result = RecycleAssetSelector.get_asset_recordcode_by_record_code("notexist")
        assert result is None

    def test_exists_by_outasset(self, asset, user):
        """检查出库记录是否有回收记录"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        assert RecycleAssetSelector.exists_by_outasset(outasset.recordcode) is True
        assert RecycleAssetSelector.exists_by_outasset("notexist") is False

    def test_get_by_asset_code(self, asset, user):
        """按资产编码获取回收记录"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        queryset = RecycleAssetSelector.get_by_asset_code("A001")
        assert queryset.count() == 1


@pytest.mark.django_db
class TestDamagedAssetSelector:
    """待报废资产选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = DamagedAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_all_asset_recordcodes(self, asset, user):
        """获取所有资产记录码"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        queryset = DamagedAssetSelector.get_all_asset_recordcodes()
        assert queryset.count() == 1

    def test_get_asset_recordcode_by_asset_code(self, asset, user):
        """按资产编码获取报废记录"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        result = DamagedAssetSelector.get_asset_recordcode_by_asset_code("A001")
        assert result is not None

    def test_get_asset_recordcode_by_asset_code_not_found(self):
        """按资产编码获取不存在的报废记录"""
        result = DamagedAssetSelector.get_asset_recordcode_by_asset_code("NOTEXIST")
        assert result is None

    def test_exists_by_asset_code(self, asset, user):
        """检查资产编码是否有报废记录"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        assert DamagedAssetSelector.exists_by_asset_code("A001") is True
        assert DamagedAssetSelector.exists_by_asset_code("NOTEXIST") is False

    def test_get_by_asset_code(self, asset, user):
        """按资产编码获取报废记录"""
        _ = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        queryset = DamagedAssetSelector.get_by_asset_code("A001")
        assert queryset.count() == 1


@pytest.mark.django_db
class TestWasteAssetSelector:
    """已报废资产选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        # 先创建 DamagedAsset
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        _ = WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_date="2024-01-01",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = WasteAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_all_asset_recordcodes(self, asset, user):
        """获取所有资产记录码"""
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        _ = WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_date="2024-01-01",
        )
        queryset = WasteAssetSelector.get_all_asset_recordcodes()
        assert queryset.count() == 1

    def test_get_asset_recordcode_by_asset_code(self, asset, user):
        """按资产编码获取报废记录"""
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        _ = WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_date="2024-01-01",
        )
        result = WasteAssetSelector.get_asset_recordcode_by_asset_code("A001")
        assert result is not None

    def test_get_asset_recordcode_by_asset_code_not_found(self):
        """按资产编码获取不存在的报废记录"""
        result = WasteAssetSelector.get_asset_recordcode_by_asset_code("NOTEXIST")
        assert result is None

    def test_get_by_asset_code(self, asset, user):
        """按资产编码获取报废记录"""
        damaged = DamagedAsset.objects.create(
            asset_recordcode=asset,
        )
        _ = WasteAsset.objects.create(
            asset_recordcode=asset,
            damaged_recordcode=damaged,
            waste_asset_date="2024-01-01",
        )
        queryset = WasteAssetSelector.get_by_asset_code("A001")
        assert queryset.count() == 1
