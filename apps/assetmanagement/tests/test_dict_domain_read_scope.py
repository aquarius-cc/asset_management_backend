"""
字典三域(asset-types/storages/contracts)读面隔离断言(M-06 组A 试点)

锚定既有 get_queryset() 口径的全局行为(行为不变重构的等价性护栏):
- 软删不可见: list 不含 is_deleted=True 记录; retrieve 软删对象 → 404(get_object 路径)
- 登录可读边界: asset-types/storages 任意认证用户可读(§4.2.1 豁免登记行);
  contracts 仅 system_admin(矩阵 :144) —— 403 半边由 test_contract_read_scope.py 在案,不重复断言
- 写面 403: regular_user 对三域 create → 403(AdminWritePermissionMixin/IsSystemAdmin)
- 无 PII: 字典域 list 载荷不含敏感字段键

注: 本文件为行为锚定测试(先绿,非回归红), accompanying M-06 类属性收敛重构。
"""

from typing import Any

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


SENSITIVE_KEYS = {"employee_phone", "auth_phone", "password", "auth_password"}

ALL_DOMAINS = [("asset-types", "asset_type"), ("storages", "storage"), ("contracts", "contract")]
READ_OPEN_DOMAINS = [("asset-types", "asset_type"), ("storages", "storage")]


def _soft_delete(obj: Any) -> None:
    obj.is_deleted = True
    obj.save()


@pytest.mark.django_db
class TestDictDomainReadScope:
    """字典三域全局读面口径锚定(软删/匿名/RBAC/PII)"""

    @pytest.mark.parametrize("basename,fixture_name", ALL_DOMAINS, ids=["asset-types", "storages", "contracts"])
    def test_list_excludes_soft_deleted(
        self, api_client: APIClient, admin_auth_user: Any, request: Any, basename: str, fixture_name: str
    ) -> None:
        obj = request.getfixturevalue(fixture_name)
        _soft_delete(obj)
        api_client.force_authenticate(user=admin_auth_user)
        resp = api_client.get(reverse(f"{basename}-list"))
        assert resp.status_code == status.HTTP_200_OK
        rows = resp.data["data"]["results"]
        assert all(row["recordcode"] != str(obj.recordcode) for row in rows)

    @pytest.mark.parametrize("basename,fixture_name", ALL_DOMAINS, ids=["asset-types", "storages", "contracts"])
    def test_retrieve_soft_deleted_404(
        self, api_client: APIClient, admin_auth_user: Any, request: Any, basename: str, fixture_name: str
    ) -> None:
        obj = request.getfixturevalue(fixture_name)
        _soft_delete(obj)
        api_client.force_authenticate(user=admin_auth_user)
        resp = api_client.get(reverse(f"{basename}-detail", kwargs={"recordcode": obj.recordcode}))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize("basename,fixture_name", ALL_DOMAINS, ids=["asset-types", "storages", "contracts"])
    def test_create_403_for_regular_user(
        self, api_client: APIClient, department: Any, request: Any, basename: str, fixture_name: str
    ) -> None:
        # regular_user 借 test_storage_view_rbac._make_role_user 同范式自建;fixture 仅保 db 状态
        from apps.authusermanagement.models import AuthUser
        from apps.usermanagement.models import Employee
        from core.tests import TEST_PASSWORD

        AuthUser.objects.create_user(auth_username="dict_ru", password=TEST_PASSWORD, auth_phone="13800000901")
        Employee.objects.create(
            employee_jobcode="dict_ru",
            employee_name="字典域常规用户",
            employee_department=department,
            role="regular_user",
            employee_phone="13800000902",
        )
        api_client.force_authenticate(user=AuthUser.objects.get(auth_username="dict_ru"))
        resp = api_client.post(reverse(f"{basename}-list"), {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("basename,fixture_name", READ_OPEN_DOMAINS, ids=["asset-types", "storages"])
    def test_list_401_for_anonymous(self, api_client: APIClient, basename: str, fixture_name: str) -> None:
        """域的匿名底线(§4.2.1 豁免仅放开已登录读面,匿名仍 401)"""
        resp = api_client.get(reverse(f"{basename}-list"))
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("basename,fixture_name", READ_OPEN_DOMAINS, ids=["asset-types", "storages"])
    def test_list_payload_no_pii(
        self, api_client: APIClient, department: Any, request: Any, basename: str, fixture_name: str
    ) -> None:
        from apps.authusermanagement.models import AuthUser
        from apps.usermanagement.models import Employee
        from core.tests import TEST_PASSWORD

        AuthUser.objects.create_user(auth_username="dict_pii", password=TEST_PASSWORD, auth_phone="13800000903")
        Employee.objects.create(
            employee_jobcode="dict_pii",
            employee_name="PII探针用户",
            employee_department=department,
            role="regular_user",
            employee_phone="13800000904",
        )
        api_client.force_authenticate(user=AuthUser.objects.get(auth_username="dict_pii"))
        resp = api_client.get(reverse(f"{basename}-list"))
        assert resp.status_code == status.HTTP_200_OK
        for row in resp.data["data"]["results"]:
            assert not SENSITIVE_KEYS & set(row.keys())
