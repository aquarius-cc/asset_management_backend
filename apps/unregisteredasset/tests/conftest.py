"""
未登记资产测试配置文件

提供测试用的 fixtures，包括：
- 测试用户
- 测试部门
- 测试仓库
- 测试资产类型
- 测试资产
- 测试未登记资产记录
"""

import pytest
from datetime import date

from apps.usermanagement.models import Employee
from apps.assetmanagement.models import AssetType, Storage, Asset
from apps.unregisteredasset.models import UnregisteredAsset


@pytest.fixture
def employee(db):
    """
    测试员工
    """
    return Employee.objects.create(
        employee_jobcode='EMP001',
        employee_name='测试员工',
        employee_department_code='DEPT001',
        employee_department_name='测试部门'
    )


@pytest.fixture
def admin_employee(db):
    """
    测试管理员员工
    """
    return Employee.objects.create(
        employee_jobcode='ADMIN001',
        employee_name='测试管理员',
        employee_department_code='DEPT001',
        employee_department_name='测试部门'
    )


@pytest.fixture
def asset_type(db):
    """
    测试资产类型
    """
    return AssetType.objects.create(
        asset_type_code='TYPE001',
        asset_type_name='测试类型'
    )


@pytest.fixture
def storage(db):
    """
    测试仓库
    """
    return Storage.objects.create(
        storage_code='STOR001',
        storage_name='测试仓库',
        storage_location='测试地点'
    )


@pytest.fixture
def existing_asset(db, storage, asset_type):
    """
    测试已存在资产（用于 S2/S3 场景）
    """
    return Asset.objects.create(
        asset_code='EXIST001',
        asset_name='已存在资产',
        asset_type_code=asset_type,
        asset_storage_code=storage,
        asset_purchase_price=1000.00,
        asset_purchase_date=date(2024, 1, 1),
        asset_entry_date=date(2024, 1, 1),
        asset_current_status='in_store'
    )


@pytest.fixture
def unregistered_asset_s1(db, employee, storage, asset_type):
    """
    测试未登记资产 - S1场景（实物有系统无）
    """
    return UnregisteredAsset.objects.create(
        scenario_type='s1_no_record',
        discovery_date=date(2024, 6, 1),
        discovery_location='会议室A',
        discovery_person_jobcode=employee,
        asset_name='未登记笔记本',
        asset_brand='测试品牌',
        asset_specification='测试规格',
        asset_type_code=asset_type,
        estimated_value=5000.00,
        target_storage_code=storage,
        approval_status='pending'
    )


@pytest.fixture
def unregistered_asset_s2(db, employee, storage, asset_type, existing_asset):
    """
    测试未登记资产 - S2场景（系统有无出库）
    """
    return UnregisteredAsset.objects.create(
        scenario_type='s2_no_outasset',
        discovery_date=date(2024, 6, 1),
        discovery_location='办公室B',
        discovery_person_jobcode=employee,
        asset_name='无出库记录资产',
        asset_type_code=asset_type,
        related_asset_code=existing_asset,
        target_storage_code=storage,
        approval_status='pending'
    )


@pytest.fixture
def unregistered_asset_s3(db, employee, storage, existing_asset):
    """
    测试未登记资产 - S3场景（状态异常）
    """
    return UnregisteredAsset.objects.create(
        scenario_type='s3_status_mismatch',
        discovery_date=date(2024, 6, 1),
        discovery_location='仓库C',
        discovery_person_jobcode=employee,
        asset_name='状态异常资产',
        related_asset_code=existing_asset,
        target_storage_code=storage,
        approval_status='pending'
    )


@pytest.fixture
def approved_unregistered_asset(db, employee, admin_employee, storage):
    """
    测试已审批的未登记资产
    """
    return UnregisteredAsset.objects.create(
        scenario_type='s1_no_record',
        discovery_date=date(2024, 6, 1),
        discovery_location='会议室A',
        discovery_person_jobcode=employee,
        asset_name='已审批资产',
        target_storage_code=storage,
        approval_status='approved',
        approver_jobcode=admin_employee,
        approval_date=date(2024, 6, 2),
        handle_type='create_and_recycle'
    )
