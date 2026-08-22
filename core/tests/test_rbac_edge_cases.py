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
class TestEdgeCases:
    def test_superuser_bypasses_all(self, db):
        su = User.objects.create_superuser(auth_username="su_t", password=TEST_PASSWORD)
        for cls in [IsSystemAdmin, IsDeptManagerOrAbove, IsAssetAdminOrAbove, IsAuditorOrAdmin]:
            perm = cls()
            request = RequestFactory().get("/api/test/")
            request.user = su
            assert perm.has_permission(request, None) is True

    def test_no_employee_defaults_to_unrestricted(self, db):
        user = User.objects.create_user(auth_username="no_emp", password=TEST_PASSWORD)
        codes = get_department_codes_for_user(user)
        assert codes is None

    def test_employee_no_department_restricted(self, db):
        Employee.objects.create(
            employee_jobcode="nd",
            employee_name="无部门",
            employee_department=None,
            role=EmployeeRole.ASSET_ADMIN,
            employee_phone=_phone(),
        )
        user = User.objects.create_user(auth_username="nd", password=TEST_PASSWORD)
        codes = get_department_codes_for_user(user)
        assert codes == []

    def test_employee_no_department_effective_scope_restrictive(self, db):
        """无部门 Employee:有效数据范围为最严兜底(空部门范围)。"""
        from core.department_scope import get_effective_data_scope_for_user

        Employee.objects.create(
            employee_jobcode="nds",
            employee_name="无部门",
            employee_department=None,
            role=EmployeeRole.ASSET_ADMIN,
            employee_phone=_phone(),
        )
        user = User.objects.create_user(auth_username="nds", password=TEST_PASSWORD)
        scope = get_effective_data_scope_for_user(user)
        assert scope == {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }

    def test_request_level_caching(self, asset_admin):
        codes1 = get_department_codes_for_user(asset_admin)
        codes2 = get_department_codes_for_user(asset_admin)
        assert codes1 == codes2
        assert hasattr(asset_admin, "_rbac_employee")


# =====================================================================
# 8. 无部门最严兜底(写权限降级)
# =====================================================================


class TestNoDepartmentWriteDegradation:
    """部门级角色无部门时,所有 RBAC 写权限类必须拒绝(与 read-only 权限码/空数据范围语义一致)。"""

    def _make_no_dept_user(self, username, role):
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}无部门",
            employee_department=None,
            role=role,
            employee_phone=_phone(),
        )
        return User.objects.create_user(auth_username=username, password=TEST_PASSWORD)

    def _check(self, perm_class, user):
        perm = perm_class()
        request = RequestFactory().get("/api/test/")
        request.user = user
        return perm.has_permission(request, None)

    def test_no_dept_asset_admin_rejected_by_write_classes(self, db):
        user = self._make_no_dept_user("nda1", EmployeeRole.ASSET_ADMIN)
        assert self._check(IsAssetAdminOrAbove, user) is False
        assert self._check(IsDeptManagerOrAbove, user) is False
        assert self._check(IsSystemAdmin, user) is False

    def test_no_dept_dept_manager_rejected_by_approval_write(self, db):
        user = self._make_no_dept_user("ndm1", EmployeeRole.DEPT_MANAGER)
        assert self._check(IsDeptManagerOrAbove, user) is False
        assert self._check(IsAssetAdminOrAbove, user) is False

    def test_no_dept_regular_user_rejected_by_all(self, db):
        user = self._make_no_dept_user("ndr1", EmployeeRole.REGULAR_USER)
        for cls in [IsSystemAdmin, IsDeptManagerOrAbove, IsAssetAdminOrAbove, IsAuditorOrAdmin]:
            assert self._check(cls, user) is False

    def test_no_dept_system_admin_exempt_global(self, db):
        user = self._make_no_dept_user("ndsa1", EmployeeRole.SYSTEM_ADMIN)
        assert self._check(IsSystemAdmin, user) is True
        assert self._check(IsDeptManagerOrAbove, user) is True
        assert self._check(IsAssetAdminOrAbove, user) is True

    def test_no_dept_auditor_exempt_global(self, db):
        user = self._make_no_dept_user("ndau1", EmployeeRole.AUDITOR)
        assert self._check(IsAuditorOrAdmin, user) is True
        assert self._check(IsAssetAdminOrAbove, user) is False

    def test_with_dept_asset_admin_still_allowed(self, asset_admin):
        """对照组:有部门的 asset_admin 写权限不受影响(无回归)。"""
        assert self._check(IsAssetAdminOrAbove, asset_admin) is True
        assert self._check(IsSystemAdmin, asset_admin) is False
