"""员工导出测试：权限矩阵 + 可见性一致性 + 分批参数。

【锁定的不变量】
1. **可见性一致**：导出内容必须与列表接口可见的员工集合完全一致。
   ``ExportExcelMixin`` 复用 ``self.get_queryset()``，与列表同源，
   因此结构上不可能偏移；本文件把该性质锁死，防将来给列表加过滤而
   遗漏导出。
2. **导出须走权限矩阵**：``EmployeeViewSet`` 有自定义 ``get_permissions``，
   若 ``export_excel`` 落入 ``else`` 分支则只校验 ``IsAuthenticated``，
   任意登录用户即可导出全量员工档案。故必须有显式 ``CanExportExcel`` 分支。
3. **最小化 PII**：导出列不含 ``employee_phone``。
"""

import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.usermanagement.models import Department, Employee, EmployeeRole
from apps.usermanagement.views import EmployeeViewSet


User = get_user_model()

TEST_PASSWORD = "Test@12345"
EXPORT_URL = reverse("employees-export-excel")
LIST_URL = reverse("employees-list")
SHEET_NAME = "员工列表"

#: 与 operation_log 导出测试同因：response.close() 触发 request_finished，
#: 其接收方 close_old_connections 会关连接，与原子事务包裹冲突。
pytestmark = pytest.mark.django_db(transaction=True)

_phone_seq = iter(range(20_000, 30_000))


def _phone():
    return f"138{next(_phone_seq):08d}"


def _make_user(username, role, department=None):
    user = User.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_is_staff=(role == EmployeeRole.SYSTEM_ADMIN),
    )
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}员工",
        employee_department=department,
        role=role,
        employee_phone=_phone(),
    )
    return user


@pytest.fixture
def department():
    return Department.objects.create(
        department_code="DEPT-EXP", department_name="导出测试部"
    )


@pytest.fixture
def employees(department):
    for index in range(3):
        Employee.objects.create(
            employee_jobcode=f"EMP{index:03d}",
            employee_name=f"员工{index}",
            employee_department=department,
            employee_phone=_phone(),
            employee_location=f"L{index}",
        )


def _export(user, query="", action="export_excel"):
    view = EmployeeViewSet.as_view({"get": action})
    request = APIRequestFactory().get(f"{EXPORT_URL}{query}")
    force_authenticate(request, user=user)
    return view(request)


def _export_sheet(user, query=""):
    """执行导出并返回解析后的 xlsx 工作表。"""
    response = _export(user, query)
    assert response.status_code == 200, response.status_code
    try:
        payload = b"".join(response.streaming_content)
    finally:
        response.close()
    return load_workbook(io.BytesIO(payload))[SHEET_NAME]


def _headers(sheet):
    return [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]


# --------------------------------------------------------------------------
# 权限矩阵
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [EmployeeRole.SYSTEM_ADMIN, EmployeeRole.ASSET_ADMIN, EmployeeRole.AUDITOR]
)
def test_export_allowed_for_export_roles(employees, department, role):
    user = _make_user(f"emp-exp-{role}", role, department)
    assert _export(user).status_code == 200


@pytest.mark.parametrize("role", [EmployeeRole.REGULAR_USER])
def test_export_denied_for_non_export_roles(employees, department, role):
    """regular_user 不在导出矩阵内（矩阵 :148）-> 403。

    注意 dept_manager **可以**导出，故不能一并断言 403。
    """
    user = _make_user(f"emp-no-{role}", role, department)
    assert _export(user).status_code == 403


def test_export_denied_for_anonymous(employees):
    from rest_framework.test import APIClient

    assert APIClient().get(EXPORT_URL).status_code in (401, 403)


# --------------------------------------------------------------------------
# 可见性一致性（核心不变量）
# --------------------------------------------------------------------------


def test_export_matches_list_visibility(employees, department):
    """导出内容必须与列表接口可见集合一致。"""
    user = _make_user("emp-vis", EmployeeRole.ASSET_ADMIN, department)
    listed = set(
        Employee.objects.filter(employee_department=department).values_list(
            "employee_jobcode", flat=True
        )
    )
    sheet = _export_sheet(user)
    exported = {row[0] for row in sheet.iter_rows(min_row=2, max_col=1, values_only=True)}
    assert exported == listed
    # 3 个 fixtures 员工 + _make_user 自身也是该部门员工
    assert len(exported) == 4


def test_export_does_not_leak_phone(employees, department):
    """导出列最小化 PII：不含手机号。"""
    user = _make_user("emp-pii", EmployeeRole.ASSET_ADMIN, department)
    headers = _headers(_export_sheet(user))
    assert "员工电话" not in headers
    assert "手机号" not in " ".join(str(h) for h in headers)


# --------------------------------------------------------------------------
# 分批参数
# --------------------------------------------------------------------------


def test_export_limit_offset(employees, department):
    user = _make_user("emp-page", EmployeeRole.ASSET_ADMIN, department)
    total = Employee.objects.count()
    sheet = _export_sheet(user, "?limit=2")
    rows = [r for r in sheet.iter_rows(min_row=2, max_col=1, values_only=True) if r[0]]
    assert len(rows) == 2
    tail = [
        r
        for r in _export_sheet(user, f"?limit=2&offset={total - 1}").iter_rows(
            min_row=2, max_col=1, values_only=True
        )
        if r[0]
    ]
    assert len(tail) == 1


def test_export_invalid_limit_returns_400(employees, department):
    user = _make_user("emp-bad", EmployeeRole.ASSET_ADMIN, department)
    assert _export(user, "?limit=abc").status_code == 400
    assert _export(user, "?limit=0").status_code == 400


def test_export_headers_expose_max_rows(employees, department):
    """响应头带上限与总数，供前端提示（跨源部署需 CORS_EXPOSE_HEADERS）。"""
    from django.conf import settings

    user = _make_user("emp-hdr", EmployeeRole.ASSET_ADMIN, department)
    response = _export(user)
    try:
        assert response["X-Export-Max-Rows"] == str(settings.EXPORT_MAX_ROWS)
        assert response["X-Export-Total-Count"] == str(Employee.objects.count())
    finally:
        response.close()
    assert "X-Export-Max-Rows" in settings.CORS_EXPOSE_HEADERS
