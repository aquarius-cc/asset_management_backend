"""M-PERF-01 部门树 3N→1 性能门 + 结构等价回归（批次 2）。

先红锚：
- test_tree_single_query / test_query_count_constant：旧实现逐层递归查询 → 红。
- test_soft_deleted_employee_not_counted：filter=_NOT_DELETED_EMPLOYEE_Q 移除/翻转 → 红。
- test_soft_deleted_department_subtree_excluded：新组树等价前提（SoftDeleteManager 排除）。
"""

from __future__ import annotations

import pytest

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department
from apps.usermanagement.selectors import DepartmentSelector
from apps.usermanagement.tests.factories import DepartmentFactory, EmployeeFactory
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db


@pytest.fixture
def tree_root():
    return DepartmentFactory(
        department_code="PERF_ROOT",
        department_name="根部门",
        department_information="info",
        parent=None,
        level=0,
        path="/PERF_ROOT",
    )


class TestDepartmentTreePerf:
    """M-PERF-01：树构建查询数恒定 + 软删口径 + 结构等价"""

    def test_tree_single_query(self, django_assert_num_queries):
        DepartmentFactory(department_code="P1", department_name="a", parent=None, level=0, path="/P1")
        child = DepartmentFactory(
            department_code="P1C",
            department_name="c",
            parent=Department.objects.get(department_code="P1"),
            level=1,
            path="/P1/P1C",
        )
        EmployeeFactory(employee_jobcode="E1", employee_name="e", employee_department=child)

        with django_assert_num_queries(1):
            DepartmentSelector.build_department_tree()

    def test_query_count_constant(self, django_assert_num_queries):
        root = DepartmentFactory(department_code="P2", department_name="a", parent=None, level=0, path="/P2")
        DepartmentSelector.build_department_tree()
        with django_assert_num_queries(1):
            DepartmentSelector.build_department_tree()

        # 数据增长：加子部门 + 员工，查询数必须不变
        child = DepartmentFactory(
            department_code="P2C",
            department_name="c",
            parent=root,
            level=1,
            path="/P2/P2C",
        )
        EmployeeFactory(employee_jobcode="E2", employee_name="e", employee_department=child)
        DepartmentSelector.build_department_tree()
        with django_assert_num_queries(1):
            DepartmentSelector.build_department_tree()

    def test_soft_deleted_employee_not_counted(self, tree_root):
        emp = EmployeeFactory(
            employee_jobcode="PSE1",
            employee_name="e",
            employee_department=tree_root,
        )
        emp.delete()  # 软删（BaseModel.delete）

        tree = DepartmentSelector.build_department_tree()
        node = next(n for n in tree if n["department_code"] == "PERF_ROOT")
        assert node["employee_count"] == 0

    def test_soft_deleted_department_subtree_excluded(self, tree_root):
        mid = DepartmentFactory(
            department_code="P_MID",
            department_name="m",
            parent=tree_root,
            level=1,
            path="/PERF_ROOT/P_MID",
        )
        DepartmentFactory(
            department_code="P_LEAF",
            department_name="l",
            parent=mid,
            level=2,
            path="/PERF_ROOT/P_MID/P_LEAF",
        )
        mid.delete()  # 软删 mid

        tree = DepartmentSelector.build_department_tree()
        codes = [n["department_code"] for n in tree]
        assert "P_MID" not in codes
        # 其子树（leaf）不再出现在任何 children 中
        root_node = next(n for n in tree if n["department_code"] == "PERF_ROOT")
        assert root_node["children"] == []

    def test_structure_unchanged(self, tree_root):
        child = DepartmentFactory(
            department_code="P_S1",
            department_name="s",
            parent=tree_root,
            level=1,
            path="/PERF_ROOT/P_S1",
        )
        EmployeeFactory(employee_jobcode="PSE3", employee_name="e", employee_department=child)

        tree = DepartmentSelector.build_department_tree()
        root_node = next(n for n in tree if n["department_code"] == "PERF_ROOT")
        child_node = root_node["children"][0]

        # 逐字段等价（与旧递归实现输出一致）
        assert set(root_node.keys()) == {
            "recordcode",
            "department_code",
            "department_name",
            "department_information",
            "parent",
            "parent_department_code",
            "path",
            "level",
            "sort_order",
            "children",
            "employee_count",
        }
        assert root_node["parent"] is None
        assert root_node["parent_department_code"] is None
        assert child_node["department_code"] == "P_S1"
        assert child_node["parent_department_code"] == "PERF_ROOT"
        assert child_node["employee_count"] == 1
        assert child_node["children"] == []

    def test_tree_api_contract(self, tree_root, api_client):
        auth_user = AuthUser.objects.create_user(auth_username="PTREE01", password=TEST_PASSWORD)
        api_client.force_authenticate(user=auth_user)

        response = api_client.get("/api/v1/users/departments/tree/")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        data = body["data"]
        root_node = next(n for n in data if n["department_code"] == "PERF_ROOT")
        assert root_node["parent"] is None
        assert "employee_count" in root_node and "children" in root_node


class TestEndpointQueryCountConstant:
    """8.4 端点级相对锚：数据翻倍后查询数不变（children/descendants/list）"""

    @staticmethod
    def _grow(root: Department) -> None:
        child = DepartmentFactory(
            department_code=f"EQC{root.department_code[-1]}",
            department_name="c",
            parent=root,
            level=1,
            path=f"{root.path}/EQC{root.department_code[-1]}",
        )
        EmployeeFactory(employee_jobcode=f"E{root.department_code[-1]}", employee_name="e", employee_department=child)

    @staticmethod
    def _measured_get(api_client, url: str) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            resp = api_client.get(url)
        assert resp.status_code == 200
        return len(ctx.captured_queries)

    def test_children_descendants_list_query_count_constant(self, tree_root, api_client):
        auth_user = AuthUser.objects.create_user(auth_username="PTREE02", password=TEST_PASSWORD)
        api_client.force_authenticate(user=auth_user)

        urls = [
            f"/api/v1/users/departments/{tree_root.department_code}/children/",
            f"/api/v1/users/departments/{tree_root.department_code}/descendants/",
            "/api/v1/users/departments/",
        ]
        before = {u: self._measured_get(api_client, u) for u in urls}

        self._grow(tree_root)  # 数据翻倍（子部门 + 员工）
        for url, old_count in before.items():
            after = self._measured_get(api_client, url)
            assert after == old_count, f"{url} 查询数漂移: {old_count} → {after}"
