"""
RoleSelector 与 PermissionService.get_auth_user_by_username 单源锚定(M-41)

锚定收编后行为不变:
- get_active_user_roles: user_id 分支过滤活跃分配;无 user_id 仅当前用户(防信息泄露);软删分配不可见
- get_active_permission_codes: 仅 is_deleted=False 的 RolePermission 派生权限码
- get_auth_user_by_username: 命中返回实例;不存在返回 None(不抛异常,P1-6 语义保持)
"""

import pytest
from django.db.models import QuerySet

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole, Permission, Role, RolePermission, UserRole
from apps.usermanagement.selectors import RoleSelector
from apps.usermanagement.services import PermissionService
from core.tests import TEST_PASSWORD


def _user(username: str, department: Department) -> AuthUser:
    user = AuthUser.objects.create_user(
        auth_username=username, password=TEST_PASSWORD, auth_phone=f"139{abs(hash(username)) % 10**8:08d}"
    )
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}员工",
        employee_department=department,
        role=EmployeeRole.REGULAR_USER,
        employee_phone=f"138{abs(hash(username)) % 10**8:08d}",
    )
    return user


@pytest.fixture
def dept(db):
    return Department.objects.create(department_code="DEPT-M41", department_name="M41 挑选器部门")


@pytest.fixture
def role(db) -> Role:
    return Role.objects.create(role_code="m41_role", role_name="M41 角色", role_level=1)


@pytest.fixture
def permission(db) -> Permission:
    return Permission.objects.create(permission_code="m41:read", module="m41", action="read")


@pytest.mark.django_db
class TestRoleSelectorUserScopes:
    """get_active_user_roles 三分支锚定"""

    def test_user_id_branch_excludes_soft_deleted(self, dept, role, permission):
        user = _user("m41a", dept)
        active = UserRole.objects.create(auth_user=user, role=role)
        gone_role = Role.objects.create(role_code="m41_gone", role_name="M41 已分配", role_level=1)
        UserRole.objects.create(auth_user=user, role=gone_role, is_deleted=True)

        qs = RoleSelector.get_active_user_roles(user.auth_id, None)

        assert isinstance(qs, QuerySet)
        assert list(qs) == [active]

    def test_no_user_id_branch_scopes_to_current_user(self, dept, role):
        me = _user("m41b", dept)
        other = _user("m41c", dept)
        mine = UserRole.objects.create(auth_user=me, role=role)
        UserRole.objects.create(auth_user=other, role=role)

        qs = RoleSelector.get_active_user_roles(None, me)

        assert list(qs) == [mine]

    def test_soft_deleted_roles_not_returned_with_assignment(self, dept, role):
        user = _user("m41d", dept)
        UserRole.objects.create(auth_user=user, role=role, is_deleted=True)

        qs = RoleSelector.get_active_user_roles(user.auth_id, None)

        assert list(qs) == []


@pytest.mark.django_db
class TestRoleSelectorPermissionCodes:
    """get_active_permission_codes 软删过滤"""

    def test_active_only(self, role, permission):
        RolePermission.objects.create(role=role, permission=permission)
        deleted_perm = Permission.objects.create(permission_code="m41:gone", module="m41", action="delete")
        RolePermission.objects.create(role=role, permission=deleted_perm, is_deleted=True)

        codes = RoleSelector.get_active_permission_codes(role)

        assert codes == ["m41:read"]

    def test_empty_when_no_binding(self, role):
        assert RoleSelector.get_active_permission_codes(role) == []


@pytest.mark.django_db
class TestGetAuthUserByUsername:
    """PermissionService.get_auth_user_by_username 语义锚定(不抛异常)"""

    def test_found_returns_instance(self, dept):
        user = _user("m41e", dept)

        got = PermissionService.get_auth_user_by_username("m41e")

        assert got is not None
        assert got.auth_id == user.auth_id

    def test_missing_returns_none(self, db):
        assert PermissionService.get_auth_user_by_username("ghost_m41") is None
