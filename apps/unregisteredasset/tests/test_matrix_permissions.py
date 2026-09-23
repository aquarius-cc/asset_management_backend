"""
未登记资产 4.5 矩阵权限与行级隔离测试(F-P1-5/6/7 回归锚)

依据 Rules_Fiels/backend-business-rules.md §4.5:
- 矩阵 :187-193 角色×动作 状态码网格
- 行级隔离 :195-200(规则1 空集收敛 / 规则2 部门过滤 / 规则3 本人例外)
- 接口语义 :202-209(语义2 仅 system_admin 代录 / 语义3 approver 强制 / 语义4 越权 404)

覆盖:
- CT-1: 角色门禁与行级路径测试覆盖
- CT-4: F-P1-5(approver 代签) / F-P1-6(discovery_person 冒名) 回归锚
- CT-3 口径: 矩阵每格至少一条用例
"""

from datetime import date

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.unregisteredasset.models import UnregisteredAsset
from apps.usermanagement.models import EmployeeRole
from core.tests import TEST_PASSWORD  # noqa: F401  (确保 core.tests 环境就绪)


CREATE_BODY = {
    "scenario_type": "s1_no_record",
    "discovery_date": "2024-06-01",
    "discovery_location": "会议室A",
    "asset_name": "矩阵资产",
}

# (role_key, action, expected_status) — 矩阵 :187-193 逐格落地
MATRIX_GRID = [
    ("sys", "list", 200),
    ("dm", "list", 200),
    ("aa", "list", 200),
    ("ru", "list", 403),
    ("au", "list", 403),
    ("sys", "create", 200),
    ("dm", "create", 403),
    ("aa", "create", 200),
    ("ru", "create", 403),
    ("au", "create", 403),
    ("sys", "update", 200),
    ("dm", "update", 403),
    ("aa", "update", 200),
    ("ru", "update", 403),
    ("au", "update", 403),
    ("sys", "destroy", 200),
    ("dm", "destroy", 403),
    ("aa", "destroy", 200),
    ("ru", "destroy", 403),
    ("au", "destroy", 403),
    ("sys", "approve", 200),
    ("dm", "approve", 200),
    ("aa", "approve", 403),
    ("ru", "approve", 403),
    ("au", "approve", 403),
    ("sys", "batch_delete", 200),
    ("dm", "batch_delete", 403),
    ("aa", "batch_delete", 200),
    ("ru", "batch_delete", 403),
    ("au", "batch_delete", 403),
]


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _list_url() -> str:
    return reverse("unregisteredasset:unregisteredasset-list")


def _detail_url(code: str) -> str:
    return reverse("unregisteredasset:unregisteredasset-detail", kwargs={"unregistered_code": code})


def _approve_url(code: str) -> str:
    return reverse("unregisteredasset:unregisteredasset-approve", kwargs={"unregistered_code": code})


def _batch_delete_url() -> str:
    return reverse("unregisteredasset:unregisteredasset-batch-delete")


@pytest.fixture
def depts(db, make_dept):
    """MX_ROOT(父) ← MX_CHILD(子); MX_OTHER(兄弟, 范围外)"""
    root = make_dept("MX_ROOT")
    child = make_dept("MX_CHILD", parent=root)
    other = make_dept("MX_OTHER")
    return {"root": root, "child": child, "other": other}


@pytest.fixture
def users(db, make_role_user, depts):
    """五角色客户端: sys(无部门全量) / dm(本部门+下级) / aa(本部门) / ru / au"""
    return {
        "sys": _client(make_role_user("mx_sys", EmployeeRole.SYSTEM_ADMIN)),
        "dm": _client(make_role_user("mx_dm", EmployeeRole.DEPT_MANAGER, depts["root"])),
        "aa": _client(make_role_user("mx_aa", EmployeeRole.ASSET_ADMIN, depts["root"])),
        "ru": _client(make_role_user("mx_ru", EmployeeRole.REGULAR_USER, depts["root"])),
        "au": _client(make_role_user("mx_au", EmployeeRole.AUDITOR, depts["root"])),
    }


@pytest.fixture
def emps(db, make_plain_employee, depts):
    """发现人侧 Employee(无 AuthUser): 本部门 / 下级部门 / 范围外部门"""
    return {
        "root": make_plain_employee("mx_emp_root", depts["root"]),
        "child": make_plain_employee("mx_emp_child", depts["child"]),
        "other": make_plain_employee("mx_emp_other", depts["other"]),
    }


@pytest.fixture
def make_record(db, storage, asset_type, emps):
    """未登记资产工厂(直接 ORM, discovery 可指定, 待审批)"""

    seq = {"n": 0}

    def _make(discovery_employee, name: str = "矩阵记录") -> UnregisteredAsset:
        seq["n"] += 1
        return UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 1),
            discovery_location="会议室A",
            discovery_person=discovery_employee,
            asset_name=f"{name}-{seq['n']}",
            unregistered_asset_type=asset_type,
            estimated_value=100,
            unregistered_asset_storage=storage,
            approval_status="pending",
        )

    return _make


@pytest.mark.django_db
class TestRoleActionMatrix:
    """矩阵 :187-193 角色×动作状态码网格(每格一用例)"""

    @pytest.mark.parametrize("role_key,action,expected", MATRIX_GRID)
    def test_matrix_cell(self, users, make_record, emps, role_key, action, expected):
        client = users[role_key]

        if action == "list":
            response = client.get(_list_url())
        elif action == "create":
            response = client.post(_list_url(), CREATE_BODY, format="json")
        elif action == "batch_delete":
            record = make_record(emps["root"])
            response = client.post(_batch_delete_url(), {"ids": [record.unregistered_code]}, format="json")
        else:
            record = make_record(emps["root"])
            if action == "update":
                response = client.put(_detail_url(record.unregistered_code), {"asset_name": "改名"}, format="json")
            elif action == "destroy":
                response = client.delete(_detail_url(record.unregistered_code))
            else:  # approve
                response = client.post(
                    _approve_url(record.unregistered_code),
                    {"handle_type": "reject", "approver": "anyone"},
                    format="json",
                )

        assert response.status_code == expected, (
            f"矩阵格 ({role_key}, {action}) 期望 {expected}, 实得 {response.status_code}"
        )


