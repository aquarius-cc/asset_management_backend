"""
未登记资产服务层测试

测试 UnregisteredAssetService 的：
- 创建未登记资产
- 更新未登记资产
- 审批处理（各种场景）
- 删除未登记资产
- 异常处理
"""

import pytest
from datetime import date
from decimal import Decimal

from core.exceptions import AppValidationError
from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.services import UnregisteredAssetService
from apps.assetmanagement.models import Asset, RecycleAsset, DamagedAsset, OutAsset


@pytest.mark.django_db
class TestUnregisteredAssetService:
    """
    未登记资产服务层测试类
    """

    def test_create_s1_success(self, employee, storage, asset_type):
        """
        测试成功创建 S1 场景未登记资产
        """
        data = {
            'scenario_type': 's1_no_record',
            'discovery_date': date(2024, 6, 1),
            'discovery_location': '会议室A',
            'asset_name': '未登记笔记本',
            'asset_brand': '测试品牌',
            'asset_specification': '测试规格',
            'asset_type_code': asset_type,
            'estimated_value': Decimal('5000.00'),
            'target_storage_code': storage,
        }

        asset = UnregisteredAssetService.create(
            data=data,
            operator_jobcode=employee.employee_jobcode
        )

        assert asset.scenario_type == 's1_no_record'
        assert asset.asset_name == '未登记笔记本'
        assert asset.approval_status == 'pending'
        assert asset.unregistered_code.startswith('UNR-')

    def test_create_s2_without_related_asset_fails(self, employee, storage):
        """
        测试 S2 场景不关联资产应该失败
        """
        data = {
            'scenario_type': 's2_no_outasset',
            'discovery_date': date(2024, 6, 1),
            'discovery_location': '办公室B',
            'asset_name': '无出库记录资产',
            'target_storage_code': storage,
        }

        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.create(
                data=data,
                operator_jobcode=employee.employee_jobcode
            )

        assert '必须关联现有资产' in str(exc_info.value.detail)

    def test_create_s1_with_related_asset_fails(self, employee, storage, existing_asset):
        """
        测试 S1 场景关联资产应该失败
        """
        data = {
            'scenario_type': 's1_no_record',
            'discovery_date': date(2024, 6, 1),
            'discovery_location': '会议室A',
            'asset_name': '未登记资产',
            'related_asset_code': existing_asset,
            'target_storage_code': storage,
        }

        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.create(
                data=data,
                operator_jobcode=employee.employee_jobcode
            )

        assert '不应关联现有资产' in str(exc_info.value.detail)

    def test_update_success(self, unregistered_asset_s1, employee):
        """
        测试成功更新未登记资产
        """
        update_data = {
            'asset_name': '更新后的名称',
            'asset_brand': '更新后的品牌',
        }

        updated = UnregisteredAssetService.update(
            unregistered_code=unregistered_asset_s1.unregistered_code,
            update_data=update_data,
            operator_jobcode=employee.employee_jobcode
        )

        assert updated.asset_name == '更新后的名称'
        assert updated.asset_brand == '更新后的品牌'

    def test_update_approved_fails(self, approved_unregistered_asset, employee):
        """
        测试更新已审批的资产应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.update(
                unregistered_code=approved_unregistered_asset.unregistered_code,
                update_data={'asset_name': '新名称'},
                operator_jobcode=employee.employee_jobcode
            )

        assert '不允许修改' in str(exc_info.value.detail)

    def test_update_nonexistent_fails(self, employee):
        """
        测试更新不存在的资产应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.update(
                unregistered_code='UNR-NOTEXIST',
                update_data={'asset_name': '新名称'},
                operator_jobcode=employee.employee_jobcode
            )

        assert '不存在' in str(exc_info.value.detail)

    def test_update_disallowed_field_fails(self, unregistered_asset_s1, employee):
        """
        测试更新不允许的字段应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.update(
                unregistered_code=unregistered_asset_s1.unregistered_code,
                update_data={'scenario_type': 's2_no_outasset'},  # 不允许修改
                operator_jobcode=employee.employee_jobcode
            )

        assert '不允许修改字段' in str(exc_info.value.detail)

    def test_approve_s1_create_and_recycle(self, unregistered_asset_s1, admin_employee, storage):
        """
        测试 S1 场景审批通过并回收
        """
        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_asset_s1.unregistered_code,
            handle_type='create_and_recycle',
            approver_jobcode=admin_employee.employee_jobcode
        )

        # 验证返回结果
        assert result['action'] == 'create_and_recycle'
        assert 'asset_code' in result
        assert 'recycle_id' in result
        # 【AGENTS 规范 - 业务唯一编码】验证返回 recycle_record_code
        assert 'recycle_record_code' in result
        assert result['recycle_record_code'].startswith('RECYCLE-')

        # 验证资产创建
        asset = Asset.objects.get(asset_code=result['asset_code'])
        assert asset.asset_name == unregistered_asset_s1.asset_name
        assert asset.asset_current_status == 'recycled_pending'

        # 验证回收记录创建
        recycle = RecycleAsset.objects.get(id=result['recycle_id'])
        assert recycle.recycle_asset_code == asset
        # 【AGENTS 规范 - 业务唯一编码】验证回收记录编码格式和唯一性
        assert recycle.recycle_record_code == result['recycle_record_code']
        assert len(recycle.recycle_record_code) == 25  # RECYCLE-YYYYMMDD-XXXXXXXX

        # 验证未登记资产状态更新
        unregistered_asset_s1.refresh_from_db()
        assert unregistered_asset_s1.approval_status == 'approved'
        assert unregistered_asset_s1.result_asset_code == asset

    def test_approve_s1_create_and_damaged(self, unregistered_asset_s1, admin_employee):
        """
        测试 S1 场景审批通过并待报废
        """
        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_asset_s1.unregistered_code,
            handle_type='create_and_damaged',
            approver_jobcode=admin_employee.employee_jobcode
        )

        assert result['action'] == 'create_and_damaged'
        assert 'asset_code' in result
        assert 'damaged_id' in result

        # 验证资产状态
        asset = Asset.objects.get(asset_code=result['asset_code'])
        assert asset.asset_current_status == 'damaged'

        # 验证待报废记录
        damaged = DamagedAsset.objects.get(id=result['damaged_id'])
        assert damaged.damaged_asset_code == asset

    def test_approve_s2_supplement_and_recycle(self, unregistered_asset_s2, admin_employee, existing_asset):
        """
        测试 S2 场景补建出库并回收
        """
        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_asset_s2.unregistered_code,
            handle_type='supplement_and_recycle',
            approver_jobcode=admin_employee.employee_jobcode
        )

        assert result['action'] == 'supplement_and_recycle'
        assert 'asset_code' in result
        assert 'outasset_code' in result
        assert 'recycle_id' in result

        # 验证出库记录创建
        outasset = OutAsset.objects.get(outasset_recordcode=result['outasset_code'])
        assert outasset.outasset_code == existing_asset

        # 验证资产状态更新
        existing_asset.refresh_from_db()
        assert existing_asset.asset_current_status == 'recycled_pending'

    def test_approve_s3_correct_and_recycle(self, unregistered_asset_s3, admin_employee, existing_asset):
        """
        测试 S3 场景修正状态并回收
        """
        old_status = existing_asset.asset_current_status

        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_asset_s3.unregistered_code,
            handle_type='correct_and_recycle',
            approver_jobcode=admin_employee.employee_jobcode
        )

        assert result['action'] == 'correct_and_recycle'
        assert result['old_status'] == old_status
        assert 'recycle_id' in result

        # 验证资产状态更新
        existing_asset.refresh_from_db()
        assert existing_asset.asset_current_status == 'recycled_pending'

    def test_approve_reject(self, unregistered_asset_s1, admin_employee):
        """
        测试审批拒绝
        """
        result = UnregisteredAssetService.approve_and_handle(
            unregistered_code=unregistered_asset_s1.unregistered_code,
            handle_type='reject',
            approver_jobcode=admin_employee.employee_jobcode,
            approval_remark='测试拒绝'
        )

        assert result['action'] == 'reject'

        # 验证状态更新
        unregistered_asset_s1.refresh_from_db()
        assert unregistered_asset_s1.approval_status == 'rejected'
        assert unregistered_asset_s1.approval_remark == '测试拒绝'

    def test_approve_non_pending_fails(self, approved_unregistered_asset, admin_employee):
        """
        测试审批非待审批状态的资产应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.approve_and_handle(
                unregistered_code=approved_unregistered_asset.unregistered_code,
                handle_type='create_and_recycle',
                approver_jobcode=admin_employee.employee_jobcode
            )

        assert '不允许审批' in str(exc_info.value.detail)

    def test_approve_invalid_handle_type_fails(self, unregistered_asset_s1, admin_employee):
        """
        测试无效的处理方式应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.approve_and_handle(
                unregistered_code=unregistered_asset_s1.unregistered_code,
                handle_type='supplement_and_recycle',  # S1 场景不支持
                approver_jobcode=admin_employee.employee_jobcode
            )

        assert '不支持处理方式' in str(exc_info.value.detail)

    def test_delete_success(self, unregistered_asset_s1, employee):
        """
        测试成功删除未登记资产
        """
        code = unregistered_asset_s1.unregistered_code

        UnregisteredAssetService.delete(
            unregistered_code=code,
            operator_jobcode=employee.employee_jobcode
        )

        # 验证软删除
        assert UnregisteredAsset.objects.filter(unregistered_code=code).count() == 0
        assert UnregisteredAsset.all_objects.filter(unregistered_code=code).count() == 1

    def test_delete_approved_fails(self, approved_unregistered_asset, employee):
        """
        测试删除已审批的资产应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.delete(
                unregistered_code=approved_unregistered_asset.unregistered_code,
                operator_jobcode=employee.employee_jobcode
            )

        assert '不允许删除' in str(exc_info.value.detail)

    def test_delete_nonexistent_fails(self, employee):
        """
        测试删除不存在的资产应该失败
        """
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.delete(
                unregistered_code='UNR-NOTEXIST',
                operator_jobcode=employee.employee_jobcode
            )

        assert '不存在' in str(exc_info.value.detail)
