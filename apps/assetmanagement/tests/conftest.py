# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\conftest.py
"""
Pytest 配置文件
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.assetmanagement.models import (
    Storage,
    Asset,
    AssetType,
    OutAsset,
)
from apps.usermanagement.models import Employee, Department

User = get_user_model()


@pytest.fixture
def api_client():
    """
    API 测试客户端
    """
    return APIClient()


@pytest.fixture
def department(db):
    """
    测试部门

    【修复】Department 模型没有 department_status 字段，移除该参数
    """
    return Department.objects.create(
        department_code='D001',
        department_name='测试部门',
    )


@pytest.fixture
def user(db, department):
    """
    测试用户

    【修复】Employee 模型的部门外键字段名为 employee_department（非 employee_department_code）
    """
    return Employee.objects.create(
        employee_jobcode='U001',
        employee_name='测试用户',
        employee_department=department
    )


@pytest.fixture
def storage(db):
    """
    测试仓库
    """
    return Storage.objects.create(
        storage_code='S001',
        storage_name='测试仓库',
        storage_address='测试地点'
    )


@pytest.fixture
def asset_type(db):
    """
    测试资产类型

    Asset.asset_type_code 是必填的 ForeignKey 字段，
    测试中创建 Asset 前必须先创建 AssetType 实例。
    """
    return AssetType.objects.create(
        asset_type_code='AT001',
        asset_type_category='硬件',
        asset_type_primary='办公设备',
        asset_type_secondary='服务器'
    )


@pytest.fixture
def asset(db, storage, asset_type):
    """
    测试资产

    【修复】添加 asset_type_code 必填外键，
    避免 IntegrityError: Column 'asset_type_code_id' cannot be null
    """
    return Asset.objects.create(
        asset_code='A001',
        asset_name='测试资产',
        asset_purchase_price=1000.00,
        asset_purchase_date='2024-01-01',
        asset_entry_date='2024-01-15',
        asset_storage_code=storage,
        asset_type_code=asset_type,
        asset_current_status='in_store',
    )


@pytest.fixture
def outasset(db, asset, user):
    """
    测试出库记录

    【AGENTS 规范 - 去除冗余】outasset_applicant_jobcode/manager_jobcode/using_location 已删除
    这些字段现在统一存储在 Asset 模型中，出库记录只保留 outasset_code 关联
    """
    # 【AGENTS 规范 - 去除冗余】将人员/地点信息设置到 Asset 模型
    asset.asset_applicant_jobcode = user
    asset.asset_manager_jobcode = user
    asset.asset_using_location = '使用地点'
    asset.save(update_fields=['asset_applicant_jobcode', 'asset_manager_jobcode', 'asset_using_location'])

    return OutAsset.objects.create(
        outasset_code=asset,
        outasset_date='2024-01-01'
    )
