"""
my-permissions 端点与权限/数据范围查询功能测试

覆盖(G1-B flavor a + G6):
- get_effective_data_scope_for_user: superuser/无Employee/system_admin/auditor → all
- get_effective_data_scope_for_user: dept_manager → departments+include_children
- get_effective_data_scope_for_user: asset_admin/regular_user → 本部门
- get_effective_data_scope_for_user: 无部门 Employee → 最严兜底(空部门范围)
- get_effective_permissions_for_user: superuser 全量 / 无部门仅查看 / UserRole 并集 / G6 角色码回退
- MyPermissionsAPIView: 响应结构 {permissions, data_scope}
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import (
    Department,
    Employee,
    EmployeeRole,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from apps.usermanagement.services.permission_service import PermissionService
from core.department_scope import get_effective_data_scope_for_user
from core.tests import TEST_PASSWORD


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


def _make_user(username, role=None, department=None, is_superuser=False) -> AuthUser:
    """创建带 Employee 的 AuthUser(角色可选)"""
    user = AuthUser.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_is_staff=(is_superuser or role == EmployeeRole.SYSTEM_ADMIN),
    )
    user.is_superuser = is_superuser
    user.save(update_fields=["is_superuser"])
    if role:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
        )
    return user


def _role_perms(role_code: str) -> list[str]:
    """按角色码查询种子角色的权限码(独立验证用)"""
    role = Role.objects.get(role_code=role_code, is_deleted=False)
    perm_ids = RolePermission.objects.filter(role_id=role.id, is_deleted=False).values_list(
        "permission_id", flat=True
    )
    return list(
        set(
            Permission.objects.filter(id__in=perm_ids, is_deleted=False).values_list(
                "permission_code", flat=True
            )
        )
    )


@pytest.mark.django_db
class TestEffectiveDataScope:
    """G1-B flavor a 数据范围派生测试"""

    def test_superuser_scope_all(self):
        user = _make_user("su", is_superuser=True)
        assert get_effective_data_scope_for_user(user) == {"scope_type": "all"}

    def test_no_employee_scope_all(self):
        user = _make_user("noemp")
        assert get_effective_data_scope_for_user(user) == {"scope_type": "all"}

    def test_no_department_employee_scope_restrictive(self):
        """无部门 Employee:最严兜底(空部门范围,无数据访问)。"""
        user = _make_user("nodept", role=EmployeeRole.ASSET_ADMIN)
        assert get_effective_data_scope_for_user(user) == {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }

    def test_system_admin_scope_all(self):
        user = _make_user("sysadmin", role=EmployeeRole.SYSTEM_ADMIN)
        assert get_effective_data_scope_for_user(user) == {"scope_type": "all"}

    def test_auditor_scope_all(self):
        user = _make_user("auditor", role=EmployeeRole.AUDITOR)
        assert get_effective_data_scope_for_user(user) == {"scope_type": "all"}

    def test_dept_manager_scope_includes_children(self):
        dept = Department.objects.create(
            department_code="DEPT-A", department_name="A部门", path="/DEPT-A"
        )
        Department.objects.create(
            department_code="DEPT-A1", department_name="A1子部门", parent=dept, path="/DEPT-A/DEPT-A1"
        )
        user = _make_user("dm", role=EmployeeRole.DEPT_MANAGER, department=dept)
        scope = get_effective_data_scope_for_user(user)
        assert scope["scope_type"] == "departments"
        assert scope["include_children"] is True
        assert set(scope["department_codes"]) == {"DEPT-A", "DEPT-A1"}

    def test_regular_user_scope_own_department(self):
        dept = Department.objects.create(department_code="DEPT-B", department_name="B部门")
        user = _make_user("reg", role=EmployeeRole.REGULAR_USER, department=dept)
        scope = get_effective_data_scope_for_user(user)
        assert scope == {
            "scope_type": "departments",
            "department_codes": ["DEPT-B"],
            "include_children": False,
        }


@pytest.mark.django_db
class TestEffectivePermissions:
    """G6 权限码查询测试"""

    def test_superuser_all_permissions(self):
        user = _make_user("su2", is_superuser=True)
        perms = PermissionService.get_effective_permissions_for_user(user)
        all_codes = list(
            Permission.objects.filter(is_deleted=False).values_list("permission_code", flat=True)
        )
        assert set(perms) == set(all_codes)

    def test_userrole_union(self):
        dept = Department.objects.create(department_code="DEPT-C", department_name="C部门")
        user = _make_user("ur", role=EmployeeRole.ASSET_ADMIN, department=dept)
        role = Role.objects.get(role_code="asset_admin", is_deleted=False)
        UserRole.objects.create(auth_user=user, role=role, data_scope={})
        perms = PermissionService.get_effective_permissions_for_user(user)
        assert set(perms) == set(_role_perms("asset_admin"))

    def test_g6_fallback_asset_admin_without_userrole(self):
        dept = Department.objects.create(department_code="DEPT-D", department_name="D部门")
        user = _make_user("fb", role=EmployeeRole.ASSET_ADMIN, department=dept)
        perms = PermissionService.get_effective_permissions_for_user(user)
        assert set(perms) == set(_role_perms("asset_admin"))

    def test_g6_fallback_regular_user_returns_empty(self):
        dept = Department.objects.create(department_code="DEPT-E", department_name="E部门")
        user = _make_user("reg2", role=EmployeeRole.REGULAR_USER, department=dept)
        assert PermissionService.get_effective_permissions_for_user(user) == []

    def test_no_employee_returns_empty(self):
        user = _make_user("noemp2")
        assert PermissionService.get_effective_permissions_for_user(user) == []

    def test_no_department_employee_view_only_permissions(self):
        """部门级角色无部门:仅保留查看(read)权限,无任何操作权限。"""
        user = _make_user("nodept2", role=EmployeeRole.ASSET_ADMIN)
        perms = PermissionService.get_effective_permissions_for_user(user)
        read_codes = set(
            Permission.objects.filter(action="read", is_deleted=False).values_list(
                "permission_code", flat=True
            )
        )
        all_codes = set(
            Permission.objects.filter(is_deleted=False).values_list("permission_code", flat=True)
        )
        assert set(perms) == read_codes
        assert len(read_codes) > 0
        assert read_codes < all_codes

    def test_no_department_system_admin_keeps_role_permissions(self):
        """全局角色无部门:不触发最严兜底,仍按角色返回权限。"""
        user = _make_user("ndsa", role=EmployeeRole.SYSTEM_ADMIN)
        perms = PermissionService.get_effective_permissions_for_user(user)
        assert set(perms) == set(_role_perms("system_admin"))

    def test_fallback_role_soft_deleted_returns_empty(self):
        dept = Department.objects.create(department_code="DEPT-F", department_name="F部门")
        user = _make_user("sd", role=EmployeeRole.SYSTEM_ADMIN, department=dept)
        Role.objects.filter(role_code="system_admin").update(is_deleted=True)
        assert PermissionService.get_effective_permissions_for_user(user) == []


@pytest.mark.django_db
class TestMyPermissionsAPI:
    """my-permissions 端点测试"""

    def _auth_client(self, user):
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return client

    def test_regular_user_returns_expected_structure(self):
        dept = Department.objects.create(department_code="DEPT-G", department_name="G部门")
        user = _make_user("api_reg", role=EmployeeRole.REGULAR_USER, department=dept)
        client = self._auth_client(user)

        resp = client.get("/api/v1/auth/my-permissions/")
        assert resp.status_code == 200
        data = resp.data.get("data", {})
        assert "permissions" in data
        assert "data_scope" in data
        assert data["permissions"] == []
        assert data["data_scope"]["scope_type"] == "departments"
        assert data["data_scope"]["department_codes"] == ["DEPT-G"]

    def test_unauthenticated_returns_401(self):
        resp = APIClient().get("/api/v1/auth/my-permissions/")
        assert resp.status_code in (401, 403)

    def test_superuser_returns_all_permissions(self):
        user = _make_user("api_su", is_superuser=True)
        client = self._auth_client(user)

        resp = client.get("/api/v1/auth/my-permissions/")
        assert resp.status_code == 200
        data = resp.data.get("data", {})
        all_codes = set(
            Permission.objects.filter(is_deleted=False).values_list("permission_code", flat=True)
        )
        assert set(data["permissions"]) == all_codes
        assert data["data_scope"] == {"scope_type": "all"}
