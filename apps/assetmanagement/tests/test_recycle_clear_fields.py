"""
回收资产清空字段测试

【P0 修复】验证回收时清空 asset_applicant、asset_manager、asset_using_location
"""

from datetime import date

from django.test import TestCase

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.assetmanagement.services import OutAssetService, RecycleAssetService
from apps.usermanagement.models import Department, Employee


class TestRecycleAssetClearFields(TestCase):
    """
    回收资产清空字段测试
    """

    def setUp(self):
        """创建测试数据"""
        self.department = Department.objects.create(
            department_code="D001",
            department_name="测试部门",
        )
        self.user = Employee.objects.create(
            employee_jobcode="U001",
            employee_name="测试用户",
            employee_department=self.department,
        )
        self.storage = Storage.objects.create(
            storage_code="S001",
            storage_name="测试仓库",
            storage_address="测试地点",
        )
        self.asset_type = AssetType.objects.create(
            type_code="AT001",
            type_name="服务器",
        )
        self.asset = Asset.objects.create(
            asset_code="A001",
            asset_name="测试资产",
            asset_purchase_price=1000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=self.storage,
            asset_type_recordcode=self.asset_type,
            asset_current_status="in_store",
        )

        # 通过 Service 创建出库记录（触发状态变更）
        outasset_data = {
            "asset_recordcode": self.asset,
            "outasset_applicant": self.user,
            "outasset_manager": self.user,
            "outasset_using_location": "测试使用地点",
            "outasset_date": "2024-01-01",
        }
        self.outasset = OutAssetService.create_outasset(outasset_data)

    def test_recycle_clears_applicant_manager_location(self):
        """
        测试回收资产时清空申请人、保管人、使用地点

        【P0 修复】回收后 asset_applicant、asset_manager、asset_using_location 应被清空
        """
        # 验证出库后字段有值
        self.asset.refresh_from_db()
        self.assertIsNotNone(self.asset.asset_applicant_recordcode, "出库后 asset_applicant_recordcode 应有值")
        self.assertIsNotNone(self.asset.asset_manager_recordcode, "出库后 asset_manager_recordcode 应有值")
        self.assertEqual(self.asset.asset_using_location, "测试使用地点", "出库后 asset_using_location 应有值")
        self.assertEqual(self.asset.asset_current_status, "in_use", "出库后状态应为 in_use")

        # 创建回收记录
        recycle_data = {
            "outasset_recordcode": self.outasset,
            "recycle_asset_date": date.today().isoformat(),
        }

        recycle_asset = RecycleAssetService.create_recycle_asset(
            recycle_data=recycle_data,
            operator_jobcode=self.user.employee_jobcode,
            operator_name=self.user.employee_name,
        )

        # 验证回收记录创建成功
        self.assertIsNotNone(recycle_asset, "回收记录应创建成功")
        self.assertEqual(recycle_asset.outasset_recordcode, self.outasset, "回收记录应关联出库记录")

        # 验证资产状态变更
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.asset_current_status, "recycled_pending", "回收后状态应为 recycled_pending")

        # 【P0 修复】验证字段被清空
        self.assertIsNone(self.asset.asset_applicant_recordcode, "回收后 asset_applicant_recordcode 应被清空")
        self.assertIsNone(self.asset.asset_manager_recordcode, "回收后 asset_manager_recordcode 应被清空")
        self.assertIsNone(self.asset.asset_using_location, "回收后 asset_using_location 应被清空")


class TestOutAssetDeleteClearFields(TestCase):
    """
    删除出库记录清空字段测试
    """

    def setUp(self):
        """创建测试数据"""
        self.department = Department.objects.create(
            department_code="D001",
            department_name="测试部门",
        )
        self.user = Employee.objects.create(
            employee_jobcode="U001",
            employee_name="测试用户",
            employee_department=self.department,
        )
        self.storage = Storage.objects.create(
            storage_code="S001",
            storage_name="测试仓库",
            storage_address="测试地点",
        )
        self.asset_type = AssetType.objects.create(
            type_code="AT001",
            type_name="服务器",
        )
        self.asset = Asset.objects.create(
            asset_code="A001",
            asset_name="测试资产",
            asset_purchase_price=1000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=self.storage,
            asset_type_recordcode=self.asset_type,
            asset_current_status="in_store",
        )

        # 通过 Service 创建出库记录
        outasset_data = {
            "asset_recordcode": self.asset,
            "outasset_applicant": self.user,
            "outasset_manager": self.user,
            "outasset_using_location": "测试使用地点",
            "outasset_date": "2024-01-01",
        }
        self.outasset = OutAssetService.create_outasset(outasset_data)

    def test_delete_outasset_restores_applicant_manager_location(self):
        """
        测试删除出库记录时从快照恢复申请人、保管人、使用地点

        【BE-C2 修复】删除出库记录后 asset_applicant、asset_manager、asset_using_location 应从快照恢复
        """
        # 验证出库后字段有值
        self.asset.refresh_from_db()
        self.assertIsNotNone(self.asset.asset_applicant_recordcode, "出库后 asset_applicant_recordcode 应有值")
        self.assertIsNotNone(self.asset.asset_manager_recordcode, "出库后 asset_manager_recordcode 应有值")
        self.assertEqual(self.asset.asset_using_location, "测试使用地点", "出库后 asset_using_location 应有值")
        self.assertEqual(self.asset.asset_current_status, "in_use", "出库后状态应为 in_use")

        # 删除出库记录
        result = OutAssetService.batch_delete_outasset(
            recordcodes=[self.outasset.recordcode],
            operator_jobcode=self.user.employee_jobcode,
            operator_name=self.user.employee_name,
        )

        # 验证删除成功
        self.assertEqual(result["success_count"], 1, "应成功删除 1 条记录")
        self.assertEqual(result["fail_count"], 0, "不应有失败记录")

        # 验证资产状态变更
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.asset_current_status, "in_store", "删除出库记录后状态应恢复为 in_store")

        # 【BE-C2 修复】验证字段从快照恢复（而非清空）
        self.assertEqual(self.asset.asset_applicant_recordcode, self.user,
                         "删除出库记录后 asset_applicant_recordcode 应从快照恢复")
        self.assertEqual(self.asset.asset_manager_recordcode, self.user,
                         "删除出库记录后 asset_manager_recordcode 应从快照恢复")
        self.assertEqual(self.asset.asset_using_location, "测试使用地点",
                         "删除出库记录后 asset_using_location 应从快照恢复")
