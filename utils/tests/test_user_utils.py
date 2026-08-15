"""
resolve_operator 三级绑定降级测试

覆盖 utils/user_utils.py 的三种解析路径:
  1. Employee.auth_user 外键绑定(user.employee)
  2. 命名约定绑定(auth_username == employee_jobcode,无 FK)
  3. 未绑定兜底(auth_username)
"""

from typing import Any, cast

import pytest

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee, EmployeeRole
from utils.user_utils import resolve_operator


def _create_user(username: str) -> AuthUser:
    return cast(
        AuthUser,
        AuthUser.objects.create_user(auth_username=username, password="test1234", auth_phone="13800138000"),
    )


def _create_employee(jobcode: str, name: str, user: AuthUser | None = None) -> Employee:
    return cast(
        Employee,
        Employee.objects.create(
            employee_jobcode=jobcode,
            employee_name=name,
            employee_department=None,
            role=EmployeeRole.SYSTEM_ADMIN,
            employee_phone="13800138000",
            employee_location="测试地点",
            auth_user=user,
        ),
    )


class TestResolveOperatorFKBound:
    def test_returns_employee_jobcode_and_name(self, db: Any) -> None:
        user = _create_user("fk_user1")
        _create_employee("EMP001", "张三", user=user)
        assert resolve_operator(user) == ("EMP001", "张三")

    def test_prefers_fk_over_username(self, db: Any) -> None:
        user = _create_user("different_login_name")
        _create_employee("EMP002", "李四", user=user)
        assert resolve_operator(user) == ("EMP002", "李四")


class TestResolveOperatorConventionBound:
    def test_resolves_via_jobcode_when_no_fk(self, db: Any) -> None:
        user = _create_user("adminuser")
        _create_employee("adminuser", "系统管理员")
        assert resolve_operator(user) == ("adminuser", "系统管理员")


class TestResolveOperatorUnbound:
    def test_falls_back_to_username(self, db: Any) -> None:
        user = _create_user("plain_user")
        assert resolve_operator(user) == ("plain_user", "plain_user")

    @pytest.mark.parametrize("username", ["123", "admin1", "x"])
    def test_never_returns_auth_id(self, db: Any, username: str) -> None:
        user = _create_user(username)
        result = resolve_operator(user)
        assert result == (username, username)
        assert str(user.auth_id) not in result
