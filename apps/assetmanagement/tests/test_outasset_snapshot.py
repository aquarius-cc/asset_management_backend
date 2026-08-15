"""
出库记录快照测试

【方案D】验证 OutAsset 表的 FK 关联和 JSON 快照功能
"""

from django.test import TestCase

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.assetmanagement.services import OutAssetService
from apps.usermanagement.models import Department, Employee


class TestOutAssetSnapshot(TestCase):
    """
    出库记录快照测试
    """

    def setUp(self):
        """创建测试数据"""
        self.department = Department.objects.create(
            department_code="D001",
            department_name="测试部门",
        )
        self.applicant = Employee.objects.create(
            employee_jobcode="A001",
            employee_name="申请人张三",
            employee_department=self.department,
        )
        self.manager = Employee.objects.create(
            employee_jobcode="A002",
            employee_name="保管人李四",
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

    def test_create_outasset_with_snapshot(self):
        """
        测试创建出库记录时保存快照

        【方案D】验证:
        1. OutAsset 表的 FK 字段正确设置
        2. JSON 快照包含申请人、保管人、使用地点信息
        """
        outasset_data = {
            "asset_recordcode": self.asset,
            "outasset_applicant": self.applicant,
            "outasset_manager": self.manager,
            "outasset_using_location": "B栋13楼",
            "outasset_date": "2024-01-01",
        }

        outasset = OutAssetService.create_outasset(outasset_data)

        # 验证 OutAsset 记录创建成功
        self.assertIsNotNone(outasset)
        self.assertEqual(outasset.asset_recordcode, self.asset)

        # 验证 FK 字段正确设置
        outasset.refresh_from_db()
        self.assertEqual(outasset.outasset_applicant_recordcode, self.applicant)
        self.assertEqual(outasset.outasset_manager_recordcode, self.manager)
        self.assertEqual(outasset.outasset_using_location, "B栋13楼")

        # 验证 JSON 快照正确保存
        snapshot = outasset.outasset_snapshot
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["applicant"]["jobcode"], "A001")
        self.assertEqual(snapshot["applicant"]["name"], "申请人张三")
        self.assertEqual(snapshot["manager"]["jobcode"], "A002")
        self.assertEqual(snapshot["manager"]["name"], "保管人李四")
        self.assertEqual(snapshot["using_location"], "B栋13楼")

    def test_snapshot_preserved_after_asset_status_change(self):
        """
        测试资产状态变更后,快照信息保持不变

        【方案D】验证:
        1. 创建出库记录后,资产状态变为 in_use
        2. 回收后,资产的申请人/保管人被清空
        3. 出库记录的快照信息保持不变
        """
        # 创建出库记录
        outasset_data = {
            "asset_recordcode": self.asset,
            "outasset_applicant": self.applicant,
            "outasset_manager": self.manager,
            "outasset_using_location": "B栋13楼",
            "outasset_date": "2024-01-01",
        }
        outasset = OutAssetService.create_outasset(outasset_data)

        # 验证出库后快照存在
        outasset.refresh_from_db()
        self.assertIsNotNone(outasset.outasset_snapshot)
        self.assertEqual(outasset.outasset_snapshot["applicant"]["name"], "申请人张三")

        # 模拟回收(清空资产的申请人/保管人)
        self.asset.refresh_from_db()
        self.asset.asset_applicant_recordcode = None
        self.asset.asset_manager_recordcode = None
        self.asset.asset_using_location = None
        self.asset.save(
            update_fields=["asset_applicant_recordcode", "asset_manager_recordcode", "asset_using_location"]
        )

        # 验证出库记录的快照信息保持不变
        outasset.refresh_from_db()
        self.assertIsNotNone(outasset.outasset_snapshot)
        self.assertEqual(outasset.outasset_snapshot["applicant"]["name"], "申请人张三")
        self.assertEqual(outasset.outasset_snapshot["manager"]["name"], "保管人李四")
        self.assertEqual(outasset.outasset_snapshot["using_location"], "B栋13楼")
