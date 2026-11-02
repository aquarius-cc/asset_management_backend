"""合同导出权限测试（BF-170 批次 3 OP-04，[HALT] 拍板口径落地）。

【锁定的不变量】
公共 resolve_viewset_permissions 中 export_excel 短路（CanExportExcel）优先于
action_overrides——dept_manager/asset_admin/auditor 持 CanExportExcel 即可导出
全量合同（金额/起止日期），绕过 BF-127 合同读权限（system_admin-only）。

ContractViewSet.get_permissions 局部覆写后：
- 仅 system_admin 200（且 xlsx 行数 == 合同数）
- dept_manager / asset_admin / regular_user / auditor 403
- 未登录 401
"""

import io

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.assetmanagement.models import Contract
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

EXPORT_URL = "/api/v1/assets/contracts/export/"

_phone_seq = iter(range(50000, 60000))


def _phone() -> str:
    return f"133{next(_phone_seq):08d}"


def _make_user(username: str, role: EmployeeRole | None, department: Department | None) -> AuthUser:
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
    return Department.objects.create(department_code="DEPT-CX", department_name="导出部门", path="/DEPT-CX")


@pytest.fixture
def two_contracts():
    return [
        Contract.objects.create(
            contract_code=f"CT-CX-{i}",
            contract_name=f"导出合同{i}",
            contract_amount=500 * i,
            contract_start_date="2024-01-01",
        )
        for i in (1, 2)
    ]


def _export(client: APIClient):
    return client.get(EXPORT_URL)


@pytest.mark.parametrize(
    "username,role,expected",
    [
        ("SYS-CX", EmployeeRole.SYSTEM_ADMIN, 200),
        ("MGR-CX", EmployeeRole.DEPT_MANAGER, 403),
        ("ADM-CX", EmployeeRole.ASSET_ADMIN, 403),
        ("REG-CX", EmployeeRole.REGULAR_USER, 403),
        ("AUD-CX", EmployeeRole.AUDITOR, 403),
    ],
)
def test_contract_export_by_role(username, role, expected, dept, two_contracts):
    """5 角色:仅 system_admin 可导出合同（OP-04 局部覆写，其余 403）。"""
    user = _make_user(username, role, dept)
    client = APIClient()
    client.force_authenticate(user=user)
    response = _export(client)
    assert response.status_code == expected, response.status_code


def test_contract_export_unauthenticated_401(two_contracts):
    """未登录 → 401（认证门禁先于权限）。"""
    client = APIClient()
    response = _export(client)
    assert response.status_code == 401, response.status_code


def test_contract_export_row_count_matches_db(two_contracts):
    """system_admin 导出 xlsx 行数 == 合同数（内容断言，非仅状态码）。"""
    user = _make_user("SYS-CX-ROW", EmployeeRole.SYSTEM_ADMIN, None)
    client = APIClient()
    client.force_authenticate(user=user)
    response = _export(client)
    assert response.status_code == 200, response.status_code
    try:
        payload = b"".join(response.streaming_content)
    finally:
        response.close()
    sheet = load_workbook(io.BytesIO(payload)).worksheets[0]
    data_rows = sum(1 for row in sheet.iter_rows(min_row=2, values_only=True) if any(row))
    assert data_rows == 2
