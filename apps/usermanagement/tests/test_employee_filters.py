"""员工列表 / 搜索 / 统计的筛选口径测试（BF-047 + BF-B2 部门筛选失效回归屏障）。

【锁定的不变量】
1. **取行口径单一入口**：``department_code`` / ``employee_status`` 在 list、
   search、statistics、export 四条路径上必须**同时**生效。任一路径单独解析
   即产生口径分叉——BF-047 的成因正是导出漏了搜索口径、B2 的成因正是
   搜索端点漏了部门筛选（前端 ``ContactsView`` 两个分支都传该参数却被静默忽略）。
2. **参数双名兼容**：``department_code`` 为业务名，
   ``employee_department__department_code`` 为历史别名，二者结果必须一致。
3. **统计 = 列表当前可见范围的聚合**：``statistics`` 端点必须尊重筛选条件，
   此前固定统计全量，导致 OpenAPI 已声明的筛选参数在本端点形同虚设。
4. **组合筛选**：keyword + 部门 + 状态三者同时生效（收窄而非取并集）。

【与 ``test_employee_view_api.py`` 的分工】该文件覆盖依赖 Selector 单方法的
端点（部门查询/权限查询）；本文件覆盖**筛选口径**这一横向不变量。
"""

import itertools
from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeStatus
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

LIST_URL = reverse("employees-list")
SEARCH_URL = reverse("employees-global-search")
STATISTICS_URL = reverse("employees-statistics")

DEPT_A_CODE = "FILTER-A"
DEPT_B_CODE = "FILTER-B"

#: employee_phone 具条件唯一约束（is_deleted=False），故每条夹具员工需独立手机号
_phone_seq = itertools.count(13_900_000_000)

#: 三名员工共有的搜索词（走 employee_description 通道，同时验证 keyword 口径）
COMMON_KEYWORD = "花名册在册"


def _employee(department: Department, jobcode: str, name: str, status_value: Any) -> Employee:
    return Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=name,
        employee_department=department,
        employee_status=status_value,
        employee_phone=f"{next(_phone_seq):011d}",
        employee_description=COMMON_KEYWORD,
    )


@pytest.fixture
def auth_user(db):
    return AuthUser.objects.create_user(auth_username="FILTER001", password=TEST_PASSWORD)


@pytest.fixture
def api_client(auth_user):
    client = APIClient()
    client.force_authenticate(user=auth_user)
    return client


@pytest.fixture
def departments(db):
    """两个部门：DEPT-A（2 人：active/left）、DEPT-B（1 人：active）"""
    dept_a = Department.objects.create(department_code=DEPT_A_CODE, department_name="筛选甲部")
    dept_b = Department.objects.create(department_code=DEPT_B_CODE, department_name="筛选乙部")
    _employee(dept_a, "FA-ACTIVE", "甲部在职张三", EmployeeStatus.ACTIVE)
    _employee(dept_a, "FA-LEFT", "甲部离职李四", EmployeeStatus.LEFT)
    _employee(dept_b, "FB-ACTIVE", "乙部在职王五", EmployeeStatus.ACTIVE)
    return {"dept_a": dept_a, "dept_b": dept_b}


def _jobcodes(response):
    """从统一响应结构中取出结果集的工码集合。"""
    assert response.status_code == status.HTTP_200_OK, response.data
    payload = response.data["data"]
    rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    return {row["employee_jobcode"] for row in rows}


# --------------------------------------------------------------------------
# 列表：department_code（业务名）与历史别名都必须生效
# --------------------------------------------------------------------------


@pytest.mark.parametrize("param", ["department_code", "employee_department__department_code"])
def test_list_filters_by_department(api_client, departments, param):
    """B2 回归：前端传 department_code，此前列表只认别名，等于静默失效。"""
    assert _jobcodes(api_client.get(LIST_URL, {param: DEPT_A_CODE})) == {"FA-ACTIVE", "FA-LEFT"}


def test_list_department_and_alias_agree(api_client, departments):
    """双名等价：不得出现两套口径。"""
    by_name = api_client.get(LIST_URL, {"department_code": DEPT_A_CODE})
    by_alias = api_client.get(LIST_URL, {"employee_department__department_code": DEPT_A_CODE})
    assert by_name.status_code == by_alias.status_code == status.HTTP_200_OK
    assert by_name.data == by_alias.data


