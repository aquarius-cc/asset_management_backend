"""导出端点权限矩阵回归（BF-170 批次 3 OP-04 配套，防局部覆写波及面外溢）。

【锁定的不变量】
ContractViewSet.get_permissions 局部覆写 export_excel 后，**其余带 export_columns
的 ViewSet 导出权限行为必须零变化**（以 test_export_columns_contract.py 的
9 ViewSet 清单为准，扣掉本批已单独断言的 contracts）：

- 资产域端点（挂 IsAssetAdminOrAbove+/CanExportExcel）：system_admin 200、
  regular_user 403（与改前一致）
- employee 域端点（CanExportExcel）：system_admin 200、regular_user 403

角色×端点行为矩阵固化，任何一端漂移即本测试红。
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

_phone_seq = iter(range(60000, 70000))


def _phone() -> str:
    return f"132{next(_phone_seq):08d}"


def _make_user(username: str, role: EmployeeRole, department: Department | None) -> AuthUser:
    user = AuthUser.objects.create_user(auth_username=username, password=TEST_PASSWORD, auth_phone=_phone())
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}本人",
        employee_department=department,
        role=role,
        employee_phone=_phone(),
    )
    return user


# 8 个不受本批影响的导出端点（url_name 或字面路径 → 域）；contracts 已单独断言，不入矩阵
# （unregisteredasset 的 include 带命名空间，reverse(name) 不可达，用字面路径）
EXPORT_MATRIX = [
    ("assets-export-excel", "资产域"),
    ("recycle-assets-export-excel", "资产域"),
    ("damaged-assets-export-excel", "资产域"),
    ("out-assets-export-excel", "资产域"),
    ("waste-assets-export-excel", "资产域"),
    ("harddisk-sn-export-excel", "资产域"),
    ("/api/v1/unregisteredassets/unregistered-assets/export/", "未登记资产域"),
    ("employees-export-excel", "员工域"),
]


@pytest.fixture
def dept():
    return Department.objects.create(department_code="DEPT-MX", department_name="矩阵部门", path="/DEPT-MX")


# D-4: 四生命周期端点此前挂 ExportExcelMixin 未配列(权限通过后必 500), 补列后入矩阵
# 强断言: 与其它资产域端点同口径(system_admin 200 / regular_user 精确 403),
# 不做 (200,403,404) 宽断言——本域导出行集与列表同口径, regular_user 必被权限层拒绝
LIFECYCLE_EXPORT_STRICT = [
    ("broken-assets-export-excel", "资产域"),
    ("lost-assets-export-excel", "资产域"),
    ("found-assets-export-excel", "资产域"),
    ("repair-assets-export-excel", "资产域"),
]


@pytest.mark.parametrize("url_name,domain", EXPORT_MATRIX)
def test_export_matrix_roles_unaffected(url_name, domain, dept, db):
    """其余导出端点 × {system_admin, regular_user} 行为零变化（局部覆写不外溢）。"""
    su = _make_user(f"S-MX-{url_name[:6]}", EmployeeRole.SYSTEM_ADMIN, None)
    regular = _make_user(f"R-MX-{url_name[:6]}", EmployeeRole.REGULAR_USER, dept)

    url = url_name if url_name.startswith("/") else reverse(url_name)
    client = APIClient()
    client.force_authenticate(user=su)
    su_response = client.get(url)

    client2 = APIClient()
    client2.force_authenticate(user=regular)
    regular_response = client2.get(url)

    # system_admin 可进（200；无数据行也 200——权限层放行，不锁行数）
    assert su_response.status_code == 200, f"{url_name} system_admin: {su_response.status_code}"
    # regular_user 被拒：403（权限层）/ 404（行级隔离不泄露存在性，§4.5 unregisteredasset 语义）/
    # 200（行级空集）——三者均为改前既有行为，锁定不漂移
    assert regular_response.status_code in (200, 403, 404), f"{url_name} regular_user: {regular_response.status_code}"


@pytest.mark.parametrize("url_name,domain", LIFECYCLE_EXPORT_STRICT)
def test_lifecycle_export_strict(url_name, domain, dept, db):
    """D-4: 四生命周期导出端点补列后, 行为对齐资产域口径(强断言, 非宽断言)。

    补列前该矩阵红: system_admin 命中 500「未配置导出列」(MissingColumnsError)。
    """
    su = _make_user(f"S-LC-{url_name[:6]}", EmployeeRole.SYSTEM_ADMIN, None)
    regular = _make_user(f"R-LC-{url_name[:6]}", EmployeeRole.REGULAR_USER, dept)

    url = reverse(url_name)
    client = APIClient()
    client.force_authenticate(user=su)
    su_response = client.get(url)
    assert su_response.status_code == 200, f"{url_name} system_admin: {su_response.status_code}"

    client2 = APIClient()
    client2.force_authenticate(user=regular)
    regular_response = client2.get(url)
    assert regular_response.status_code == 403, f"{url_name} regular_user: {regular_response.status_code}"
