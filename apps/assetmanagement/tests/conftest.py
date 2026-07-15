# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\conftest.py
"""
Pytest 配置文件
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.assetmanagement.models import (
    Asset,
    AssetType,
    BrokenAsset,
    Contract,
    DamagedAsset,
    FoundAsset,
    LostAsset,
    OutAsset,
    RecycleAsset,
    Storage,
)
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee


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
        department_code="D001",
        department_name="测试部门",
    )


@pytest.fixture
def user(db, department):
    """
    测试用户

    【修复】Employee 模型的部门外键字段名为 employee_department（非 employee_department_code）
    """
    return Employee.objects.create(employee_jobcode="U001", employee_name="测试用户", employee_department=department)


@pytest.fixture
def storage(db):
    """
    测试仓库
    """
    return Storage.objects.create(
        storage_code="S001",
        storage_name="测试仓库",
        storage_address="测试地点",
        storage_location="测试地点",
        storage_capacity=100,
        sort_order=0,
    )


@pytest.fixture
def asset_type(db):
    """
    测试资产类型

    Asset.asset_type_code 是必填的 ForeignKey 字段，
    测试中创建 Asset 前必须先创建 AssetType 实例。
    """
    return AssetType.objects.create(
        type_code="AT001",
        type_name="服务器",
    )


@pytest.fixture
def asset(db, storage, asset_type):
    """
    测试资产

    【修复】添加 asset_type_code 必填外键，
    避免 IntegrityError: Column 'asset_type_code_id' cannot be null
    """
    return Asset.objects.create(
        asset_code="A001",
        asset_name="测试资产",
        asset_purchase_price=1000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_store",
    )


@pytest.fixture
def outasset(db, asset, user):
    """
    测试出库记录

    【AGENTS 规范 - 去除冗余】outasset_applicant_jobcode/manager_jobcode/using_location 已删除
    这些字段现在统一存储在 Asset 模型中，出库记录只保留 outasset_code 关联
    """
    # 【AGENTS 规范 - 去除冗余】将人员/地点信息设置到 Asset 模型
    asset.asset_applicant_recordcode = user
    asset.asset_manager_recordcode = user
    asset.asset_using_location = "使用地点"
    asset.asset_current_status = "in_use"  # 出库后状态应为in_use
    asset.save(
        update_fields=[
            "asset_applicant_recordcode",
            "asset_manager_recordcode",
            "asset_using_location",
            "asset_current_status",
        ]
    )

    return OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")


@pytest.fixture
def auth_user(db):
    """
    测试认证用户（用于API认证）
    """
    return AuthUser.objects.create_user(auth_username="testuser", password="testpass123", auth_phone="13800138000")


@pytest.fixture
def admin_auth_user(db):
    """
    测试管理员认证用户（用于需要管理员权限的API测试）
    创建 superuser 以通过 IsAssetAdminOrAbove 权限检查
    """
    return AuthUser.objects.create_superuser(
        auth_username="adminuser", password="adminpass123", auth_phone="13800138001"
    )


@pytest.fixture
def admin_employee(db, department):
    """
    管理员员工，与 admin_auth_user 关联
    """
    return Employee.objects.create(
        employee_jobcode="adminuser",
        employee_name="管理员",
        employee_department=department,
        role="system_admin",
    )


@pytest.fixture
def contract(db):
    """
    测试合同
    """
    return Contract.objects.create(
        contract_code="C001",
        contract_name="测试合同",
        contract_amount=10000.00,
        contract_status="purchasing",
        contract_type="service",
        contract_start_date="2024-01-01",
        contract_end_date="2025-01-01",
    )


@pytest.fixture
def employee(db, department):
    """
    测试员工
    """
    return Employee.objects.create(
        employee_jobcode="U002",
        employee_name="测试员工2",
        employee_department=department,
    )


@pytest.fixture
def damaged_asset(db, asset, employee):
    """
    测试待报废资产
    """
    from apps.assetmanagement.models import DamagedAsset
    return DamagedAsset.objects.create(
        asset_recordcode=asset,
        damaged_date="2024-06-01",
        damaged_asset_description="测试损坏",
        damaged_asset_number=1,
        approval_status="pending",
        approver=employee,
    )


@pytest.fixture
def recycle_asset(db, outasset, asset, employee):
    """
    测试回收资产
    """
    from apps.assetmanagement.models import RecycleAsset
    return RecycleAsset.objects.create(
        outasset_recordcode=outasset,
        asset_recordcode=asset,
        recycle_asset_date="2024-07-01",
        recycle_asset_number=1,
        operator_employee=employee,
    )


@pytest.fixture
def broken_asset(db, asset, employee):
    """
    测试损坏资产
    """
    return BrokenAsset.objects.create(
        asset_recordcode=asset,
        broken_reason="测试损坏原因",
        broken_date="2024-09-01",
        broken_description="测试损坏描述",
        operator_employee=employee,
    )


@pytest.fixture
def lost_asset(db, asset, employee):
    """
    测试遗失资产
    """
    return LostAsset.objects.create(
        asset_recordcode=asset,
        lost_reason="测试遗失原因",
        lost_date="2024-10-01",
        last_known_location="测试最后已知位置",
        lost_description="测试遗失描述",
        operator_employee=employee,
    )


@pytest.fixture
def found_asset(db, asset, employee, lost_asset):
    """
    测试找回资产
    """
    return FoundAsset.objects.create(
        lost_asset_recordcode=lost_asset,
        asset_recordcode=asset,
        found_location="测试找回位置",
        found_date="2024-11-01",
        found_description="测试找回描述",
        operator_employee=employee,
    )


@pytest.fixture
def repair_asset(db, asset, employee):
    """
    测试维修资产
    """
    from apps.assetmanagement.models import RepairAsset
    return RepairAsset.objects.create(
        asset_recordcode=asset,
        repair_reason="测试维修原因",
        repair_date="2024-12-01",
        repair_description="测试维修描述",
        operator_employee=employee,
    )
