"""
出库/回收/报废选择器测试
"""

import pytest

from apps.assetmanagement.models import (
    OutAsset,
)
from apps.assetmanagement.selectors.outasset_selector import (
    OutAssetSelector,
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

    def test_get_recyclable_outassets_rbac_isolation(self, asset, user):
        """C-2 验证: get_recyclable_outassets 传入 user 后启用 RBAC 行级隔离"""
        from apps.assetmanagement.models import Asset, OutAsset
        from apps.assetmanagement.selectors.outasset_selector import OutAssetSelector
        from apps.usermanagement.models import Department, Employee

        # 创建第二个部门和用户
        dept_b = Department.objects.create(department_code="D002", department_name="部门B")
        user_b = Employee.objects.create(
            employee_jobcode="U002",
            employee_name="用户B",
            employee_department=dept_b,
            employee_phone="13900139002",
        )

        # 创建 AuthUser 并关联 Employee（auth_username 必须匹配 employee_jobcode）
        auth_user_a = AuthUser.objects.create_user(auth_username="U001", password=TEST_PASSWORD, auth_phone="13700000001")
        user.auth_user = auth_user_a
        user.save(update_fields=[])

        auth_user_b = AuthUser.objects.create_user(auth_username="U002", password=TEST_PASSWORD, auth_phone="13700000002")
        user_b.auth_user = auth_user_b
        user_b.save(update_fields=[])

        # 资产 A 归属部门 A（通过 asset_manager_recordcode）
        asset.asset_current_status = "in_use"
        asset.asset_manager_recordcode = user  # user 在 D001
        asset.save(update_fields=["asset_current_status", "asset_manager_recordcode"])
        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")

        # 资产 B 归属部门 B
        asset_b = Asset.objects.create(
            asset_code="A002",
            asset_name="资产B",
            asset_purchase_price=2000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=asset.asset_storage_recordcode,
            asset_type_recordcode=asset.asset_type_recordcode,
            asset_current_status="in_use",
            asset_manager_recordcode=user_b,  # user_b 在 D002
        )
        OutAsset.objects.create(asset_recordcode=asset_b, outasset_date="2024-01-02")

        # 不传 user → 无隔离，返回全部
        all_qs = OutAssetSelector.get_recyclable_outassets()
        assert all_qs.count() == 2

        # 传入 auth_user_a（D001） → 仅返回 D001 的资产
        qs_a = OutAssetSelector.get_recyclable_outassets(user=auth_user_a)
        assert qs_a.count() == 1
        assert qs_a.first().asset_recordcode == asset

        # 传入 auth_user_b（D002） → 仅返回 D002 的资产
        qs_b = OutAssetSelector.get_recyclable_outassets(user=auth_user_b)
        assert qs_b.count() == 1
        assert qs_b.first().asset_recordcode == asset_b

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
