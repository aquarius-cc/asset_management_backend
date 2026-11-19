"""BF-204/BF-206: 部门创建 API 契约测试

【BF-206】create 走 DepartmentCreateSerializer + perform_create 委托 DepartmentService:
- 请求体 parent_department_code 可写(此前被 read_only 丢弃,部门被建到根层且 path 为空)
- level/path 由服务层计算
- 审计适配器被触发(此前不触发)
"""

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


def _admin(db) -> AuthUser:
    """role-based system_admin(固定唯一电话防部分唯一约束冲突)"""
    admin = AuthUser.objects.create_user(auth_username="bf204_admin", password=TEST_PASSWORD, auth_phone="13700000901")
    Employee.objects.create(
        employee_jobcode="bf204_admin",
        employee_name="BF-204 管理员",
        employee_department=None,
        role=EmployeeRole.SYSTEM_ADMIN,
        employee_phone="13700000902",
    )
    return admin


def _client(admin: AuthUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def _create_department(department_code: str, department_name: str, **kwargs) -> Department:
    return Department.objects.create(
        department_code=department_code,
        department_name=department_name,
        department_information="BF-204 测试部门",
        **kwargs,
    )


@pytest.mark.django_db
class TestDepartmentCreateApi:
    def test_create_with_parent_writes_parent_level_path_sort_order(self, db):
        """带 parent_department_code 创建: parent/level/path/sort_order 四项正确,序号=组内 max+1"""
        admin = _admin(db)
        parent = _create_department("BF204_PARENT", "BF204 父部门", level=0, path="/BF204_PARENT")
        # 父组已有 sort_order=3 的子部门 → 新建应排到 4
        _create_department(
            "BF204_SIB", "BF204 兄弟", parent=parent, level=1, path="/BF204_PARENT/BF204_SIB", sort_order=3
        )
        client = _client(admin)
        resp = client.post(
            reverse("departments-list"),
            {
                "department_code": "BF204_CHILD",
                "department_name": "BF204 子部门",
                "department_information": "BF-204 测试子部门",
                "parent_department_code": "BF204_PARENT",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        dept = Department.objects.get(department_code="BF204_CHILD")
        assert dept.parent == parent
        assert dept.level == 1
        assert dept.path == "/BF204_PARENT/BF204_CHILD"
        assert dept.sort_order == 4

    def test_create_with_missing_parent_400(self, db):
        """父编码不存在: 400 + PARENT_DEPARTMENT_NOT_FOUND"""
        admin = _admin(db)
        client = _client(admin)
        resp = client.post(
            reverse("departments-list"),
            {
                "department_code": "BF204_ORPHAN",
                "department_name": "BF204 孤儿",
                "department_information": "BF-204 孤儿部门",
                "parent_department_code": "NO_SUCH_BF204_PARENT",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        # 拒绝发生在序列化器校验层(SlugRelatedField 对不存在值报字段级错误)
        assert resp.data["message"] == "参数验证失败"
        assert "parent_department_code" in resp.data["data"]
        assert not Department.objects.filter(department_code="BF204_ORPHAN").exists()

    def test_create_without_parent_root_contract(self, db):
        """不带父创建: level=0、path=/编码(补齐此前 path 为空的缺陷)"""
        admin = _admin(db)
        client = _client(admin)
        resp = client.post(
            reverse("departments-list"),
            {
                "department_code": "BF204_ROOT",
                "department_name": "BF204 根部门",
                "department_information": "BF-204 根部门",
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        dept = Department.objects.get(department_code="BF204_ROOT")
        assert dept.parent is None
        assert dept.level == 0
        assert dept.path == "/BF204_ROOT"

    def test_create_triggers_audit_once_with_empty_operator(self, db):
        """审计核验: perform_create 触发 log_create 恰好一次,operator 空值不报错"""
        admin = _admin(db)
        client = _client(admin)
        with patch("apps.usermanagement.services.department_service.DepartmentAuditAdapter.log_create") as mock_log:
            resp = client.post(
                reverse("departments-list"),
                {
                    "department_code": "BF204_AUDIT",
                    "department_name": "BF204 审计",
                    "department_information": "BF-204 审计部门",
                },
                format="json",
            )

        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert mock_log.call_count == 1
        args, _kwargs = mock_log.call_args
        assert args[0].department_code == "BF204_AUDIT"
        assert args[1] is None  # operator_jobcode 空值

    def test_batch_create_appends_sort_order_when_omitted(self, db):
        """BF-207: 批量创建缺省 sort_order → 组内 0/1/2 递增(append 权威,非全 0 并列)"""
        admin = _admin(db)
        client = _client(admin)
        for i in range(3):
            resp = client.post(
                reverse("departments-batch-create"),
                {
                    "items": [
                        {
                            "department_code": f"BF207_B{i}",
                            "department_name": f"BF207 批量{i}",
                            "department_information": "BF-207",
                        }
                    ]
                },
                format="json",
            )
            assert resp.status_code == status.HTTP_200_OK, resp.data

        orders = [Department.objects.get(department_code=f"BF207_B{i}").sort_order for i in range(3)]
        assert orders == [0, 1, 2]

    def test_batch_create_explicit_sort_order_respected(self, db):
        """BF-207: 批量创建显式 sort_order=5 → 落 5(显式值被尊重)"""
        admin = _admin(db)
        client = _client(admin)
        resp = client.post(
            reverse("departments-batch-create"),
            {
                "items": [
                    {
                        "department_code": "BF207_EXPL",
                        "department_name": "BF207 显式",
                        "department_information": "BF-207",
                        "sort_order": 5,
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert Department.objects.get(department_code="BF207_EXPL").sort_order == 5

    def test_batch_create_negative_sort_order_400(self, db):
        """BF-207: min_value=0 收紧 → 负序号 400"""
        admin = _admin(db)
        client = _client(admin)
        resp = client.post(
            reverse("departments-batch-create"),
            {
                "items": [
                    {
                        "department_code": "BF207_NEG",
                        "department_name": "BF204 负序号",
                        "department_information": "BF-207",
                        "sort_order": -1,
                    }
                ]
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
