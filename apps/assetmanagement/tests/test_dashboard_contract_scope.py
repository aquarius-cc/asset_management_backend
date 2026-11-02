"""Dashboard 合同统计隔离测试（BF-170 批次 3 M-12，[HALT] D3 拍板口径落地）。

【锁定的不变量】
overview 端点的 total_contracts 可见性与 BF-127 合同读权限（system_admin-only）对齐：

- 仅 system_admin（含 superuser）返回真值
- dept_manager / asset_admin / regular_user / auditor 恒为 0
- auditor 用例专门锁定「不能用 get_department_codes_for_user 做 gate」的坑：
  auditor 的 dept_codes 为 None（全局角色不限部门），若用它当 gate，auditor 会
  看到全公司合同聚合——与合同读权限矩阵矛盾。gate 必须是 is_system_admin。
"""

import pytest
from rest_framework.test import APIClient

from apps.assetmanagement.models import Contract
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

OVERVIEW_URL = "/api/v1/dashboard/overview/"

_phone_seq = iter(range(40000, 50000))


def _phone() -> str:
    return f"134{next(_phone_seq):08d}"


def _make_user(username: str, role: EmployeeRole | None, department: Department | None) -> AuthUser:
    """按角色构造 AuthUser + Employee（role=None 仅 AuthUser，superuser 语义）。"""
    user = AuthUser.objects.create_user(
        auth_username=username, password=TEST_PASSWORD, auth_phone=_phone()
    )
    if role is not None:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}本人",
            employee_department=department,
            role=role,
            employee_phone=_phone(),
        )
    return user


@pytest.fixture
def dept():
    return Department.objects.create(department_code="DEPT-CT", department_name="统计部门", path="/DEPT-CT")


@pytest.fixture
def two_contracts():
    return [
        Contract.objects.create(
            contract_code=f"CT-SC-{i}",
            contract_name=f"统计合同{i}",
            contract_amount=1000 * i,
            contract_start_date="2024-01-01",
        )
        for i in (1, 2)
    ]


@pytest.mark.parametrize(
    "username,role,expected",
    [
        ("SYS-CT", EmployeeRole.SYSTEM_ADMIN, 2),  # system_admin：真值
        ("MGR-CT", EmployeeRole.DEPT_MANAGER, 0),
        ("ADM-CT", EmployeeRole.ASSET_ADMIN, 0),
        ("REG-CT", EmployeeRole.REGULAR_USER, 0),
        ("AUD-CT", EmployeeRole.AUDITOR, 0),  # 坑位锁定:auditor dept_codes=None 但必须 0
    ],
)
def test_overview_total_contracts_by_role(username, role, expected, dept, two_contracts):
    """5 角色参数化:合同聚合仅 system_admin 可见,其余角色恒 0（D3 拍板口径）。"""
    user = _make_user(username, role, dept)
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(OVERVIEW_URL)
    assert response.status_code == 200, response.status_code
    assert response.data["data"]["total_contracts"] == expected


def test_overview_superuser_sees_full_contracts(two_contracts):
    """superuser（is_superuser 绕过）返回真值。"""
    su = AuthUser.objects.create_superuser(
        auth_username="SU-CT", password=TEST_PASSWORD, auth_phone=_phone()
    )
    client = APIClient()
    client.force_authenticate(user=su)
    response = client.get(OVERVIEW_URL)
    assert response.status_code == 200, response.status_code
    assert response.data["data"]["total_contracts"] == 2
