"""
损坏/遗失/找回/维修选择器测试
"""

import pytest

from apps.assetmanagement.models import BrokenAsset, FoundAsset, LostAsset, RepairAsset
from apps.assetmanagement.selectors.outasset_selector import (
    BrokenAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
    RepairAssetSelector,
)
from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


@pytest.mark.django_db
class TestBrokenAssetSelector:
    """损坏记录选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        _ = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason="测试损坏",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = BrokenAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_broken_assets_for_list(self, asset, user):
        """获取列表视图的损坏记录"""
        _ = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason="测试损坏",
        )
        queryset = BrokenAssetSelector.get_broken_assets_for_list()
        assert queryset.count() == 1

    def test_get_broken_assets_with_details(self, asset, user):
        """获取包含详情的损坏记录"""
        _ = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason="测试损坏",
        )
        queryset = BrokenAssetSelector.get_broken_assets_with_details()
        assert queryset.count() == 1

    def test_get_broken_asset_by_recordcode(self, asset, user):
        """按 recordcode 获取损坏记录"""
        broken = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason="测试损坏",
        )
        result = BrokenAssetSelector.get_broken_asset_by_recordcode(broken.recordcode)
        assert result is not None
        assert result.recordcode == broken.recordcode

    def test_get_broken_asset_by_recordcode_not_found(self):
        """按 recordcode 获取不存在的损坏记录"""
        result = BrokenAssetSelector.get_broken_asset_by_recordcode("notexist")
        assert result is None

    def test_exists_by_asset_code(self, asset, user):
        """检查资产编码是否有损坏记录"""
        _ = BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason="测试损坏",
        )
        assert BrokenAssetSelector.exists_by_asset_code("A001") is True
        assert BrokenAssetSelector.exists_by_asset_code("NOTEXIST") is False


@pytest.mark.django_db
class TestLostAssetSelector:
    """遗失记录选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        _ = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = LostAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_lost_assets_for_list(self, asset, user):
        """获取列表视图的遗失记录"""
        _ = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        queryset = LostAssetSelector.get_lost_assets_for_list()
        assert queryset.count() == 1

    def test_get_lost_assets_with_details(self, asset, user):
        """获取包含详情的遗失记录"""
        _ = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        queryset = LostAssetSelector.get_lost_assets_with_details()
        assert queryset.count() == 1

    def test_get_lost_asset_by_recordcode(self, asset, user):
        """按 recordcode 获取遗失记录"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        result = LostAssetSelector.get_lost_asset_by_recordcode(lost.recordcode)
        assert result is not None
        assert result.recordcode == lost.recordcode

    def test_get_lost_asset_by_recordcode_not_found(self):
        """按 recordcode 获取不存在的遗失记录"""
        result = LostAssetSelector.get_lost_asset_by_recordcode("notexist")
        assert result is None

    def test_exists_by_asset_code(self, asset, user):
        """检查资产编码是否有遗失记录"""
        _ = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        assert LostAssetSelector.exists_by_asset_code("A001") is True
        assert LostAssetSelector.exists_by_asset_code("NOTEXIST") is False


@pytest.mark.django_db
class TestFoundAssetSelector:
    """找回记录选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        _ = FoundAsset.objects.create(
            asset_recordcode=asset,
            lost_asset_recordcode=lost,
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = FoundAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_found_assets_for_list(self, asset, user):
        """获取列表视图的找回记录"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        _ = FoundAsset.objects.create(
            asset_recordcode=asset,
            lost_asset_recordcode=lost,
        )
        queryset = FoundAssetSelector.get_found_assets_for_list()
        assert queryset.count() == 1

    def test_get_found_assets_with_details(self, asset, user):
        """获取包含详情的找回记录"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        _ = FoundAsset.objects.create(
            asset_recordcode=asset,
            lost_asset_recordcode=lost,
        )
        queryset = FoundAssetSelector.get_found_assets_with_details()
        assert queryset.count() == 1

    def test_get_found_asset_by_recordcode(self, asset, user):
        """按 recordcode 获取找回记录"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        found = FoundAsset.objects.create(
            asset_recordcode=asset,
            lost_asset_recordcode=lost,
        )
        result = FoundAssetSelector.get_found_asset_by_recordcode(found.recordcode)
        assert result is not None
        assert result.recordcode == found.recordcode

    def test_get_found_asset_by_recordcode_not_found(self):
        """按 recordcode 获取不存在的找回记录"""
        result = FoundAssetSelector.get_found_asset_by_recordcode("notexist")
        assert result is None

    def test_exists_by_lost_asset_recordcode(self, asset, user):
        """检查遗失记录是否有找回记录"""
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason="测试遗失",
        )
        _ = FoundAsset.objects.create(
            asset_recordcode=asset,
            lost_asset_recordcode=lost,
        )
        assert FoundAssetSelector.exists_by_lost_asset_recordcode(lost.recordcode) is True
        assert FoundAssetSelector.exists_by_lost_asset_recordcode("notexist") is False


@pytest.mark.django_db
class TestRepairAssetSelector:
    """维修记录选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        _ = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-01-01",
            repair_reason="测试维修",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = RepairAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_repair_assets_for_list(self, asset, user):
        """获取列表视图的维修记录"""
        _ = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-01-01",
            repair_reason="测试维修",
        )
        queryset = RepairAssetSelector.get_repair_assets_for_list()
        assert queryset.count() == 1

    def test_get_repair_asset_by_recordcode(self, asset, user):
        """按 recordcode 获取维修记录"""
        repair = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-01-01",
            repair_reason="测试维修",
        )
        result = RepairAssetSelector.get_repair_asset_by_recordcode(repair.recordcode)
        assert result is not None
        assert result.recordcode == repair.recordcode

    def test_get_repair_asset_by_recordcode_not_found(self):
        """按 recordcode 获取不存在的维修记录"""
        result = RepairAssetSelector.get_repair_asset_by_recordcode("notexist")
        assert result is None

    def test_exists_by_asset_code(self, asset, user):
        """检查资产编码是否有维修记录"""
        _ = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date="2024-01-01",
            repair_reason="测试维修",
        )
        assert RepairAssetSelector.exists_by_asset_code("A001") is True
        assert RepairAssetSelector.exists_by_asset_code("NOTEXIST") is False
