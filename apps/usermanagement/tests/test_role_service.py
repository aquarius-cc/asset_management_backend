"""
RoleService 测试(Step 4:D1 继承部门 / D2 同步 Employee.role / M3 自定义角色 / 审计操作者)

覆盖:
- D1: data_scope 继承 Employee 部门(含部门经理含下级、无 Employee → 空部门范围、部门级无部门最严兜底、全局角色无部门 → all)
- D2: assign/remove 后 Employee.role 重算(升级/保持最高/降级/忽略自定义角色/回退 regular_user)
- M3: 自定义角色禁止分配 → AppValidationError(CUSTOM_ROLE_NOT_ASSIGNABLE)
- 审计:操作者解析(显式参数 / request 上下文 / 缺省 None)
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase as DjangoTestCase
from django.urls import reverse

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
    return Department.objects.create(department_code="DEPT-ROLE", department_name="角色测试部门", path="/DEPT-ROLE")


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

    def test_assign_no_employee_restrictive_scope(self):
        """AUD-21:无 Employee → 空部门范围(拒绝),不再 all"""
        user = _make_user("r3")
        role = _seed_role("asset_admin")

        user_role = RoleService.assign_role(user.auth_id, role.id)

        assert user_role.data_scope == {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }

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
        custom = Role.objects.create(role_code="custom_op", role_name="自定义角色", role_level=10, is_deleted=False)

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
        custom = Role.objects.create(role_code="custom_legacy", role_name="遗留自定义", role_level=10, is_deleted=False)
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

        with DjangoTestCase.captureOnCommitCallbacks(execute=True):
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
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                RoleService.assign_role(user.auth_id, role.id)
        finally:
            _thread_locals.request = None

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operator_jobcode == user.auth_username

    def test_assign_audit_operator_none_without_context(self, dept):
        user = _make_user("a3", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")

        with DjangoTestCase.captureOnCommitCallbacks(execute=True):
            RoleService.assign_role(user.auth_id, role.id)

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operator_jobcode is None

    def test_remove_audit_uses_explicit_operator(self, dept):
        user = _make_user("a4", role=EmployeeRole.REGULAR_USER, department=dept)
        role = _seed_role("asset_admin")
        with DjangoTestCase.captureOnCommitCallbacks(execute=True):
            RoleService.assign_role(user.auth_id, role.id)
            RoleService.remove_role(user.auth_id, role.id, operator_jobcode="OP002", operator_name="操作员乙")

        log = self._latest_audit(user.auth_id, role.id)
        assert log is not None
        assert log.operation_type == "remove"
        assert log.operator_jobcode == "OP002"
        assert log.operator_name == "操作员乙"


def _plain_role(code: str, *, is_system: bool = False) -> Role:
    """独立建角色(不依赖 init 种子,判定面单一)"""
    return Role.objects.create(role_code=code, role_name=f"{code}角色", role_level=1, is_system=is_system)


def _assign(role: Role, username: str, dept) -> UserRole:
    """建用户并挂活跃 UserRole(auth/employee 均为部分唯一约束,双用户须补唯一电话)"""
    user = _make_user(username, role=EmployeeRole.REGULAR_USER, department=dept)
    user.auth_phone = f"139{abs(hash(username)) % 10**8:08d}"
    user.save(update_fields=["auth_phone"])
    Employee.objects.filter(employee_jobcode=username).update(
        employee_phone=f"138{abs(hash(username)) % 10**8:08d}"
    )
    return UserRole.objects.create(auth_user=user, role=role)


@pytest.mark.django_db
class TestDeleteRoleService:
    """M-29: RoleService.delete_role(View 内联守卫下沉,锁内复检后软删)"""

    def test_system_role_rejected(self, dept):
        role = _plain_role("sys_x", is_system=True)

        with pytest.raises(AppValidationError) as exc:
            RoleService.delete_role(role)

        assert exc.value.error_code == "SYSTEM_ROLE_NOT_DELETABLE"
        role.refresh_from_db()
        assert role.is_deleted is False

    def test_active_assignment_rejected(self, dept):
        role = _plain_role("busy_x")
        _assign(role, "del_r1", dept)

        with pytest.raises(AppValidationError) as exc:
            RoleService.delete_role(role)

        assert exc.value.error_code == "ROLE_IN_USE"
        role.refresh_from_db()
        assert role.is_deleted is False

    def test_success_soft_deletes_unassigned_role(self, dept):
        role = _plain_role("free_x")

        RoleService.delete_role(role)

        role.refresh_from_db()
        assert role.is_deleted is True

    def test_soft_deleted_assignment_does_not_block(self, dept):
        role = _plain_role("retired_x")
        assignment = _assign(role, "del_r2", dept)
        assignment.is_deleted = True
        assignment.save()

        RoleService.delete_role(role)

        role.refresh_from_db()
        assert role.is_deleted is True

    def test_failure_rolls_back_to_live_role(self, dept, monkeypatch):
        role = _plain_role("rb_x")

        def explode(self, *args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(Role, "delete", explode)
        with pytest.raises(RuntimeError):
            RoleService.delete_role(role)

        role.refresh_from_db()
        assert role.is_deleted is False


@pytest.mark.django_db
class TestDeleteRoleViewContract:
    """M-29 View 契约:400 文案逐字 / 200 信封 / 404 / 403(权限面 P3-9 收紧后)"""

    def _admin(self, dept):
        return _make_user("rva1", role=EmployeeRole.SYSTEM_ADMIN, department=dept)

    def test_system_role_400_verbatim(self, dept):
        from rest_framework.test import APIClient

        role = _plain_role("vsys_x", is_system=True)
        client = APIClient()
        client.force_authenticate(user=self._admin(dept))
        resp = client.delete(reverse("roles-detail", kwargs={"pk": role.pk}))

        assert resp.status_code == 400
        assert resp.data["code"] != 0
        assert resp.data["message"] == "系统内置角色不可删除"
        role.refresh_from_db()
        assert role.is_deleted is False

    def test_in_use_role_400_verbatim(self, dept):
        from rest_framework.test import APIClient

        role = _plain_role("vbusy_x")
        _assign(role, "del_v1", dept)
        client = APIClient()
        client.force_authenticate(user=self._admin(dept))
        resp = client.delete(reverse("roles-detail", kwargs={"pk": role.pk}))

        assert resp.status_code == 400
        assert resp.data["message"] == "该角色已分配给用户,不可删除。请先移除所有用户的角色分配。"

    def test_success_200_envelope(self, dept):
        from rest_framework.test import APIClient

        role = _plain_role("vfree_x")
        client = APIClient()
        client.force_authenticate(user=self._admin(dept))
        resp = client.delete(reverse("roles-detail", kwargs={"pk": role.pk}))

        assert resp.status_code == 200
        assert resp.data["code"] == 0
        assert resp.data["message"] == "删除成功"
        role.refresh_from_db()
        assert role.is_deleted is True

    def test_unknown_pk_404(self, dept):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self._admin(dept))
        resp = client.delete(reverse("roles-detail", kwargs={"pk": 987654321}))

        assert resp.status_code == 404
        assert resp.data["message"] == "资源不存在或已被删除"

    def test_regular_user_403(self, dept):
        from rest_framework.test import APIClient

        role = _plain_role("v_forbid_x")
        user = _make_user("del_v2", role=EmployeeRole.REGULAR_USER, department=dept)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.delete(reverse("roles-detail", kwargs={"pk": role.pk}))

        assert resp.status_code == 403
        role.refresh_from_db()
        assert role.is_deleted is False
