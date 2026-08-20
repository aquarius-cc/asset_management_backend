"""
RoleService 测试(Step 4:D1 继承部门 / D2 同步 Employee.role / M3 自定义角色 / 审计操作者)

覆盖:
- D1: data_scope 继承 Employee 部门(含部门经理含下级、无 Employee → all、部门级无部门最严兜底、全局角色无部门 → all)
- D2: assign/remove 后 Employee.role 重算(升级/保持最高/降级/忽略自定义角色/回退 regular_user)
- M3: 自定义角色禁止分配 → AppValidationError(CUSTOM_ROLE_NOT_ASSIGNABLE)
- 审计:操作者解析(显式参数 / request 上下文 / 缺省 None)
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.usermanagement.models import Department, Employee, EmployeeRole, Role, UserRole
from apps.usermanagement.services.role_service import RoleService
from core.exceptions import AppValidationError
from core.models_audit import AuditLog
from core.tests import TEST_PASSWORD


User = get_user_model()


def _make_user(username, role=None, department=None):
    """创建带 Employee 的 AuthUser(角色可选)"""
    user = User.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_is_staff=(role == EmployeeRole.SYSTEM_ADMIN),
    )
    if role:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
        )
    return user


def _seed_role(code: str) -> Role:
    """按角色码获取种子角色"""
    return Role.objects.get(role_code=code, is_deleted=False)


@pytest.fixture
def dept(db):
    return Department.objects.create(
        department_code="DEPT-ROLE", department_name="角色测试部门", path="/DEPT-ROLE"
    )


@pytest.fixture
def dept_child(db, dept):
    return Department.objects.create(
        department_code="DEPT-ROLE1",
        department_name="角色测试子部门",
        parent=dept,
        path="/DEPT-ROLE/DEPT-ROLE1",
    )


@pytest.mark.django_db
class TestAssignRoleD1DataScope:
    """D1:data_scope 继承 Employee 部门(忽略客户端传入)"""

    def test_assign_asset_admin_syncs_employee_role_and_scope(self, dept):
        user = _make_user("r1", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id, operator_jobcode="adm")

        assert user_role.role_id == role.id
        assert user_role.data_scope == {
            "scope_type": "departments",
            "department_codes": ["DEPT-ROLE"],
            "include_children": False,
        }
        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

    def test_assign_department_manager_scope_includes_children(self, dept, dept_child):
        user = _make_user("r2", role=EmployeeRole.DEPT_MANAGER, department=dept)
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id)

        assert user_role.data_scope["scope_type"] == "departments"
        assert user_role.data_scope["include_children"] is True
        assert set(user_role.data_scope["department_codes"]) == {"DEPT-ROLE", "DEPT-ROLE1"}

    def test_assign_no_employee_scope_all(self):
        user = _make_user("r3")
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id)

        assert user_role.data_scope == {"scope_type": "all"}

    def test_assign_no_department_employee_restrictive_scope(self):
        """部门级角色无部门:data_scope 为最严兜底(空部门范围)"""
        user = _make_user("r4", role=EmployeeRole.ASSET_ADMIN)
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id)

        assert user_role.data_scope == {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }

    def test_assign_global_role_without_department_scope_all(self):
        """全局角色无部门:不触发最严兜底"""
        user = _make_user("r5", role=EmployeeRole.SYSTEM_ADMIN)
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id)

        assert user_role.data_scope == {"scope_type": "all"}


@pytest.mark.django_db
class TestAssignRoleM3:
    """M3:自定义角色禁止分配 + 参数校验"""

    def test_custom_role_rejected(self, dept):
        user = _make_user("m1", role=EmployeeRole.REGULAR_USER, department=dept)
        custom = Role.objects.create(
            role_code="custom_op", role_name="自定义角色", role_level=10, is_deleted=False
        )

        with pytest.raises(AppValidationError) as exc:
            RoleService.assign_role(user.auth_id, custom.id)

        assert exc.value.error_code == "CUSTOM_ROLE_NOT_ASSIGNABLE"
        assert not UserRole.objects.filter(auth_user=user, role=custom).exists()

    def test_nonexistent_user_raises(self):
        role = _seed_role("asset_admin")

        with pytest.raises(AppValidationError) as exc:
            RoleService.assign_role(999999, role.id)

        assert exc.value.error_code == "USER_NOT_FOUND"

    def test_nonexistent_role_raises(self):
        user = _make_user("m2")

        with pytest.raises(AppValidationError) as exc:
            RoleService.assign_role(user.auth_id, 999999)

        assert exc.value.error_code == "ROLE_NOT_FOUND"


@pytest.mark.django_db
class TestAssignRoleD2:
    """D2:分配后 Employee.role 重算"""

    def test_higher_role_upgrades_employee(self, dept):
        user = _make_user("d1", role=EmployeeRole.REGULAR_USER, department=dept)
        asset_admin = _seed_role("asset_admin")

        RoleService.assign_role(user.auth_id, asset_admin.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

    def test_lower_role_keeps_highest(self, dept):
        user = _make_user("d2", role=EmployeeRole.ASSET_ADMIN, department=dept)
        regular = _seed_role("regular_user")

        RoleService.assign_role(user.auth_id, regular.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

    def test_assign_same_role_no_downgrade(self, dept):
        user = _make_user("d3", role=EmployeeRole.ASSET_ADMIN, department=dept)
        asset_admin = _seed_role("asset_admin")

        RoleService.assign_role(user.auth_id, asset_admin.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

    def test_recompute_ignores_custom_role(self, dept):
        """M1:遗留 UserRole 中的自定义角色不参与重算"""
        user = _make_user("d4", role=EmployeeRole.REGULAR_USER, department=dept)
        custom = Role.objects.create(
            role_code="custom_legacy", role_name="遗留自定义", role_level=10, is_deleted=False
        )
        UserRole.objects.create(auth_user=user, role=custom, data_scope={})

        RoleService._recompute_employee_role(user)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.REGULAR_USER

    def test_recompute_fallback_when_only_invalid_role(self):
        """Employee.role 为幽灵自定义码且无有效 UserRole → 回退 regular_user"""
        user = User.objects.create_user(auth_username="d6", password=TEST_PASSWORD)
        Employee.objects.create(employee_jobcode="d6", employee_name="幽灵角色员工", role="ghost_role")

        RoleService._recompute_employee_role(user)

        assert Employee.objects.get(employee_jobcode="d6").role == EmployeeRole.REGULAR_USER


@pytest.mark.django_db
class TestRemoveRoleD2:
    """D2:撤销后 Employee.role 重算(可能降级)"""

    def test_remove_downgrades_employee(self, dept):
        user = _make_user("x1", role=EmployeeRole.REGULAR_USER, department=dept)
        asset_admin = _seed_role("asset_admin")
        regular = _seed_role("regular_user")

        RoleService.assign_role(user.auth_id, asset_admin.id)
        RoleService.assign_role(user.auth_id, regular.id)
        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

        RoleService.remove_role(user.auth_id, asset_admin.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.REGULAR_USER
        assert not UserRole.objects.filter(auth_user=user, role=asset_admin, is_deleted=False).exists()

    def test_remove_idempotent_noop(self, dept):
        """未分配的 UserRole:幂等,Employee.role 不变"""
        user = _make_user("x2", role=EmployeeRole.ASSET_ADMIN, department=dept)
        asset_admin = _seed_role("asset_admin")
        before = Employee.objects.get(employee_jobcode=user.auth_username).role

        RoleService.remove_role(user.auth_id, asset_admin.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == before

    def test_remove_no_employee_user_noop(self):
        user = User.objects.create_user(auth_username="x3", password=TEST_PASSWORD)
        asset_admin = _seed_role("asset_admin")
        RoleService.assign_role(user.auth_id, asset_admin.id)

        RoleService.remove_role(user.auth_id, asset_admin.id)

        assert not UserRole.objects.filter(auth_user=user, role=asset_admin).exists()

    def test_remove_non_seed_role_keeps_legacy_baseline(self, dept):
        """遗留种子(G6)不被连带撤销:asset_admin 种子 + 撤销 regular_user 分配 → 保持 asset_admin"""
        user = _make_user("x4", role=EmployeeRole.ASSET_ADMIN, department=dept)
        regular = _seed_role("regular_user")

        RoleService.assign_role(user.auth_id, regular.id)
        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN

        RoleService.remove_role(user.auth_id, regular.id)

        assert Employee.objects.get(employee_jobcode=user.auth_username).role == EmployeeRole.ASSET_ADMIN


@pytest.mark.django_db
class TestAuditOperator:
    """审计操作者解析(显式参数 / request 上下文 / 缺省 None)"""

    def _latest_audit(self, user_id, role_id):
        return (
            AuditLog.objects.filter(app_label="user_role", record_code=f"user_{user_id}_role_{role_id}")
            .order_by("-id")
            .first()
        )

    def test_assign_audit_uses_explicit_operator(self, dept):
        user = _make_user("a1", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")

        RoleService.assign_role(user.auth_id, role.id, operator_jobcode="OP001", operator_name="操作员甲")

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operation_type == "assign"
        assert log.operator_jobcode == "OP001"
        assert log.operator_name == "操作员甲"

    def test_assign_audit_operator_from_request_context(self, dept):
        from core.request_context import _thread_locals

        user = _make_user("a2", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")

        request = RequestFactory().get("/api/v1/users/")
        request.user = user
        _thread_locals.request = request
        try:
            RoleService.assign_role(user.auth_id, role.id)
        finally:
            _thread_locals.request = None

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operator_jobcode == user.auth_username

    def test_assign_audit_operator_none_without_context(self, dept):
        user = _make_user("a3", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")

        RoleService.assign_role(user.auth_id, role.id)

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operator_jobcode is None

    def test_remove_audit_uses_explicit_operator(self, dept):
        user = _make_user("a4", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")
        RoleService.assign_role(user.auth_id, role.id)

        RoleService.remove_role(user.auth_id, role.id, operator_jobcode="OP002", operator_name="操作员乙")

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operation_type == "remove"
        assert log.operator_jobcode == "OP002"
        assert log.operator_name == "操作员乙"
