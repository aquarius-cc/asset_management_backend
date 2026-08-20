"""
出库/回收/报废选择器测试
"""

import pytest

from apps.assetmanagement.models import (
    BrokenAsset,
    DamagedAsset,
    FoundAsset,
    LostAsset,
    OutAsset,
    RecycleAsset,
    RepairAsset,
    WasteAsset,
)
from apps.assetmanagement.selectors.outasset_selector import (
    BrokenAssetSelector,
    DamagedAssetSelector,
    FoundAssetSelector,
    LostAssetSelector,
    OutAssetSelector,
    RecycleAssetSelector,
    RepairAssetSelector,
    WasteAssetSelector,
)
from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


@pytest.mark.django_db
class TestOutAssetSelector:
    """出库记录选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password=TEST_PASSWORD)
        user.auth_user = auth_user
        user.save()

        queryset = OutAssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_outassets_for_list(self, asset, user):
        """获取列表视图的出库记录"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_outassets_for_list()
        assert queryset.count() == 1

    def test_get_outassets_with_asset_details(self, asset, user):
        """获取包含资产详情的出库记录"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_outassets_with_asset_details()
        assert queryset.count() == 1

    def test_get_asset_recordcodes_for_list(self, asset, user):
        """获取资产记录码列表"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_asset_recordcodes_for_list()
        assert queryset.count() == 1

    def test_get_asset_recordcodes_with_asset_details(self, asset, user):
        """获取包含资产详情的记录码列表"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_asset_recordcodes_with_asset_details()
        assert queryset.count() == 1

    def test_get_recyclable_outassets(self, asset, user):
        """获取可回收的出库记录"""
        # 设置资产状态为 in_use(出库后的状态)
        asset.asset_current_status = "in_use"
        asset.asset_applicant_recordcode = user
        asset.asset_manager_recordcode = user
        asset.save(update_fields=["asset_current_status", "asset_applicant_recordcode", "asset_manager_recordcode"])
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_recyclable_outassets()
        # 资产状态是 in_use,应该返回
        assert queryset.count() == 1

    def test_get_all_out_assets(self, asset, user):
        """获取所有出库记录"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_all_out_assets()
        assert queryset.count() == 1

    def test_get_outasset_by_record_code(self, asset, user):
        """按 recordcode 获取出库记录"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        result = OutAssetSelector.get_outasset_by_record_code(outasset.recordcode)
        assert result is not None
        assert result.recordcode == outasset.recordcode

    def test_get_outasset_by_record_code_not_found(self):
        """按 recordcode 获取不存在的出库记录"""
        result = OutAssetSelector.get_outasset_by_record_code("notexist")
        assert result is None

    def test_get_outassets_by_applicant(self, asset, user):
        """按申请人获取出库记录"""
        # 设置资产的申请人
        asset.asset_applicant_recordcode = user
        asset.save(update_fields=["asset_applicant_recordcode"])
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_outassets_by_applicant(user.employee_jobcode)
        assert queryset.count() == 1

    def test_get_outassets_by_asset(self, asset, user):
        """按资产编码获取出库记录"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_outassets_by_asset("A001")
        assert queryset.count() == 1

    def test_get_outassets_by_status(self, asset, user):
        """按状态获取出库记录"""
        # 设置资产状态为 in_use
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        queryset = OutAssetSelector.get_outassets_by_status("in_use")
        assert queryset.count() == 1

    def test_get_active_outasset_by_asset(self, asset, user):
        """获取资产的活动出库记录"""
        # 设置资产状态为 in_use
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        result = OutAssetSelector.get_active_outasset_by_asset("A001")
        assert result is not None

    def test_get_outasset_by_asset_and_status(self, asset, user):
        """按资产和状态获取出库记录"""
        # 设置资产状态为 in_use
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        result = OutAssetSelector.get_outasset_by_asset_and_status(asset, ["in_use"])
        assert result is not None

    def test_get_outasset_statistics(self, asset, user):
        """获取出库统计信息"""
        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        stats = OutAssetSelector.get_outasset_statistics()
        assert "total_outassets" in stats
        assert "by_type" in stats
        assert stats["total_outassets"] == 1


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

    def test_get_asset_recordcodes_for_list(self, asset, user):
        """获取资产记录码列表"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        queryset = RecycleAssetSelector.get_asset_recordcodes_for_list()
        assert queryset.count() == 1

    def test_get_asset_recordcodes_with_asset_details(self, asset, user):
        """获取包含资产详情的记录码列表"""
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        queryset = RecycleAssetSelector.get_asset_recordcodes_with_asset_details()
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
