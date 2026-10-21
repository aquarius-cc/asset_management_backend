"""
合同读面收口权限测试(BF-127)

矩阵依据:backend-business-rules.md 4.2 :144 系统配置行(类型/仓库/合同/员工/部门/用户)
—— system_admin ✅,dept_manager/asset_admin/regular_user/auditor 全 ❌。

ContractViewSet 读 action(list/retrieve/getcontractByname/statistics/global_search)
经 _CONTRACT_READ_OVERRIDES 收口 IsSystemAdmin;本文件承担角色矩阵面与匿名 401,
读功能面见 test_contract_view_api(已改用 admin client)。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db


@pytest.fixture
def department(db):
    """测试部门(部门级角色须带部门,排除 get_user_role 无部门 None 降级干扰)"""
    from apps.usermanagement.models import Department

    return Department.objects.create(department_code="D-CR", department_name="合同读测试部门")


def _user_with_role(username: str, role: EmployeeRole, department) -> AuthUser:
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}用户",
        employee_department=department,
        role=role,
        employee_phone=f"1390000{abs(hash(username)) % 10000:04d}",
    )
    return AuthUser.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_phone=f"1380000{abs(hash(username)) % 10000:04d}",
    )


def _client_for(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


def test_anonymous_list_401(api_client):
    """匿名读合同:401(JWT 挑战头;IsSystemAdmin 匿名恒拒)"""
    response = api_client.get(reverse("contracts-list"))
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_system_admin_list_200(api_client, department, contract):
    """正例锚:matrix :144 system_admin 可读"""
    user = _user_with_role("cr_sysadmin", EmployeeRole.SYSTEM_ADMIN, department)
    response = _client_for(api_client, user).get(reverse("contracts-list"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["code"] == 0


def test_regular_user_list_and_retrieve_403(api_client, department, contract):
    """regular_user:list/retrieve 均 403(矩阵 ❌;存量读功能测试改 admin 后的权限面补位)"""
    user = _user_with_role("cr_regular", EmployeeRole.REGULAR_USER, department)
    client = _client_for(api_client, user)
    list_resp = client.get(reverse("contracts-list"))
    detail_resp = client.get(reverse("contracts-detail", kwargs={"recordcode": contract.recordcode}))
    assert list_resp.status_code == status.HTTP_403_FORBIDDEN
    assert detail_resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize("role", [EmployeeRole.DEPT_MANAGER, EmployeeRole.ASSET_ADMIN])
def test_dept_and_asset_admin_list_403(api_client, department, contract, role):
    """dept_manager/asset_admin:list 403(矩阵 :144 ❌;防「三角色放宽」回归)"""
    user = _user_with_role(f"cr_{role.value}", role, department)
    response = _client_for(api_client, user).get(reverse("contracts-list"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_auditor_list_403(api_client, department, contract):
    """auditor:list 403(矩阵 :144 系统配置行 ❌;全局只读不覆盖系统配置面)"""
    user = _user_with_role("cr_auditor", EmployeeRole.AUDITOR, department)
    response = _client_for(api_client, user).get(reverse("contracts-list"))
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    ("action", "kwargs"),
    [
        ("contracts-statistics", {}),
        ("contracts-global-search", {}),
        ("contracts-getcontractByname", {"name": "任意名"}),
    ],
)
def test_custom_read_actions_403_for_regular(api_client, department, contract, action, kwargs):
    """自定义读 action(statistics/global_search/getcontractByname)对 regular 同样 403
    (_CONTRACT_READ_OVERRIDES 全读面覆盖,防漏收口 action)"""
    user = _user_with_role("cr_regular_custom", EmployeeRole.REGULAR_USER, department)
    response = _client_for(api_client, user).get(reverse(action, kwargs=kwargs), {"keyword": "x"})
    assert response.status_code == status.HTTP_403_FORBIDDEN
