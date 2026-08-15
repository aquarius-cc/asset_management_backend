"""
双通道认证(Bearer / Cookie)与 CSRF 测试

覆盖(本阶段双通道过渡方案, 对应 CT-3/CT-4 补测):
- Service 层: resolve_role_info / inject_rbac_claims / issue_tokens / refresh_tokens
- 通道判据: 有 Authorization 头 -> bearer; 无 -> cookie
- 登录双写: body 返回 access/refresh + set cookie(access/refresh/csrftoken)
- 登录 CSRF 加固: X-Requested-With 校验
- Cookie 通道不安全方法强制 CSRF; bearer 通道豁免
- Refresh 双通道 + 轮换/黑名单 + 回写 + 旧 token 拒绝
- Logout 双通道 + 宽容清理 + AllowAny(过期 access 不阻断)
- RBAC claims: 签发/刷新注入; profile 返回派生字段
"""

import jwt
import pytest
from django.conf import settings
from django.test.utils import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.services import AuthService
from apps.usermanagement.models import Department, Employee, EmployeeRole


LOGIN_URL = "/api/auth/login/"
REGISTER_URL = "/api/auth/register/"
LOGOUT_URL = "/api/auth/logout/"
PROFILE_URL = "/api/auth/profile/"
REFRESH_URL = "/api/auth/token/refresh/"

XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


def _make_user(username: str, role=None, department=None, is_superuser: bool = False) -> AuthUser:
    """创建带可选 Employee 的 AuthUser(与 test_my_permissions 一致)"""
    user = AuthUser.objects.create_user(
        auth_username=username,
        password="testpass123",
        auth_is_staff=(is_superuser or role == EmployeeRole.SYSTEM_ADMIN),
    )
    user.is_superuser = is_superuser
    user.save(update_fields=["is_superuser"])
    if role:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
        )
    return user


def _make_department(code: str = "IT-001") -> Department:
    return Department.objects.create(department_code=code, department_name=f"部门{code}")


def _login(client: APIClient, username: str = "testuser", password: str = "testpass123"):
    return client.post(LOGIN_URL, {"auth_username": username, "password": password}, **XHR)


def _csrf_header(client: APIClient) -> dict:
    """从登录后响应的 csrftoken Cookie 构造 X-CSRFToken 头"""
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def _decode(token: str) -> dict:
    """解码 JWT payload(不验签, 仅读取 claims)"""
    return jwt.decode(token, options={"verify_signature": False})