@pytest.mark.django_db
class TestRowIsolation:
    """行级隔离 :195-200 与语义4(越权 404, 不泄露存在性)"""

    def test_dm_approve_out_of_dept_returns_404(self, users, make_record, emps):
        record = make_record(emps["other"])
        response = users["dm"].post(
            _approve_url(record.unregistered_code),
            {"handle_type": "reject", "approver": "mx_dm"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_aa_update_out_of_dept_returns_404(self, users, make_record, emps):
        record = make_record(emps["other"])
        response = users["aa"].put(_detail_url(record.unregistered_code), {"asset_name": "越权"}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_aa_retrieve_out_of_dept_returns_404(self, users, make_record, emps):
        record = make_record(emps["other"])
        response = users["aa"].get(_detail_url(record.unregistered_code))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_dm_retrieve_out_of_dept_returns_404(self, users, make_record, emps):
        record = make_record(emps["other"])
        response = users["dm"].get(_detail_url(record.unregistered_code))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_aa_list_excludes_out_of_dept(self, users, make_record, emps):
        in_scope = make_record(emps["root"], "范围内")
        out_scope = make_record(emps["other"], "范围外")
        response = users["aa"].get(_list_url())
        assert response.status_code == status.HTTP_200_OK
        codes = {row["unregistered_code"] for row in response.data["data"]["results"]}
        assert in_scope.unregistered_code in codes
        assert out_scope.unregistered_code not in codes

    def test_dm_list_includes_child_dept(self, users, make_record, emps):
        """规则2: dept_manager 本部门+下级(:192)"""
        child_record = make_record(emps["child"], "下级部门记录")
        response = users["dm"].get(_list_url())
        codes = {row["unregistered_code"] for row in response.data["data"]["results"]}
        assert child_record.unregistered_code in codes

    def test_sys_list_sees_all_depts(self, users, make_record, emps):
        root_record = make_record(emps["root"])
        other_record = make_record(emps["other"])
        response = users["sys"].get(_list_url())
        codes = {row["unregistered_code"] for row in response.data["data"]["results"]}
        assert root_record.unregistered_code in codes
        assert other_record.unregistered_code in codes

    def test_aa_batch_delete_out_of_scope_returns_not_found(self, users, make_record, emps):
        """B14 + 语义4: 越权条目逐条跳过, 与不存在同构 NOT_FOUND, 记录不被删除"""
        record = make_record(emps["other"])
        response = users["aa"].post(_batch_delete_url(), {"ids": [record.unregistered_code]}, format="json")

        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["success_count"] == 0
        assert data["fail_items"][0]["error_code"] == "NOT_FOUND"
        assert UnregisteredAsset.objects.filter(unregistered_code=record.unregistered_code).exists()

    def test_aa_batch_delete_in_scope_succeeds(self, users, make_record, emps):
        """B14: 本部门条目正常删除"""
        record = make_record(emps["root"])
        response = users["aa"].post(_batch_delete_url(), {"ids": [record.unregistered_code]}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 1
        assert not UnregisteredAsset.objects.filter(unregistered_code=record.unregistered_code).exists()


@pytest.mark.django_db
class TestFp15ApproverOverride:
    """F-P1-5: 语义3 — approver 强制=当前审批人, 覆盖客户端传入值(防代签)"""

    def test_approver_forced_to_current_operator(self, users, make_record, emps):
        record = make_record(emps["root"])
        response = users["dm"].post(
            _approve_url(record.unregistered_code),
            {"handle_type": "reject", "approver": "mx_ru", "approval_remark": "代签尝试"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        record.refresh_from_db()
        assert record.approver is not None
        assert record.approver.employee_jobcode == "mx_dm"


@pytest.mark.django_db
class TestFp16DiscoveryWhitelist:
    """F-P1-6: 语义2 — 仅 system_admin 可代录 discovery_person;语义5 operator 解耦"""

    def test_asset_admin_proxy_discovery_denied_403(self, users, emps):
        body = {**CREATE_BODY, "discovery_person": emps["root"].employee_jobcode}
        response = users["aa"].post(_list_url(), body, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_asset_admin_create_defaults_to_self(self, users):
        response = users["aa"].post(_list_url(), CREATE_BODY, format="json")
        assert response.status_code == status.HTTP_200_OK

        record = UnregisteredAsset.objects.get(unregistered_code=response.data["data"]["unregistered_code"])
        assert record.discovery_person.employee_jobcode == "mx_aa"

    def test_system_admin_proxy_allowed(self, users, emps):
        body = {**CREATE_BODY, "discovery_person": emps["root"].employee_jobcode}
        response = users["sys"].post(_list_url(), body, format="json")
        assert response.status_code == status.HTTP_200_OK

        record = UnregisteredAsset.objects.get(unregistered_code=response.data["data"]["unregistered_code"])
        assert record.discovery_person.employee_jobcode == emps["root"].employee_jobcode

    def test_create_with_unknown_discovery_returns_400(self, users):
        body = {**CREATE_BODY, "discovery_person": "NO-SUCH-JOBCODE"}
        response = users["sys"].post(_list_url(), body, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
