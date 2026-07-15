"""
未登记资产选择器测试

测试 UnregisteredAssetSelector 的：
- 根据编码获取
- 根据 ID 获取
- 列表筛选
- 存在性检查
"""

from datetime import date

import pytest

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.selectors import UnregisteredAssetSelector


@pytest.mark.django_db
class TestUnregisteredAssetSelector:
    """
    未登记资产选择器测试类
    """

    def test_get_by_code_exists(self, unregistered_asset_s1):
        """
        测试根据编码获取存在的记录
        """
        result = UnregisteredAssetSelector.get_by_code(unregistered_asset_s1.unregistered_code)

        assert result is not None
        assert result.id == unregistered_asset_s1.id

    def test_get_by_code_not_exists(self):
        """
        测试根据编码获取不存在的记录
        """
        result = UnregisteredAssetSelector.get_by_code("UNR-NOTEXIST")
        assert result is None

    def test_get_by_code_soft_deleted(self, unregistered_asset_s1):
        """
        测试根据编码获取已软删除的记录
        """
        code = unregistered_asset_s1.unregistered_code
        unregistered_asset_s1.delete()

        result = UnregisteredAssetSelector.get_by_code(code)
        assert result is None

    def test_get_by_id_exists(self, unregistered_asset_s1):
        """
        测试根据 ID 获取存在的记录
        """
        result = UnregisteredAssetSelector.get_by_id(unregistered_asset_s1.id)

        assert result is not None
        assert result.unregistered_code == unregistered_asset_s1.unregistered_code

    def test_get_by_id_not_exists(self):
        """
        测试根据 ID 获取不存在的记录
        """
        result = UnregisteredAssetSelector.get_by_id(99999)
        assert result is None

    def test_list_by_filters_empty(self, db):
        """
        测试无筛选条件返回所有记录
        """
        queryset = UnregisteredAssetSelector.list_by_filters()
        assert queryset.count() == 0

    def test_list_by_filters_scenario_type(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试按场景类型筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(scenario_type="s1_no_record")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_list_by_filters_approval_status(self, unregistered_asset_s1, approved_unregistered_asset):
        """
        测试按审批状态筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(approval_status="pending")

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_by_filters_discovery_person(self, unregistered_asset_s1, employee):
        """
        测试按发现人筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(discovery_person=employee.employee_jobcode)

        assert queryset.count() == 1
        assert queryset.first().discovery_person == employee

    def test_list_by_filters_combined(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试组合筛选条件
        """
        queryset = UnregisteredAssetSelector.list_by_filters(scenario_type="s1_no_record", approval_status="pending")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_list_by_discovery_person(self, unregistered_asset_s1, employee):
        """
        测试按发现人获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_discovery_person(discovery_person=employee.employee_jobcode)

        assert queryset.count() == 1

    def test_list_by_discovery_person_with_status(self, unregistered_asset_s1, approved_unregistered_asset, employee):
        """
        测试按发现人和状态获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_discovery_person(
            discovery_person=employee.employee_jobcode, approval_status="pending"
        )

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_pending(self, unregistered_asset_s1, approved_unregistered_asset):
        """
        测试获取待审批列表
        """
        queryset = UnregisteredAssetSelector.list_pending()

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_by_scenario(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试按场景类型获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_scenario("s1_no_record")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_exists_by_code_true(self, unregistered_asset_s1):
        """
        测试存在性检查 - 存在
        """
        exists = UnregisteredAssetSelector.exists_by_code(unregistered_asset_s1.unregistered_code)
        assert exists is True

    def test_exists_by_code_false(self):
        """
        测试存在性检查 - 不存在
        """
        exists = UnregisteredAssetSelector.exists_by_code("UNR-NOTEXIST")
        assert exists is False

    def test_exists_by_code_soft_deleted(self, unregistered_asset_s1):
        """
        测试存在性检查 - 已软删除
        """
        code = unregistered_asset_s1.unregistered_code
        unregistered_asset_s1.delete()

        exists = UnregisteredAssetSelector.exists_by_code(code)
        assert exists is False

    def test_ordering_by_created_at_desc(self, employee, storage):
        """
        测试按创建时间倒序排列
        """
        # 创建两个记录
        asset1 = UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 1),
            discovery_location="地点1",
            discovery_person=employee,
            asset_name="资产1",
            unregistered_asset_storage=storage,
        )

        asset2 = UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 2),
            discovery_location="地点2",
            discovery_person=employee,
            asset_name="资产2",
            unregistered_asset_storage=storage,
        )

        queryset = UnregisteredAssetSelector.list_by_filters()

        # 验证倒序排列
        assert queryset.first().id == asset2.id
        assert queryset.last().id == asset1.id
