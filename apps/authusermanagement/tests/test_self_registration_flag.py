"""
自助注册开关 AUTH_SELF_REGISTRATION_ENABLED 双入口门禁测试（AUD-21 批次2）

覆盖：
- 开关关闭: 匿名 POST /auth/register/ 与 /auth/users/ 一律 403（零建号）
- 开关关闭: 普通用户（有 Employee、非 system_admin）POST /auth/users/ 403
- 开关关闭: system_admin 双入口放行 201（保留管理端建号能力）
- 开关开启(dev/test 默认): 双入口匿名注册照常 201 —— 固化存量行为
  （残留提示①: 开关开启下 /auth/users/ 匿名建号洞保持现状，另立账本后续项）
"""

import pytest
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Employee, EmployeeRole
from core.tests import TEST_PASSWORD


REGISTER_URL = "/api/v1/auth/register/"
CREATE_URL = "/api/v1/auth/users/"


@pytest.fixture
def api_client():
    """API 测试客户端（清缓存防止限流计数跨用例累积）"""
    from django.core.cache import cache

    cache.clear()
    return APIClient()


def _payload(username: str, phone: str) -> dict[str, str]:
    return {
        "auth_username": username,
        "password": "Passw0rd@123",
        "password2": "Passw0rd@123",
        "auth_phone": phone,
    }


def _system_admin() -> AuthUser:
    user = AuthUser.objects.create_user(auth_username="sysadmin_flag", password=TEST_PASSWORD, auth_is_staff=True)
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    return user


@pytest.mark.django_db
class TestSelfRegistrationDisabled:
    """AUTH_SELF_REGISTRATION_ENABLED=False（生产 fail-closed 默认）"""

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_register_anonymous_403(self, api_client):
        resp = api_client.post(REGISTER_URL, _payload("anon_off1", "13800000001"))
        assert resp.status_code == 403
        assert resp.data["code"] == 403
        assert not AuthUser.objects.filter(auth_username="anon_off1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_users_create_anonymous_403(self, api_client):
        resp = api_client.post(CREATE_URL, _payload("anon_off2", "13800000002"))
        assert resp.status_code == 403
        assert resp.data["code"] == 403
        assert not AuthUser.objects.filter(auth_username="anon_off2").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_users_create_regular_user_403(self, api_client):
        user = AuthUser.objects.create_user(auth_username="regular_off", password=TEST_PASSWORD)
        Employee.objects.create(
            employee_jobcode="regular_off", employee_name="普通员工", role=EmployeeRole.REGULAR_USER
        )
        api_client.force_authenticate(user=user)
        resp = api_client.post(CREATE_URL, _payload("victim1", "13800000003"))
        assert resp.status_code == 403
        assert not AuthUser.objects.filter(auth_username="victim1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_users_create_system_admin_201(self, api_client):
        api_client.force_authenticate(user=_system_admin())
        resp = api_client.post(CREATE_URL, _payload("admin_made1", "13800000004"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="admin_made1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_register_system_admin_201(self, api_client):
        api_client.force_authenticate(user=_system_admin())
        resp = api_client.post(REGISTER_URL, _payload("admin_made2", "13800000005"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="admin_made2").exists()


@pytest.mark.django_db
class TestSelfRegistrationEnabled:
    """AUTH_SELF_REGISTRATION_ENABLED=True（base 默认，dev/test 存量行为）"""

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=True)
    def test_register_anonymous_201(self, api_client):
        resp = api_client.post(REGISTER_URL, _payload("anon_on1", "13800000006"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="anon_on1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=True)
    def test_users_create_anonymous_201_status_quo(self, api_client):
        # 固化存量行为: 开关开启(默认)下 create 权限类维持 AllowAny, 匿名建号仍 201。
        # 残留提示①: 若日后收紧(改权限类或默认值), 须同步更新本用例与活账本后续项。
        resp = api_client.post(CREATE_URL, _payload("anon_on2", "13800000007"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="anon_on2").exists()
