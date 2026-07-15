"""
RBAC 权限矩阵自动化测试

覆盖范围：
- 权限类测试（IsSystemAdmin / IsDeptManagerOrAbove / IsAssetAdminOrAbove / IsAuditorOrAdmin）
- 行级数据隔离测试（get_department_codes_for_user / get_queryset_for_user）
- 资产部门归属动态解析测试（resolve_asset_department_codes）
- 边界场景测试（无 Employee / is_superuser / 跨部门）
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.assetmanagement.models import Asset, AssetType, Storage
from apps.assetmanagement.selectors.asset_selector import AssetSelector
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.department_scope import (
    get_asset_linked_queryset_for_user,
    get_department_codes_for_user,
    resolve_asset_department_codes,
)
from core.permissions import (
    IsAssetAdminOrAbove,
    IsAuditorOrAdmin,
    IsDeptManagerOrAbove,
    IsSystemAdmin,
)

User = get_user_model()

# =====================================================================
# Helpers
# =====================================================================

_counter = 0


def _uid():
    global _counter
    _counter += 1
    return f"U{_counter:03d}"


def _make_user(username, role, department=None):
    """创建带角色的 AuthUser + Employee（jobcode ≤ 20 字符）"""
    user = User.objects.create_user(
        auth_username=username, password="test1234",
        auth_is_staff=(role == EmployeeRole.SYSTEM_ADMIN),
    )
    Employee.objects.create(
        employee_jobcode=username, employee_name=f"{username}员工",
        employee_department=department, role=role,
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
        department_code="DEPT-B1", department_name="B1子部门", parent=dept_b,
    )


@pytest.fixture
def storage_a(db, dept_a):
    """A 部门的仓库"""
    emp = Employee.objects.create(
        employee_jobcode="WH-A", employee_name="A仓管",
        employee_department=dept_a, role=EmployeeRole.ASSET_ADMIN,
    )
    return Storage.objects.create(
        storage_code="SA-001", storage_name="A仓库",
        storage_address="A地址", storage_manager=emp,
    )


@pytest.fixture
def storage_b(db, dept_b):
    """B 部门的仓库"""
    emp = Employee.objects.create(
        employee_jobcode="WH-B", employee_name="B仓管",
        employee_department=dept_b, role=EmployeeRole.ASSET_ADMIN,
    )
    return Storage.objects.create(
        storage_code="SB-001", storage_name="B仓库",
        storage_address="B地址", storage_manager=emp,
    )


@pytest.fixture
def asset_in_dept_a(db, dept_a, storage_a):
    """归属 A 部门的资产（通过 entry_person 关联）"""
    entry_person = Employee.objects.create(
        employee_jobcode="EP-A1", employee_name="入库员A1",
        employee_department=dept_a, role=EmployeeRole.ASSET_ADMIN,
    )
    asset_type = AssetType.objects.create(type_code="T001", type_name="电脑")
    return Asset.objects.create(
        asset_code="AST-A001", asset_name="A部门资产",
        asset_purchase_price=5000, asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_type_recordcode=asset_type,
        asset_storage_recordcode=storage_a,
        asset_entry_person_recordcode=entry_person,
        asset_current_status="in_store",
    )


@pytest.fixture
def asset_in_dept_b(db, dept_b, storage_b):
    """归属 B 部门的资产（通过 manager 关联，使用 B 部门的仓库）"""
    manager = Employee.objects.create(
        employee_jobcode="MG-B1", employee_name="保管人B1",
        employee_department=dept_b, role=EmployeeRole.ASSET_ADMIN,
    )
    asset_type = AssetType.objects.create(type_code="T002", type_name="显示器")
    return Asset.objects.create(
        asset_code="AST-B001", asset_name="B部门资产",
        asset_purchase_price=3000, asset_purchase_date="2024-02-01",
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
        su = User.objects.create_superuser(auth_username="su", password="test1234")
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
        user = User.objects.create_user(auth_username="noemp", password="test1234")
        assert get_department_codes_for_user(user) is None


# =====================================================================
# 3. AssetSelector 行级过滤测试
# =====================================================================


class TestAssetSelectorRowIsolation:
    def test_admin_sees_all(self, sys_admin, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(sys_admin)
        assert qs.count() == 2

    def test_auditor_sees_all(self, auditor, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(auditor)
        assert qs.count() == 2

    def test_dept_a_manager_sees_dept_a_only(self, dept_manager, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(dept_manager)
        codes = list(qs.values_list("asset_code", flat=True))
        assert "AST-A001" in codes
        assert "AST-B001" not in codes

    def test_dept_a_asset_admin_sees_dept_a_only(self, asset_admin, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(asset_admin)
        codes = list(qs.values_list("asset_code", flat=True))
        assert "AST-A001" in codes
        assert "AST-B001" not in codes

    def test_dept_b_asset_admin_sees_dept_b_only(self, asset_admin_b, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(asset_admin_b)
        codes = list(qs.values_list("asset_code", flat=True))
        assert "AST-B001" in codes
        assert "AST-A001" not in codes

    def test_regular_user_read_only(self, regular_user, asset_in_dept_a, asset_in_dept_b):
        qs = AssetSelector.get_queryset_for_user(regular_user)
        codes = list(qs.values_list("asset_code", flat=True))
        assert "AST-A001" in codes
        assert "AST-B001" not in codes


# =====================================================================
# 4. 资产部门归属动态解析测试
# =====================================================================


class TestResolveAssetDepartment:
    def test_resolves_via_manager(self, asset_in_dept_b):
        codes = resolve_asset_department_codes(asset_in_dept_b)
        assert codes is not None
        assert "DEPT-B" in codes

    def test_resolves_via_entry_person(self, asset_in_dept_a):
        codes = resolve_asset_department_codes(asset_in_dept_a)
        assert codes is not None
        assert "DEPT-A" in codes

    def test_resolves_via_storage_manager(self, db, storage_a):
        """manager 和 entry_person 都为空时通过 storage.manager 解析"""
        asset_type = AssetType.objects.create(type_code="T999", type_name="空资产")
        asset = Asset.objects.create(
            asset_code="AST-NULL", asset_name="无归属资产",
            asset_purchase_price=1000, asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_type_recordcode=asset_type,
            asset_storage_recordcode=storage_a,
            asset_current_status="in_store",
        )
        codes = resolve_asset_department_codes(asset)
        assert codes is not None
        assert "DEPT-A" in codes  # storage_a 的 manager 在 dept_a


# =====================================================================
# 5. 资产关联记录行级过滤测试
# =====================================================================


class TestAssetLinkedRowIsolation:
    def test_filters_by_department(self, asset_admin, asset_in_dept_a, asset_in_dept_b):
        from apps.assetmanagement.models import OutAsset
        OutAsset.objects.create(asset_recordcode=asset_in_dept_a, outasset_date="2024-01-01")
        OutAsset.objects.create(asset_recordcode=asset_in_dept_b, outasset_date="2024-02-01")
        qs = get_asset_linked_queryset_for_user(asset_admin, OutAsset.objects.all())
        assert qs.count() == 1
        assert qs.first().asset_recordcode.asset_code == "AST-A001"

    def test_admin_sees_all_linked(self, sys_admin, asset_in_dept_a, asset_in_dept_b):
        from apps.assetmanagement.models import OutAsset
        OutAsset.objects.create(asset_recordcode=asset_in_dept_a, outasset_date="2024-01-01")
        OutAsset.objects.create(asset_recordcode=asset_in_dept_b, outasset_date="2024-02-01")
        qs = get_asset_linked_queryset_for_user(sys_admin, OutAsset.objects.all())
        assert qs.count() == 2


# =====================================================================
# 6. 参数化权限矩阵测试（短 jobcode）
# =====================================================================


# 权限类 → (role, module, expected)
PERM_CASES = [
    # IsSystemAdmin
    ("sa", EmployeeRole.SYSTEM_ADMIN, "asset", True),
    ("sa", EmployeeRole.SYSTEM_ADMIN, "storage", True),
    # IsAssetAdminOrAbove
    ("dm", EmployeeRole.DEPT_MANAGER, "asset", True),
    ("dm", EmployeeRole.DEPT_MANAGER, "damaged", True),
    ("dm", EmployeeRole.DEPT_MANAGER, "storage", False),
    ("aa", EmployeeRole.ASSET_ADMIN, "asset", True),
    ("aa", EmployeeRole.ASSET_ADMIN, "damaged", False),
    ("aa", EmployeeRole.ASSET_ADMIN, "storage", False),
    # Regular / Auditor
    ("ru", EmployeeRole.REGULAR_USER, "asset", False),
    ("ru", EmployeeRole.REGULAR_USER, "storage", False),
    ("au", EmployeeRole.AUDITOR, "asset", False),
    ("au", EmployeeRole.AUDITOR, "storage", False),
]


@pytest.mark.parametrize("suffix,role,module,expected", PERM_CASES)
def test_write_permission_matrix(suffix, role, module, expected, db):
    """写操作权限矩阵：角色 × 模块"""
    user = _make_user(f"t{suffix}_{module[:3]}", role)
    perm_map = {
        "asset": IsAssetAdminOrAbove,
        "damaged": IsDeptManagerOrAbove,
        "storage": IsSystemAdmin,
    }
    perm = perm_map[module]()
    request = RequestFactory().get("/api/test/")
    request.user = user
    result = perm.has_permission(request, None)
    assert result == expected, f"Role={role}, Module={module}: expected {expected}, got {result}"


AUDIT_CASES = [
    (EmployeeRole.SYSTEM_ADMIN, True),
    (EmployeeRole.DEPT_MANAGER, False),
    (EmployeeRole.ASSET_ADMIN, False),
    (EmployeeRole.REGULAR_USER, False),
    (EmployeeRole.AUDITOR, True),
]


@pytest.mark.parametrize("role,expected", AUDIT_CASES)
def test_audit_log_permission_matrix(role, expected, db):
    """审计日志查看权限矩阵"""
    user = _make_user(f"al_{role[:3]}", role)
    perm = IsAuditorOrAdmin()
    request = RequestFactory().get("/api/test/")
    request.user = user
    result = perm.has_permission(request, None)
    assert result == expected, f"Role={role}: expected {expected}, got {result}"


# =====================================================================
# 7. 边界场景测试
# =====================================================================


class TestEdgeCases:
    def test_superuser_bypasses_all(self, db):
        su = User.objects.create_superuser(auth_username="su_t", password="test1234")
        for cls in [IsSystemAdmin, IsDeptManagerOrAbove, IsAssetAdminOrAbove, IsAuditorOrAdmin]:
            perm = cls()
            request = RequestFactory().get("/api/test/")
            request.user = su
            assert perm.has_permission(request, None) is True

    def test_no_employee_defaults_to_unrestricted(self, db):
        user = User.objects.create_user(auth_username="no_emp", password="test1234")
        codes = get_department_codes_for_user(user)
        assert codes is None

    def test_employee_no_department_defaults_to_unrestricted(self, db):
        Employee.objects.create(
            employee_jobcode="nd", employee_name="无部门",
            employee_department=None, role=EmployeeRole.ASSET_ADMIN,
        )
        user = User.objects.create_user(auth_username="nd", password="test1234")
        codes = get_department_codes_for_user(user)
        assert codes is None

    def test_request_level_caching(self, asset_admin):
        codes1 = get_department_codes_for_user(asset_admin)
        codes2 = get_department_codes_for_user(asset_admin)
        assert codes1 == codes2
        assert hasattr(asset_admin, "_rbac_employee")
