"""
基础选择器测试
"""

import pytest

from apps.assetmanagement.models import Contract, HardDiskSN
from apps.assetmanagement.selectors.base_selector import (
    ContractSelector,
    DashboardSelector,
    HardDiskSNSelector,
    StorageSelector,
)
from apps.authusermanagement.models import AuthUser


@pytest.mark.django_db
class TestStorageSelector:
    """仓库选择器测试类"""

    def test_get_all_storages(self, storage):
        """获取所有仓库"""
        queryset = StorageSelector.get_all_storages()
        assert queryset.count() == 1

    def test_get_storage_by_code(self, storage):
        """按编码获取仓库"""
        result = StorageSelector.get_storage_by_code("S001")
        assert result is not None
        assert result.storage_code == "S001"

    def test_get_storage_by_code_not_found(self):
        """按编码获取不存在的仓库"""
        result = StorageSelector.get_storage_by_code("NOTEXIST")
        assert result is None

    def test_get_storages_by_type(self, storage):
        """按类型获取仓库"""
        # 测试仓库没有设置 storage_type,需要修改 fixture 或创建新仓库
        storage.storage_type = "newasset"
        storage.save()
        queryset = StorageSelector.get_storages_by_type("newasset")
        assert queryset.count() == 1

    def test_exists_by_code(self, storage):
        """检查仓库编码是否存在"""
        assert StorageSelector.exists_by_code("S001") is True
        assert StorageSelector.exists_by_code("NOTEXIST") is False

    def test_exists_by_name(self, storage):
        """检查仓库名称是否存在"""
        assert StorageSelector.exists_by_name("测试仓库") is True
        assert StorageSelector.exists_by_name("不存在") is False

    def test_search_storages_by_keyword(self, storage):
        """按关键词搜索仓库"""
        queryset = StorageSelector.search_storages_by_keyword("测试")
        assert queryset.count() == 1


@pytest.mark.django_db
class TestContractSelector:
    """合同选择器测试类"""

    def test_get_all_contracts(self, storage):
        """获取所有合同"""
        # 先创建合同
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        queryset = ContractSelector.get_all_contracts()
        assert queryset.count() == 1

    def test_get_contract_by_code(self, storage):
        """按编码获取合同"""
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        result = ContractSelector.get_contract_by_code("C001")
        assert result is not None
        assert result.contract_code == "C001"

    def test_get_contract_by_code_not_found(self):
        """按编码获取不存在的合同"""
        result = ContractSelector.get_contract_by_code("NOTEXIST")
        assert result is None

    def test_search_contracts(self, storage):
        """搜索合同"""
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        queryset = ContractSelector.search_contracts("测试")
        assert queryset.count() == 1

    def test_get_contracts_by_type(self, storage):
        """按类型获取合同"""
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        queryset = ContractSelector.get_contracts_by_type("tender_procurement")
        assert queryset.count() == 1

    def test_exists_by_code(self, storage):
        """检查合同编码是否存在"""
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        assert ContractSelector.exists_by_code("C001") is True
        assert ContractSelector.exists_by_code("NOTEXIST") is False

    def test_get_contract_statistics(self, storage):
        """获取合同统计信息"""
        _ = Contract.objects.create(
            contract_code="C001",
            contract_name="测试合同",
            contract_type="tender_procurement",
            contract_status="purchasing",
            contract_amount=10000.00,
        )
        stats = ContractSelector.get_contract_statistics()
        assert "total_contracts" in stats
        assert "total_value" in stats
        assert "by_type" in stats
        assert "by_status" in stats
        assert stats["total_contracts"] == 1


