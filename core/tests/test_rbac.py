"""
RBAC 权限矩阵自动化测试

覆盖范围:
- 权限类测试(IsSystemAdmin / IsDeptManagerOrAbove / IsAssetAdminOrAbove / IsAuditorOrAdmin)
- 行级数据隔离测试(get_department_codes_for_user / get_queryset_for_user)
- 资产部门归属动态解析测试(resolve_asset_department_codes)
- 边界场景测试(无 Employee / is_superuser / 跨部门)
"""

import itertools

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.department_scope import (
    get_department_codes_for_user,
)
from core.permissions import (
    IsAssetAdminOrAbove,
    IsAuditorOrAdmin,
    IsDeptManagerOrAbove,
    IsSystemAdmin,
)
from core.tests import TEST_PASSWORD


User = get_user_model()

# =====================================================================
# Helpers
# =====================================================================

_phone_seq = itertools.count(1)


def _phone():
    """生成测试用唯一手机号(满足 unique_employee_phone_not_deleted 条件约束)"""
    return f"138{next(_phone_seq):08d}"


def _make_user(username, role, department=None):
    """创建带角色的 AuthUser + Employee(jobcode ≤ 20 字符)

    department 未指定时自动创建独立部门,避免矩阵测试误用"无部门"员工
    (无部门部门级角色按最严兜底拒绝写权限,见 TestNoDepartmentWriteDegradation)。
    """
    if department is None:
        department = Department.objects.create(
            department_code=f"DPT-{username[:10]}",
            department_name=f"{username}部门",
        )
    user = User.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_is_staff=(role == EmployeeRole.SYSTEM_ADMIN),
    )
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}员工",
        employee_department=department,
        role=role,
        employee_phone=_phone(),
    )
    return user


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def dept_a(db):
    return Department.objects.create(department_code="DEPT-A", department_name="A部门")


@pytest.fixture
def dept_b(db):
    return Department.objects.create(department_code="DEPT-B", department_name="B部门")


@pytest.fixture
def dept_b_child(db, dept_b):
    return Department.objects.create(
        department_code="DEPT-B1",
        department_name="B1子部门",
        parent=dept_b,
    )


