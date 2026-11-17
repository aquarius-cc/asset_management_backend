"""【MA-11】AuthUser 写权限矩阵回归——IsSystemAdminOrSelf 收编具名权限类。

覆盖:
- system_admin 可操作任意账号(update 200)
- 本人可自助操作自己的账号(partial_update 200)
- 普通用户操作他人 → 403 且 message 与归一前手写分支逐字一致(跨端契约零变化)
- 未认证 → 401(登录层前置,零回归锚)
- 普通用户 retrieve 他人 → 403(IsSystemAdmin 通道不变,零回归锚)
"""

import pytest
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def _make_user(username: str) -> AuthUser:
    user = AuthUser.objects.create_user(
        auth_username=username,
        password=TEST_PASSWORD,
        auth_phone=f"138{username[-8:]}",
        email=f"{username}@example.com",
    )
    return user


def _make_admin(username: str = "ma11admin") -> AuthUser:
    user = _make_user(username)
    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    return user


def _login(client: APIClient, username: str) -> None:
    resp = client.post(
        "/api/v1/auth/login/",
        {"auth_username": username, "password": TEST_PASSWORD},
        **XHR,
    )
    assert resp.status_code == 200, resp.data


def _csrf_header(client: APIClient) -> dict:
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def _user_detail_url(user: AuthUser) -> str:
    return f"/api/v1/auth/users/{user.auth_id}/"


@pytest.mark.django_db
class TestAuthUserWritePermissionMatrix:
    """MA-11 归一后的写权限矩阵(先红:原实现无任何 API 级用例,本类为净新增)。"""

    def _patch_email(self, client: APIClient, target: AuthUser, email: str):
        return client.patch(
            _user_detail_url(target),
            {"email": email},
            format="json",
            **XHR,
            **_csrf_header(client),
        )

    def test_system_admin_updates_other_user(self, api_client):
        _make_user("ma11alice")
        admin = _make_admin()
        _login(api_client, admin.auth_username)
        resp = self._patch_email(api_client, _make_user("ma11bob"), "bob-new@example.com")
        assert resp.status_code == 200, resp.data
        AuthUser.objects.get(auth_username="ma11bob").refresh_from_db()
        assert AuthUser.objects.get(auth_username="ma11bob").email == "bob-new@example.com"

    def test_self_partial_update_allowed(self, api_client):
        user = _make_user("ma11self")
        _login(api_client, user.auth_username)
        resp = self._patch_email(api_client, user, "self-new@example.com")
        assert resp.status_code == 200, resp.data
        user.refresh_from_db()
        assert user.email == "self-new@example.com"

    def test_regular_user_updates_other_forbidden_message_verbatim(self, api_client):
        _make_user("ma11alice")
        other = _make_user("ma11bob")
        actor = _make_user("ma11carol")
        _login(api_client, actor.auth_username)
        resp = self._patch_email(api_client, other, "hijacked@example.com")
        assert resp.status_code == 403, resp.data
        # 与归一前 views.check_object_permissions 手写文案逐字一致(§3 跨端契约)
        assert resp.data["message"] == "您没有权限执行此操作。"
        other.refresh_from_db()
        assert other.email != "hijacked@example.com"

    def test_regular_user_destroys_other_forbidden_message_verbatim(self, api_client):
        _make_user("ma11alice")
        other = _make_user("ma11bob")
        actor = _make_user("ma11carol")
        _login(api_client, actor.auth_username)
        resp = api_client.delete(
            _user_detail_url(other),
            **XHR,
            **_csrf_header(api_client),
        )
        assert resp.status_code == 403, resp.data
        assert resp.data["message"] == "您没有权限执行此操作。"
        assert AuthUser.objects.filter(auth_id=other.auth_id).exists()

    def test_unauthenticated_patch_returns_401(self, api_client):
        target = _make_user("ma11bob")
        resp = api_client.patch(_user_detail_url(target), {"email": "x@example.com"}, format="json", **XHR)
        assert resp.status_code == 401, resp.data

    def test_regular_user_retrieve_other_forbidden_zero_regression(self, api_client):
        _make_user("ma11alice")
        actor = _make_user("ma11carol")
        _login(api_client, actor.auth_username)
        resp = api_client.get(_user_detail_url(_make_user("ma11bob")), **XHR)
        # IsSystemAdmin 通道未变:读取仍仅管理员(B11 语义零回归锚)
        assert resp.status_code == 403, resp.data


@pytest.mark.django_db
class TestPermissionClassUnit:
    """权限类单元口径:IsSystemAdminOrSelf 与 IsSystemAdmin 判定一致性。"""

    def test_message_attribute_matches_legacy_verbatim(self):
        from core.permissions import IsSystemAdminOrSelf

        assert IsSystemAdminOrSelf.message == "您没有权限执行此操作。"

    def test_self_identity_matches_by_auth_id(self, api_client):
        from core.permissions import IsSystemAdminOrSelf

        user = _make_user("ma11unit")
        permission = IsSystemAdminOrSelf()
        request = api_client.get("/api/v1/users/")
        request.user = user
        assert permission.has_object_permission(request, None, user) is True

    def test_admin_role_matches_is_system_admin(self, api_client):
        from core.permissions import IsSystemAdmin, IsSystemAdminOrSelf

        admin = _make_admin()
        other = _make_user("ma11unit2")
        request = api_client.get("/api/v1/users/")
        request.user = admin
        permission = IsSystemAdminOrSelf()
        assert permission.has_object_permission(request, None, other) is True
        assert IsSystemAdmin().has_permission(request, None) is True
