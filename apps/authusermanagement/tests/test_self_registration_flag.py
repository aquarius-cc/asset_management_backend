"""
自助注册开关 AUTH_SELF_REGISTRATION_ENABLED 门禁测试（AUD-21 批次2 + BF-126 批次3）

覆盖：
- 开关关闭: 匿名 POST /auth/register/ 403（零建号，生产 fail-closed 默认）
- 开关开启: 匿名 POST /auth/register/ 201（唯一匿名注册入口）
- /auth/users/ create 收口单通道（BF-126，与注册开关解耦）:
  - 匿名 → 401（任意开关取值；DRF 权限类 IsSystemAdmin 拒绝，Bearer 挑战头）
  - 已认证非 system_admin → 403（任意开关取值）
  - system_admin → 201（任意开关取值，管理端建号能力保留）
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
    """AUTH_SELF_REGISTRATION_ENABLED=False（生产 fail-closed 默认）——本开关仅管 /auth/register/"""

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_register_anonymous_403(self, api_client):
        resp = api_client.post(REGISTER_URL, _payload("anon_off1", "13800000001"))
        assert resp.status_code == 403
        assert resp.data["code"] == 403
        assert not AuthUser.objects.filter(auth_username="anon_off1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_register_system_admin_201(self, api_client):
        api_client.force_authenticate(user=_system_admin())
        resp = api_client.post(REGISTER_URL, _payload("admin_made2", "13800000005"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="admin_made2").exists()


@pytest.mark.django_db
class TestSelfRegistrationEnabled:
    """AUTH_SELF_REGISTRATION_ENABLED=True（base 默认，dev/test）"""

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=True)
    def test_register_anonymous_201(self, api_client):
        resp = api_client.post(REGISTER_URL, _payload("anon_on1", "13800000006"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="anon_on1").exists()


@pytest.mark.django_db
class TestCreateSingleChannel:
    """BF-126: /auth/users/ create 收口 sysadmin 单通道——行为与注册开关解耦"""

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=True)
    def test_create_anonymous_401_flag_on(self, api_client):
        resp = api_client.post(CREATE_URL, _payload("anon_on2", "13800000007"))
        assert resp.status_code == 401
        assert resp.data["code"] == 401
        assert not AuthUser.objects.filter(auth_username="anon_on2").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_create_anonymous_401_flag_off(self, api_client):
        # 收口后匿名 create 恒 401（权限门），不再是批次2 的方法体 403——证明与开关解耦
        resp = api_client.post(CREATE_URL, _payload("anon_off2", "13800000002"))
        assert resp.status_code == 401
        assert resp.data["code"] == 401
        assert not AuthUser.objects.filter(auth_username="anon_off2").exists()

    def test_create_regular_user_403(self, api_client):
        user = AuthUser.objects.create_user(auth_username="regular_off", password=TEST_PASSWORD)
        Employee.objects.create(
            employee_jobcode="regular_off", employee_name="普通员工", role=EmployeeRole.REGULAR_USER
        )
        api_client.force_authenticate(user=user)
        resp = api_client.post(CREATE_URL, _payload("victim1", "13800000003"))
        assert resp.status_code == 403
        assert not AuthUser.objects.filter(auth_username="victim1").exists()

    def test_create_system_admin_201_flag_on(self, api_client):
        api_client.force_authenticate(user=_system_admin())
        resp = api_client.post(CREATE_URL, _payload("admin_made1", "13800000004"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="admin_made1").exists()

    @override_settings(AUTH_SELF_REGISTRATION_ENABLED=False)
    def test_create_system_admin_201_flag_off(self, api_client):
        # 生产 fail-closed 开关关闭时管理端建号不受影响（解耦双向直证）
        api_client.force_authenticate(user=_system_admin())
        resp = api_client.post(CREATE_URL, _payload("admin_made3", "13800000008"))
        assert resp.status_code == 201
        assert AuthUser.objects.filter(auth_username="admin_made3").exists()