def test_list_filters_by_status(api_client, departments):
    assert _jobcodes(api_client.get(LIST_URL, {"employee_status": EmployeeStatus.LEFT})) == {"FA-LEFT"}


# --------------------------------------------------------------------------
# 搜索：department_code / employee_status 必须与列表同口径
# --------------------------------------------------------------------------


def test_search_filters_by_department(api_client, departments):
    """B2 回归：ContactsView 搜索分支传 department_code，此前被完全忽略。"""
    response = api_client.get(SEARCH_URL, {"keyword": COMMON_KEYWORD, "department_code": DEPT_A_CODE})
    assert _jobcodes(response) == {"FA-ACTIVE", "FA-LEFT"}


def test_search_filters_by_status(api_client, departments):
    """状态作为精确筛选与 keyword 取交集，而非并集。"""
    response = api_client.get(SEARCH_URL, {"keyword": COMMON_KEYWORD, "employee_status": EmployeeStatus.LEFT})
    assert _jobcodes(response) == {"FA-LEFT"}


def test_search_without_keyword_returns_400(api_client, departments):
    """keyword 仍为必填：搜索端点不接受无关键词的全量列举。"""
    assert api_client.get(SEARCH_URL).status_code == status.HTTP_400_BAD_REQUEST


def test_search_keyword_matches_department_name(api_client, departments):
    """keyword 保留 Selector 的部门名匹配能力（DRF search= 无此能力）。"""
    response = api_client.get(SEARCH_URL, {"keyword": "筛选乙"})
    assert _jobcodes(response) == {"FB-ACTIVE"}


# --------------------------------------------------------------------------
# 统计：必须尊重筛选条件
# --------------------------------------------------------------------------


def test_statistics_unfiltered_aggregates_all(api_client, departments):
    data = api_client.get(STATISTICS_URL).data["data"]
    assert data["total_employees"] == 3
    assert data["active_employees"] == 2
    assert {code: item["count"] for code, item in data["by_status"].items()} == {"active": 2, "left": 1}
    assert data["by_department"] == {"筛选甲部": 2, "筛选乙部": 1}


@pytest.mark.parametrize("param", ["department_code", "employee_department__department_code"])
def test_statistics_filters_by_department(api_client, departments, param):
    """四个维度（total/active/by_status/by_department）必须同时收窄。"""
    data = api_client.get(STATISTICS_URL, {param: DEPT_A_CODE}).data["data"]
    assert data["total_employees"] == 2
    assert data["active_employees"] == 1
    assert {code: item["count"] for code, item in data["by_status"].items()} == {"active": 1, "left": 1}
    assert data["by_department"] == {"筛选甲部": 2}


def test_statistics_filters_by_status(api_client, departments):
    data = api_client.get(STATISTICS_URL, {"employee_status": EmployeeStatus.LEFT}).data["data"]
    assert data["total_employees"] == 1
    assert data["active_employees"] == 0
    assert {code: item["count"] for code, item in data["by_status"].items()} == {"left": 1}
    assert data["by_department"] == {"筛选甲部": 1}


def test_statistics_combined_filters(api_client, departments):
    """部门 + 状态叠加：统计口径与列表可见集合必须一致。"""
    stats = api_client.get(
        STATISTICS_URL, {"department_code": DEPT_A_CODE, "employee_status": EmployeeStatus.ACTIVE}
    ).data["data"]
    listed = _jobcodes(
        api_client.get(LIST_URL, {"department_code": DEPT_A_CODE, "employee_status": EmployeeStatus.ACTIVE})
    )
    assert stats["total_employees"] == len(listed) == 1


def test_statistics_respects_default_ordering(api_client, departments):
    """Employee.Meta 有默认 ordering，聚合不得因继承排序而碎组或报错。"""
    assert api_client.get(STATISTICS_URL, {"ordering": "-employee_jobcode"}).status_code == status.HTTP_200_OK
    data = api_client.get(STATISTICS_URL, {"ordering": "-employee_jobcode"}).data["data"]
    assert data["total_employees"] == 3
    assert data["by_department"] == {"筛选甲部": 2, "筛选乙部": 1}
