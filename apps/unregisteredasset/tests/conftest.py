"""
未登记资产测试配置文件

提供测试用的 fixtures,包括:
- 测试用户
- 测试部门
- 测试仓库
- 测试资产类型
- 测试资产
- 测试未登记资产记录
"""

from datetime import date

import pytest

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.authusermanagement.models import AuthUser
from apps.unregisteredasset.models import UnregisteredAsset
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


@pytest.fixture
def auth_user(db):
    """
    测试认证用户(用于API认证)
    """
    return AuthUser.objects.create_user(auth_username="testuser", password=TEST_PASSWORD, auth_phone="13800138000")


@pytest.fixture
def admin_auth_user(db):
    """
    测试系统管理员认证用户(用于需要管理员权限的API测试)

    RBAC 系统管理员:Employee.role=system_admin,无部门(全局角色不受无部门兜底影响)。
    删除操作使用 IsSystemAdmin(替代遗留 is_staff 门禁),故夹具不依赖 auth_is_staff。
    """
    user = AuthUser.objects.create_user(
        auth_username="adminuser", password=TEST_PASSWORD, auth_phone="13800138001"
    )
    Employee.objects.create(
        employee_jobcode="adminuser",
        employee_name="系统管理员",
        employee_department=None,
        role=EmployeeRole.SYSTEM_ADMIN,
        employee_phone="13800138001",
        employee_location="测试地点",
    )
    return user


@pytest.fixture
def employee(db):
    """
    测试员工
    """
    return Employee.objects.create(
        employee_jobcode="EMP001",
        employee_name="测试员工",
        employee_department=None,
        employee_phone="13800138000",
        employee_location="测试地点",
    )


@pytest.fixture
def admin_employee(db):
    """
    测试管理员员工
    """
    return Employee.objects.create(
        employee_jobcode="ADMIN001",
        employee_name="测试管理员",
        employee_department=None,
        employee_phone="13800138001",
        employee_location="测试地点",
    )


@pytest.fixture
def dept_manager_user(db):
    """部门经理用户(用于审批测试)"""
    dept = Department.objects.create(
        department_code="DM_DEPT",
        department_name="审批部门",
        department_information="info",
    )
    user = AuthUser.objects.create_user(
        auth_username="dmuser",
        password=TEST_PASSWORD,
        auth_phone="13800138002",
    )
    Employee.objects.create(
        employee_jobcode="dmuser",
        employee_name="部门经理",
        employee_department=dept,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone="13800138002",
        employee_location="测试地点",
    )
    return user


@pytest.fixture
def dept_manager_client(api_client, dept_manager_user):
    """部门经理认证客户端"""
    api_client.force_authenticate(user=dept_manager_user)
    return api_client


@pytest.fixture
def asset_type(db):
    """
    测试资产类型
    """
    return AssetType.objects.create(type_code="TYPE001", type_name="测试大类")


@pytest.fixture
def storage(db):
    """
    测试仓库
    """
    return Storage.objects.create(storage_code="STOR001", storage_name="测试仓库", storage_address="测试地点")


@pytest.fixture
def existing_asset(db, storage, asset_type):
    """
    测试已存在资产(用于 S2/S3 场景)
    """
    return Asset.objects.create(
        asset_code="EXIST001",
        asset_name="已存在资产",
        asset_type_recordcode=asset_type,
        asset_storage_recordcode=storage,
        asset_purchase_price=1000.00,
        asset_purchase_date=date(2024, 1, 1),
        asset_entry_date=date(2024, 1, 1),
        asset_current_status="in_store",
    )


@pytest.fixture
def unregistered_asset_s1(db, employee, storage, asset_type):
    """
    测试未登记资产 - S1场景(实物有系统无)
    """
    return UnregisteredAsset.objects.create(
        scenario_type="s1_no_record",
        discovery_date=date(2024, 6, 1),
        discovery_location="会议室A",
        discovery_person=employee,
        asset_name="未登记笔记本",
        asset_brand="测试品牌",
        asset_specification="测试规格",
        unregistered_asset_type=asset_type,
        estimated_value=5000.00,
        unregistered_asset_storage=storage,
        approval_status="pending",
    )


@pytest.fixture
def unregistered_asset_s2(db, employee, storage, asset_type, existing_asset):
    """
    测试未登记资产 - S2场景(系统有无出库)
    """
    return UnregisteredAsset.objects.create(
        scenario_type="s2_no_outasset",
        discovery_date=date(2024, 6, 1),
        discovery_location="办公室B",
        discovery_person=employee,
        asset_name="无出库记录资产",
        unregistered_asset_type=asset_type,
        related_asset=existing_asset,
        unregistered_asset_storage=storage,
        approval_status="pending",
    )


@pytest.fixture
def unregistered_asset_s3(db, employee, storage, existing_asset):
    """
    测试未登记资产 - S3场景(状态异常)
    """
    return UnregisteredAsset.objects.create(
        scenario_type="s3_status_mismatch",
        discovery_date=date(2024, 6, 1),
        discovery_location="仓库C",
        discovery_person=employee,
        asset_name="状态异常资产",
        related_asset=existing_asset,
        unregistered_asset_storage=storage,
        approval_status="pending",
    )


@pytest.fixture
def approved_unregistered_asset(db, employee, admin_employee, storage):
    """
    测试已审批的未登记资产
    """
    return UnregisteredAsset.objects.create(
        scenario_type="s1_no_record",
        discovery_date=date(2024, 6, 1),
        discovery_location="会议室A",
        discovery_person=employee,
        asset_name="已审批资产",
        unregistered_asset_storage=storage,
        approval_status="approved",
        approver=admin_employee,
        approval_date=date(2024, 6, 2),
        handle_type="create_and_recycle",
    )