@pytest.mark.django_db
class TestHardDiskSNSelector:
    """硬盘序列号选择器测试类"""

    def test_get_queryset_for_user(self, asset, user):
        """RBAC 行级过滤"""
        # 创建硬盘
        _ = HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        # 模拟用户
        auth_user = AuthUser.objects.create_user(auth_username="test", password="test123")
        user.auth_user = auth_user
        user.save()

        queryset = HardDiskSNSelector.get_queryset_for_user(auth_user)
        assert queryset.count() == 1

    def test_get_by_recordcode(self, asset):
        """按 recordcode 查询硬盘"""
        harddisk = HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        result = HardDiskSNSelector.get_by_recordcode(harddisk.recordcode)
        assert result is not None
        assert result.harddisk_sn_code == "HD001"

    def test_get_by_recordcode_not_found(self):
        """按 recordcode 查询不存在的硬盘"""
        result = HardDiskSNSelector.get_by_recordcode("notexist")
        assert result is None

    def test_get_by_pk(self, asset):
        """按主键查询硬盘"""
        harddisk = HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        result = HardDiskSNSelector.get_by_pk(harddisk.pk)
        assert result is not None
        assert result.pk == harddisk.pk

    def test_get_by_pk_not_found(self):
        """按主键查询不存在的硬盘"""
        result = HardDiskSNSelector.get_by_pk(99999)
        assert result is None

    def test_get_by_sn_code(self, asset):
        """按序列号查询硬盘"""
        _ = HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        result = HardDiskSNSelector.get_by_sn_code("HD001")
        assert result is not None
        assert result.harddisk_sn_code == "HD001"

    def test_get_by_sn_code_not_found(self):
        """按序列号查询不存在的硬盘"""
        result = HardDiskSNSelector.get_by_sn_code("NOTEXIST")
        assert result is None

    def test_exists_by_sn_code(self, asset):
        """检查序列号是否存在"""
        _ = HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        assert HardDiskSNSelector.exists_by_sn_code("HD001") is True
        assert HardDiskSNSelector.exists_by_sn_code("NOTEXIST") is False

    def test_get_by_asset(self, asset):
        """查询某资产的所有硬盘"""
        HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        queryset = HardDiskSNSelector.get_by_asset(asset.recordcode)
        assert queryset.count() == 1

    def test_get_by_asset_code(self, asset):
        """按资产编码查询所有硬盘"""
        HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        queryset = HardDiskSNSelector.get_by_asset_code("A001")
        assert queryset.count() == 1

    def test_count_by_asset(self, asset):
        """统计某资产的硬盘数量"""
        HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        count = HardDiskSNSelector.count_by_asset(asset.recordcode)
        assert count == 1

    def test_get_by_status(self, asset):
        """按状态查询硬盘"""
        HardDiskSN.objects.create(
            harddisk_sn_code="HD001",
            asset_recordcode=asset,
            harddisk_status="normal",
        )
        queryset = HardDiskSNSelector.get_by_status("normal")
        assert queryset.count() == 1


@pytest.mark.django_db
class TestDashboardSelector:
    """仪表盘选择器测试类"""

    def test_get_statistics(self, asset):
        """获取统计信息"""
        stats = DashboardSelector.get_statistics()
        assert "total_assets" in stats
        assert "total_value" in stats
        assert "in_store" in stats
        assert "in_use" in stats
        assert "recycled_pending" in stats
        assert "damaged" in stats
        assert "scrapped" in stats
        assert stats["total_assets"] == 1

    def test_get_overview_statistics(self, asset):
        """获取概览统计信息"""
        stats = DashboardSelector.get_overview_statistics()
        assert "total_assets" in stats
        assert "total_value" in stats
        assert "total_contracts" in stats
        assert "active_assets" in stats

    def test_get_recent_out_assets(self, asset, user):
        """获取最近出库记录"""
        from apps.assetmanagement.models import OutAsset

        _ = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        result = DashboardSelector.get_recent_out_assets()
        assert len(result) == 1
        assert result[0]["asset_code"] == "A001"

    def test_get_recent_recycle_assets(self, asset, user):
        """获取最近回收记录"""
        from apps.assetmanagement.models import OutAsset, RecycleAsset

        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-01-01",
        )
        _ = RecycleAsset.objects.create(
            asset_recordcode=asset,
            outasset_recordcode=outasset,
            recycle_asset_date="2024-01-02",
        )
        result = DashboardSelector.get_recent_recycle_assets()
        assert len(result) == 1
        assert result[0]["asset_code"] == "A001"

    def test_get_asset_trend(self, asset):
        """获取资产趋势数据"""
        result = DashboardSelector.get_asset_trend(days=30)
        assert isinstance(result, list)
        assert len(result) >= 30
        assert result[0]["date"]
        assert "new_assets" in result[0]
        assert "distributed" in result[0]
        assert "recovered" in result[0]
        assert "scrapped" in result[0]

    def test_get_department_distribution(self, asset):
        """获取资产按部门分布统计"""
        result = DashboardSelector.get_department_distribution()
        assert isinstance(result, list)

    def test_get_type_distribution(self, asset, asset_type):
        """获取资产按类型分布统计"""
        result = DashboardSelector.get_type_distribution()
        assert isinstance(result, list)

    def test_get_expiring_assets(self, asset):
        """获取即将到期的资产"""
        result = DashboardSelector.get_expiring_assets()
        assert isinstance(result, list)

    def test_get_maintenance_reminders(self, asset):
        """获取维护提醒数据"""
        result = DashboardSelector.get_maintenance_reminders()
        assert isinstance(result, list)
