"""
未登记资产模型测试

测试 UnregisteredAsset 模型的：
- 创建和字段验证
- 编码自动生成
- 状态检查方法
- 软删除功能
"""

import pytest
from datetime import date
from decimal import Decimal

from apps.unregisteredasset.models import UnregisteredAsset


@pytest.mark.django_db
class TestUnregisteredAssetModel:
    """
    未登记资产模型测试类
    """

    def test_create_s1_scenario(self, employee, storage, asset_type):
        """
        测试创建 S1 场景未登记资产
        """
        asset = UnregisteredAsset.objects.create(
            scenario_type='s1_no_record',
            discovery_date=date(2024, 6, 1),
            discovery_location='会议室A',
            discovery_person_jobcode=employee,
            asset_name='测试资产',
            asset_brand='测试品牌',
            asset_specification='测试规格',
            asset_type_code=asset_type,
            estimated_value=Decimal('5000.00'),
            target_storage_code=storage
        )

        assert asset.unregistered_code.startswith('UNR-')
        assert asset.scenario_type == 's1_no_record'
        assert asset.asset_name == '测试资产'
        assert asset.approval_status == 'pending'
        assert asset.is_delete is False

    def test_create_s2_scenario(self, employee, storage, existing_asset):
        """
        测试创建 S2 场景未登记资产（关联现有资产）
        """
        asset = UnregisteredAsset.objects.create(
            scenario_type='s2_no_outasset',
            discovery_date=date(2024, 6, 1),
            discovery_location='办公室B',
            discovery_person_jobcode=employee,
            asset_name='无出库记录资产',
            related_asset_code=existing_asset,
            target_storage_code=storage
        )

        assert asset.related_asset_code == existing_asset
        assert asset.scenario_type == 's2_no_outasset'

    def test_code_auto_generation(self, employee, storage):
        """
        测试编码自动生成
        """
        asset = UnregisteredAsset.objects.create(
            scenario_type='s1_no_record',
            discovery_date=date(2024, 6, 1),
            discovery_location='测试地点',
            discovery_person_jobcode=employee,
            asset_name='测试资产',
            target_storage_code=storage
        )

        # 验证编码格式：UNR-YYYYMMDD-XXXXXX
        assert len(asset.unregistered_code) == 19
        assert asset.unregistered_code.startswith('UNR-')
        assert asset.unregistered_code[4:12].isdigit()  # 日期部分

    def test_code_uniqueness(self, employee, storage):
        """
        测试编码唯一性
        """
        from django.db import IntegrityError

        asset1 = UnregisteredAsset.objects.create(
            scenario_type='s1_no_record',
            discovery_date=date(2024, 6, 1),
            discovery_location='地点1',
            discovery_person_jobcode=employee,
            asset_name='资产1',
            target_storage_code=storage
        )

        # 手动设置相同编码应该失败
        with pytest.raises(IntegrityError):
            UnregisteredAsset.objects.create(
                unregistered_code=asset1.unregistered_code,
                scenario_type='s1_no_record',
                discovery_date=date(2024, 6, 1),
                discovery_location='地点2',
                discovery_person_jobcode=employee,
                asset_name='资产2',
                target_storage_code=storage
            )

    def test_str_representation(self, unregistered_asset_s1):
        """
        测试字符串表示
        """
        expected = f'{unregistered_asset_s1.asset_name}({unregistered_asset_s1.unregistered_code})'
        assert str(unregistered_asset_s1) == expected

    def test_can_modify_pending_status(self, unregistered_asset_s1):
        """
        测试待审批状态可以修改
        """
        assert unregistered_asset_s1.can_modify() is True

    def test_cannot_modify_approved_status(self, approved_unregistered_asset):
        """
        测试已审批状态不能修改
        """
        assert approved_unregistered_asset.can_modify() is False

    def test_can_delete_pending_status(self, unregistered_asset_s1):
        """
        测试待审批状态可以删除
        """
        assert unregistered_asset_s1.can_delete() is True

    def test_cannot_delete_approved_status(self, approved_unregistered_asset):
        """
        测试已审批状态不能删除
        """
        assert approved_unregistered_asset.can_delete() is False

    def test_soft_delete(self, unregistered_asset_s1):
        """
        测试软删除功能
        """
        code = unregistered_asset_s1.unregistered_code
        unregistered_asset_s1.delete()

        # 软删除后查询不到
        assert UnregisteredAsset.objects.filter(unregistered_code=code).count() == 0

        # 但使用 all_objects 可以查询到
        assert UnregisteredAsset.all_objects.filter(unregistered_code=code).count() == 1

        # 验证 is_delete 标记
        deleted = UnregisteredAsset.all_objects.get(unregistered_code=code)
        assert deleted.is_delete is True

    def test_scenario_type_choices(self, employee, storage):
        """
        测试场景类型选项
        """
        valid_scenarios = ['s1_no_record', 's2_no_outasset', 's3_status_mismatch']

        for scenario in valid_scenarios:
            asset = UnregisteredAsset.objects.create(
                scenario_type=scenario,
                discovery_date=date(2024, 6, 1),
                discovery_location='测试地点',
                discovery_person_jobcode=employee,
                asset_name=f'资产-{scenario}',
                target_storage_code=storage
            )
            assert asset.scenario_type == scenario

    def test_approval_status_choices(self, employee, storage):
        """
        测试审批状态选项
        """
        # pending 是默认值
        asset = UnregisteredAsset.objects.create(
            scenario_type='s1_no_record',
            discovery_date=date(2024, 6, 1),
            discovery_location='测试地点',
            discovery_person_jobcode=employee,
            asset_name='测试资产',
            target_storage_code=storage
        )
        assert asset.approval_status == 'pending'

    def test_optional_fields(self, employee, storage):
        """
        测试可选字段可以为空
        """
        asset = UnregisteredAsset.objects.create(
            scenario_type='s1_no_record',
            discovery_date=date(2024, 6, 1),
            discovery_location='测试地点',
            discovery_person_jobcode=employee,
            asset_name='最小化资产'
            # 其他字段均为可选
        )

        assert asset.asset_brand is None
        assert asset.asset_specification is None
        assert asset.asset_type_code is None
        assert asset.estimated_value is None
        assert asset.related_asset_code is None
        assert asset.target_storage_code is None