@pytest.fixture
def storage_a(db, dept_a):
    """A 部门的仓库"""
    emp = Employee.objects.create(
        employee_jobcode="WH-A",
        employee_name="A仓管",
        employee_department=dept_a,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    return Storage.objects.create(
        storage_code="SA-001",
        storage_name="A仓库",
        storage_address="A地址",
        storage_manager=emp,
    )


@pytest.fixture
def storage_b(db, dept_b):
    """B 部门的仓库"""
    emp = Employee.objects.create(
        employee_jobcode="WH-B",
        employee_name="B仓管",
        employee_department=dept_b,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    return Storage.objects.create(
        storage_code="SB-001",
        storage_name="B仓库",
        storage_address="B地址",
        storage_manager=emp,
    )


@pytest.fixture
def asset_in_dept_a(db, dept_a, storage_a):
    """归属 A 部门的资产(通过 entry_person 关联)"""
    entry_person = Employee.objects.create(
        employee_jobcode="EP-A1",
        employee_name="入库员A1",
        employee_department=dept_a,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    asset_type = AssetType.objects.create(type_code="T001", type_name="电脑")
    return Asset.objects.create(
        asset_code="AST-A001",
        asset_name="A部门资产",
        asset_purchase_price=5000,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_type_recordcode=asset_type,
        asset_storage_recordcode=storage_a,
        asset_entry_person_recordcode=entry_person,
        asset_current_status="in_store",
    )


@pytest.fixture
def asset_in_dept_b(db, dept_b, storage_b):
    """归属 B 部门的资产(通过 manager 关联,使用 B 部门的仓库)"""
    manager = Employee.objects.create(
        employee_jobcode="MG-B1",
        employee_name="保管人B1",
        employee_department=dept_b,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    asset_type = AssetType.objects.create(type_code="T002", type_name="显示器")
    return Asset.objects.create(
        asset_code="AST-B001",
        asset_name="B部门资产",
        asset_purchase_price=3000,
        asset_purchase_date="2024-02-01",
        asset_entry_date="2024-02-15",
        asset_type_recordcode=asset_type,
        asset_storage_recordcode=storage_b,
        asset_manager_recordcode=manager,
        asset_current_status="in_use",
    )


@pytest.fixture
def sys_admin(db, dept_a):
    return _make_user("adm", EmployeeRole.SYSTEM_ADMIN, dept_a)


@pytest.fixture
def dept_manager(db, dept_a):
    return _make_user("mgr", EmployeeRole.DEPT_MANAGER, dept_a)


@pytest.fixture
def asset_admin(db, dept_a):
    return _make_user("ast", EmployeeRole.ASSET_ADMIN, dept_a)


@pytest.fixture
def regular_user(db, dept_a):
    return _make_user("usr", EmployeeRole.REGULAR_USER, dept_a)


@pytest.fixture
def auditor(db, dept_a):
    return _make_user("aud", EmployeeRole.AUDITOR, dept_a)


@pytest.fixture
def asset_admin_b(db, dept_b):
    return _make_user("asb", EmployeeRole.ASSET_ADMIN, dept_b)


# =====================================================================
# 1. 权限类测试
# =====================================================================


class TestPermissionClasses:
    def _check(self, perm_class, user):
        perm = perm_class()
        request = RequestFactory().get("/api/test/")
        request.user = user
        return perm.has_permission(request, None)

    # --- IsSystemAdmin ---
    def test_admin_allows_admin(self, sys_admin):
        assert self._check(IsSystemAdmin, sys_admin) is True

    def test_admin_rejects_manager(self, dept_manager):
        assert self._check(IsSystemAdmin, dept_manager) is False

    def test_admin_rejects_asset_admin(self, asset_admin):
        assert self._check(IsSystemAdmin, asset_admin) is False

    def test_admin_rejects_regular(self, regular_user):
        assert self._check(IsSystemAdmin, regular_user) is False

    def test_admin_rejects_auditor(self, auditor):
        assert self._check(IsSystemAdmin, auditor) is False

    def test_admin_allows_superuser(self, db):
        su = User.objects.create_superuser(auth_username="su", password=TEST_PASSWORD)
        assert self._check(IsSystemAdmin, su) is True

    # --- IsDeptManagerOrAbove ---
    def test_manager_allows_admin(self, sys_admin):
        assert self._check(IsDeptManagerOrAbove, sys_admin) is True

    def test_manager_allows_manager(self, dept_manager):
        assert self._check(IsDeptManagerOrAbove, dept_manager) is True

    def test_manager_rejects_asset_admin(self, asset_admin):
        assert self._check(IsDeptManagerOrAbove, asset_admin) is False

    def test_manager_rejects_regular(self, regular_user):
        assert self._check(IsDeptManagerOrAbove, regular_user) is False

    def test_manager_rejects_auditor(self, auditor):
        assert self._check(IsDeptManagerOrAbove, auditor) is False

    # --- IsAssetAdminOrAbove ---
    def test_asset_allows_admin(self, sys_admin):
        assert self._check(IsAssetAdminOrAbove, sys_admin) is True

    def test_asset_allows_manager(self, dept_manager):
        assert self._check(IsAssetAdminOrAbove, dept_manager) is True

    def test_asset_allows_asset_admin(self, asset_admin):
        assert self._check(IsAssetAdminOrAbove, asset_admin) is True

    def test_asset_rejects_regular(self, regular_user):
        assert self._check(IsAssetAdminOrAbove, regular_user) is False

    def test_asset_rejects_auditor(self, auditor):
        assert self._check(IsAssetAdminOrAbove, auditor) is False

    # --- IsAuditorOrAdmin ---
    def test_auditor_allows_admin(self, sys_admin):
        assert self._check(IsAuditorOrAdmin, sys_admin) is True

    def test_auditor_allows_auditor(self, auditor):
        assert self._check(IsAuditorOrAdmin, auditor) is True

    def test_auditor_rejects_manager(self, dept_manager):
        assert self._check(IsAuditorOrAdmin, dept_manager) is False

    def test_auditor_rejects_asset_admin(self, asset_admin):
        assert self._check(IsAuditorOrAdmin, asset_admin) is False

    def test_auditor_rejects_regular(self, regular_user):
        assert self._check(IsAuditorOrAdmin, regular_user) is False


# =====================================================================
# 2. 行级数据隔离测试
# =====================================================================


class TestDepartmentScope:
    def test_superuser_no_restriction(self, sys_admin):
        assert get_department_codes_for_user(sys_admin) is None

    def test_auditor_no_restriction(self, auditor):
        assert get_department_codes_for_user(auditor) is None

    def test_dept_manager_sees_own(self, dept_manager, dept_a):
        codes = get_department_codes_for_user(dept_manager)
        assert codes is not None
        assert "DEPT-A" in codes

    def test_asset_admin_sees_own_only(self, asset_admin, dept_a):
        codes = get_department_codes_for_user(asset_admin)
        assert codes == ["DEPT-A"]

    def test_regular_user_sees_own_only(self, regular_user, dept_a):
        codes = get_department_codes_for_user(regular_user)
        assert codes == ["DEPT-A"]

    def test_no_employee_returns_none(self, db):
        user = User.objects.create_user(auth_username="noemp", password=TEST_PASSWORD)
        assert get_department_codes_for_user(user) is None


# =====================================================================
# 3. AssetSelector 行级过滤测试
# =====================================================================