def _rotation_settings() -> dict:
    """开启轮换 + 黑名单的 SIMPLE_JWT 覆盖(生产默认值)"""
    return {"SIMPLE_JWT": {**settings.SIMPLE_JWT, "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True}}


@pytest.mark.django_db
class TestServiceRBAC:
    """Service 层 RBAC 派生与签发(CT-2 Service>=90% 专项)"""

    def test_resolve_superuser(self):
        user = _make_user("su1", is_superuser=True)
        assert AuthService.resolve_role_info(user) == {
            "role": "system_admin",
            "department_code": None,
            "is_superuser": True,
        }

    def test_resolve_employee_with_dept(self):
        dept = _make_department()
        user = _make_user("emp1", role=EmployeeRole.ASSET_ADMIN, department=dept)
        info = AuthService.resolve_role_info(user)
        assert info == {
            "role": EmployeeRole.ASSET_ADMIN,
            "department_code": dept.department_code,
            "is_superuser": False,
        }

    def test_resolve_employee_no_dept(self):
        user = _make_user("emp2", role=EmployeeRole.REGULAR_USER)
        info = AuthService.resolve_role_info(user)
        assert info["role"] == EmployeeRole.REGULAR_USER
        assert info["department_code"] is None

    def test_resolve_no_employee(self):
        user = _make_user("noemp")
        assert AuthService.resolve_role_info(user) == {
            "role": "regular_user",
            "department_code": None,
            "is_superuser": False,
        }

    def test_issue_tokens_access_inherits_claims(self):
        dept = _make_department()
        user = _make_user("emp3", role=EmployeeRole.DEPT_MANAGER, department=dept)
        tokens = AuthService.issue_tokens(user)
        payload = _decode(tokens["access"])
        assert payload["role"] == EmployeeRole.DEPT_MANAGER
        assert payload["department_code"] == dept.department_code
        assert payload["is_superuser"] is False

    def test_issue_tokens_superuser(self):
        user = _make_user("su2", is_superuser=True)
        tokens = AuthService.issue_tokens(user)
        payload = _decode(tokens["access"])
        assert payload["role"] == "system_admin"
        assert payload["is_superuser"] is True

    def test_role_change_blacklists_tokens_and_relogin_picks_new_role(self):
        dept = _make_department()
        user = _make_user("emp4", role=EmployeeRole.REGULAR_USER, department=dept)
        tokens = AuthService.issue_tokens(user)
        assert _decode(tokens["access"])["role"] == EmployeeRole.REGULAR_USER
        emp = Employee.objects.get(employee_jobcode="emp4")
        emp.role = EmployeeRole.DEPT_MANAGER
        emp.save(update_fields=["role"])
        with pytest.raises(TokenError):
            AuthService.refresh_tokens(tokens["refresh"])
        fresh_user = AuthUser.objects.get(auth_id=user.auth_id)
        relogin = AuthService.issue_tokens(fresh_user)
        assert _decode(relogin["access"])["role"] == EmployeeRole.DEPT_MANAGER

    def test_refresh_invalid_token_raises(self):
        with pytest.raises(TokenError):
            AuthService.refresh_tokens("not-a-jwt")

    def test_refresh_missing_user_id_raises(self):
        user = _make_user("emp5")
        tokens = AuthService.issue_tokens(user)
        user.delete()
        with pytest.raises(AuthUser.DoesNotExist):
            AuthService.refresh_tokens(tokens["refresh"])

    @override_settings(SIMPLE_JWT={**settings.SIMPLE_JWT, "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True})
    def test_refresh_rotates_and_blacklists_old(self):
        user = _make_user("rot1")
        tokens = AuthService.issue_tokens(user)
        refreshed = AuthService.refresh_tokens(tokens["refresh"])
        assert refreshed["refresh"] != tokens["refresh"]
        assert _decode(refreshed["access"])["role"] == "regular_user"
        with pytest.raises(TokenError):
            AuthService.refresh_tokens(tokens["refresh"])

    @override_settings(
        SIMPLE_JWT={**settings.SIMPLE_JWT, "ROTATE_REFRESH_TOKENS": False, "BLACKLIST_AFTER_ROTATION": False}
    )
    def test_refresh_without_rotation_keeps_refresh(self):
        user = _make_user("norot")
        tokens = AuthService.issue_tokens(user)
        refreshed = AuthService.refresh_tokens(tokens["refresh"])
        assert refreshed["refresh"] == tokens["refresh"]


@pytest.mark.django_db
class TestLoginDualChannel:
    """登录双写: 响应体 + Cookie"""

    def test_login_sets_cookies(self, api_client):
        _make_user("testuser")
        resp = _login(api_client)
        assert resp.status_code == 200
        assert resp.data["code"] == 0
        assert "access" in resp.data["data"]
        assert "refresh" in resp.data["data"]
        for name in ("asset_access_token", "asset_refresh_token", "csrftoken"):
            assert name in api_client.cookies

    def test_login_requires_x_requested_with(self, api_client):
        _make_user("testuser")
        resp = api_client.post(LOGIN_URL, {"auth_username": "testuser", "password": "testpass123"})
        assert resp.status_code == 403

    def test_login_wrong_password(self, api_client):
        _make_user("testuser")
        resp = _login(api_client, password="wrongpass")
        assert resp.status_code == 401

    def test_login_inactive_user(self, api_client):
        user = _make_user("inactive")
        user.auth_is_active = False
        user.save(update_fields=["auth_is_active"])
        resp = _login(api_client, username="inactive")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestBearerChannel:
    """Bearer 通道认证(移动端 / API 客户端)"""

    def test_bearer_gets_profile(self, api_client):
        user = _make_user("bearer1", is_superuser=True)
        access = AuthService.issue_tokens(user)["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = api_client.get(PROFILE_URL)
        assert resp.status_code == 200
        assert resp.data["data"]["auth_username"] == "bearer1"

    def test_no_token_returns_401(self, api_client):
        resp = api_client.get(PROFILE_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestCookieChannelCSRF:
    """Cookie 通道 + CSRF 强制(cookie 通道不安全方法)"""

    def test_cookie_get_no_csrf(self, api_client):
        _make_user("cook1")
        _login(api_client, username="cook1")
        resp = api_client.get(PROFILE_URL)
        assert resp.status_code == 200
        assert resp.data["data"]["auth_username"] == "cook1"

    def test_cookie_put_without_csrf_forbidden(self, api_client):
        _make_user("cook2")
        _login(api_client, username="cook2")
        resp = api_client.put(PROFILE_URL, {"email": "c2@example.com"})
        assert resp.status_code == 403

    def test_cookie_put_with_csrf_succeeds(self, api_client):
        _make_user("cook3")
        _login(api_client, username="cook3")
        resp = api_client.put(PROFILE_URL, {"email": "c3@example.com"}, **_csrf_header(api_client))
        assert resp.status_code == 200

    def test_bearer_put_no_csrf_succeeds(self, api_client):
        user = _make_user("bearer2")
        access = AuthService.issue_tokens(user)["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = api_client.put(PROFILE_URL, {"email": "b2@example.com"})
        assert resp.status_code == 200


@pytest.mark.django_db
class TestRefreshDualChannel:
    """Token 刷新双通道"""

    @override_settings(SIMPLE_JWT={**settings.SIMPLE_JWT, "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True})
    def test_refresh_bearer_rotates_and_blacklists(self, api_client):
        user = _make_user("rf1")
        tokens = AuthService.issue_tokens(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
        assert resp.status_code == 200
        new_refresh = resp.data["data"]["refresh"]
        assert new_refresh != tokens["refresh"]
        old = tokens["refresh"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_refresh}")
        resp2 = api_client.post(REFRESH_URL, {"refresh": old})
        assert resp2.status_code == 401

    def test_refresh_cookie_channel(self, api_client):
        _make_user("rf2")
        _login(api_client, username="rf2")
        resp = api_client.post(REFRESH_URL, {}, **_csrf_header(api_client))
        assert resp.status_code == 200
        assert "access" in resp.data["data"]
        assert resp.cookies.get("asset_access_token") is not None

    def test_refresh_cookie_without_csrf_forbidden(self, api_client):
        _make_user("rf3")
        _login(api_client, username="rf3")
        resp = api_client.post(REFRESH_URL, {})
        assert resp.status_code == 403

    def test_refresh_missing_token_bad_request(self, api_client):
        user = _make_user("rf4")
        _login(api_client, username="rf4")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AuthService.issue_tokens(user)['access']}")
        resp = api_client.post(REFRESH_URL, {})
        assert resp.status_code == 400

    def test_refresh_invalid_token_unauthorized(self, api_client):
        user = _make_user("rf5")
        _login(api_client, username="rf5")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AuthService.issue_tokens(user)['access']}")
        resp = api_client.post(REFRESH_URL, {"refresh": "garbage-token"})
        assert resp.status_code == 401

    def test_refresh_does_not_require_valid_access(self, api_client):
        """过期/无效 access cookie 不应阻断刷新(authentication_classes=[])"""
        _make_user("rf6")
        _login(api_client, username="rf6")
        api_client.cookies["asset_access_token"] = "invalid-expired"
        resp = api_client.post(REFRESH_URL, {}, **_csrf_header(api_client))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestLogoutDualChannel:
    """退出登录双通道 + 宽容清理"""

    def test_logout_bearer_blacklists(self, api_client):
        user = _make_user("lo1")
        tokens = AuthService.issue_tokens(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})
        assert resp.status_code == 200
        with pytest.raises(TokenError):
            AuthService.refresh_tokens(tokens["refresh"])

    def test_logout_cookie_channel(self, api_client):
        _make_user("lo2")
        _login(api_client, username="lo2")
        resp = api_client.post(LOGOUT_URL, {}, **_csrf_header(api_client))
        assert resp.status_code == 200
        assert not api_client.cookies["asset_access_token"].value

    def test_logout_cookie_without_csrf_forbidden(self, api_client):
        _make_user("lo3")
        _login(api_client, username="lo3")
        resp = api_client.post(LOGOUT_URL, {})
        assert resp.status_code == 403

    def test_logout_tolerant_invalid_refresh(self, api_client):
        user = _make_user("lo4")
        _login(api_client, username="lo4")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AuthService.issue_tokens(user)['access']}")
        resp = api_client.post(LOGOUT_URL, {"refresh": "already-revoked-or-invalid"})
        assert resp.status_code == 200

    def test_logout_tolerant_no_refresh(self, api_client):
        user = _make_user("lo5")
        _login(api_client, username="lo5")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AuthService.issue_tokens(user)['access']}")
        resp = api_client.post(LOGOUT_URL, {})
        assert resp.status_code == 200

    def test_logout_allowany_with_expired_access(self, api_client):
        _make_user("lo6")
        _login(api_client, username="lo6")
        api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid-access")
        resp = api_client.post(LOGOUT_URL, {}, **_csrf_header(api_client))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestProfileAndRegister:
    """profile 派生字段 + 注册补齐 claims"""

    def test_profile_returns_rbac_fields(self, api_client):
        dept = _make_department()
        user = _make_user("prof1", role=EmployeeRole.ASSET_ADMIN, department=dept)
        access = AuthService.issue_tokens(user)["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = api_client.get(PROFILE_URL)
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["role"] == EmployeeRole.ASSET_ADMIN
        assert data["department_code"] == dept.department_code
        assert data["is_superuser"] is False
        assert data["auth_username"] == "prof1"

    def test_register_returns_regular_user_claims(self, api_client):
        resp = api_client.post(
            REGISTER_URL,
            {
                "auth_username": "newreg",
                "password": "Passw0rd@123",
                "password2": "Passw0rd@123",
                "email": "n@x.com",
                "auth_phone": "13800000000",
            },
        )
        assert resp.status_code == 201
        payload = _decode(resp.data["data"]["access"])
        assert payload["role"] == "regular_user"
        assert "asset_access_token" in api_client.cookies
