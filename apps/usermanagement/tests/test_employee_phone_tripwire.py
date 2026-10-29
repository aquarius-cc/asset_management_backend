"""
M-03 绊线测试：员工手机号三条读路径口径一致性锚点。

【临时业务口径锚点 — 隐私整改时按票废除】
业务确认（merge-audit-2026-10-29 M-03，BF-165）：employee_phone 对所有
IsAuthenticated 用户明文返回——通讯录按手机号检索为既定诉求，且列表/详情/
搜索三条读路径共用同一数据源与同一权限（IsAuthenticated），单点脱敏必被
同源端点绕过，故整体维持明文口径（WAI 留痕关闭）。

本文件锁定「三处口径一致」这一不变量：
- list   : EmployeeSerializer（fields 白名单含 employee_phone）
- detail : EmployeeDetailSerializer（fields="__all__"）
- search : global_search（get_serializer_class 默认 EmployeeSerializer）

未来任一侧被单独改动（如仅列表脱敏），本测试立即报警；
真正引入隐私口径时，三处同步改造后按票废除/改写本文件。
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

LIST_URL = reverse("employees-list")
SEARCH_URL = reverse("employees-global-search")

TRIPWIRE_PHONE = "13911112222"
TRIPWIRE_JOBCODE = "M03-TRIP"


@pytest.fixture
def m03_auth_user(db):
    # superuser: 本文件锁定口径一致性(非 RBAC),需全量可见
    return AuthUser.objects.create_superuser(auth_username="M03TRIP", password=TEST_PASSWORD)


@pytest.fixture
def m03_client(m03_auth_user):
    client = APIClient()
    client.force_authenticate(user=m03_auth_user)
    return client


@pytest.fixture
def m03_employee(db):
    department = Department.objects.create(department_code="M03-DEPT", department_name="绊线测试部")
    return Employee.objects.create(
        employee_jobcode=TRIPWIRE_JOBCODE,
        employee_name="绊线员工",
        employee_department=department,
        employee_phone=TRIPWIRE_PHONE,
    )


def _detail_url() -> str:
    return reverse("employees-detail", kwargs={"employee_jobcode": TRIPWIRE_JOBCODE})


def _assert_list_phone(m03_client, m03_employee) -> str:
    response = m03_client.get(LIST_URL)
    assert response.status_code == status.HTTP_200_OK, response.data
    payload = response.data["data"]
    rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    row = next(r for r in rows if r["employee_jobcode"] == TRIPWIRE_JOBCODE)
    assert "employee_phone" in row, "列表响应缺 employee_phone 字段——口径被单独改动"
    return row["employee_phone"]


def _assert_detail_phone(m03_client, m03_employee) -> str:
    response = m03_client.get(_detail_url())
    assert response.status_code == status.HTTP_200_OK, response.data
    data = response.data["data"]
    assert "employee_phone" in data, "详情响应缺 employee_phone 字段——口径被单独改动"
    return data["employee_phone"]


def _assert_search_phone(m03_client, m03_employee) -> str:
    response = m03_client.get(SEARCH_URL, {"keyword": TRIPWIRE_JOBCODE})
    assert response.status_code == status.HTTP_200_OK, response.data
    payload = response.data["data"]
    rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    row = next(r for r in rows if r["employee_jobcode"] == TRIPWIRE_JOBCODE)
    assert "employee_phone" in row, "搜索响应缺 employee_phone 字段——口径被单独改动"
    return row["employee_phone"]


class TestEmployeePhoneTripwire:
    """三读路径 employee_phone 口径必须一致（当前均为明文，BF-165 WAI 锚点）"""

    def test_three_read_paths_phone_consistent(self, m03_client, m03_employee):
        phone_list = _assert_list_phone(m03_client, m03_employee)
        phone_detail = _assert_detail_phone(m03_client, m03_employee)
        phone_search = _assert_search_phone(m03_client, m03_employee)

        assert phone_list == phone_detail == phone_search, (
            "M-03: 员工手机号三条读路径口径分叉——list/detail/search 必须同源同口径"
            "（BF-165 临时锚点；引入隐私口径时须三处同步改造并按票废除本断言）"
        )
