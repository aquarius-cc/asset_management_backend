"""
audit_orphan_accounts 命令核查测试（AUD-21 批次2）

覆盖：孤儿判定口径（含软删员工算孤儿）、JSON 输出、--active-only 过滤、只读语义。
"""

import io
import json
import zlib
from typing import Any

import pytest
from django.core.management import call_command

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee
from core.tests import TEST_PASSWORD


def _make_user(username: str, active: bool = True) -> AuthUser:
    # unique_auth_phone_active 对启用账号按 auth_phone 条件唯一(空串也参与)，
    # 同一用例内多账号必须给出互异手机号
    phone = f"138{zlib.crc32(username.encode()) % 10**10:010d}"
    return AuthUser.objects.create_user(
        auth_username=username, password=TEST_PASSWORD, auth_is_active=active, auth_phone=phone
    )


def _link_employee(username: str) -> Employee:
    return Employee.objects.create(employee_jobcode=username, employee_name=f"{username}员工")


def _run(*args: str) -> dict[str, Any]:
    out = io.StringIO()
    call_command("audit_orphan_accounts", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestAuditOrphanAccounts:
    def test_orphan_detected_and_linked_excluded(self):
        _make_user("orphan_u1")
        _make_user("linked_u1")
        _link_employee("linked_u1")
        text = _run()
        assert "orphan_u1" in text
        assert "linked_u1" not in text
        assert "summary total=2 linked=1 orphan=1" in text

    def test_soft_deleted_employee_counts_as_orphan(self):
        user = _make_user("del_emp_u1")
        employee = _link_employee("del_emp_u1")
        employee.delete()  # 软删后默认 manager 不可见 → RBAC 链路断 → 孤儿
        assert AuthUser.objects.filter(auth_username=user.auth_username).exists()
        text = _run()
        assert "del_emp_u1" in text
        assert "orphan=1" in text

    def test_json_output_shape(self):
        _make_user("orphan_json")
        _make_user("linked_json")
        _link_employee("linked_json")
        payload = json.loads(_run("--json"))
        assert payload["total"] == 2
        assert payload["linked"] == 1
        assert payload["orphan_count"] == 1
        assert payload["orphans"][0]["auth_username"] == "orphan_json"
        assert payload["orphans"][0]["auth_is_active"] is True

    def test_active_only_excludes_inactive_orphans(self):
        _make_user("inactive_orphan", active=False)
        _make_user("active_orphan")
        payload = json.loads(_run("--json", "--active-only"))
        names = [row["auth_username"] for row in payload["orphans"]]
        assert names == ["active_orphan"]
        assert payload["total"] == 1

    def test_read_only_no_writes(self):
        _make_user("ro_orphan")
        before = AuthUser.objects.filter(auth_username="ro_orphan").values("auth_id", "auth_is_active")[0]
        _run()
        after = AuthUser.objects.filter(auth_username="ro_orphan").values("auth_id", "auth_is_active")[0]
        assert before == after
