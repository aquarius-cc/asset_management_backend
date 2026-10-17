"""
P2-03: AuthUserViewSet.create 注册限流口径对齐

断言:
- get_throttles() 在 create 动作前插 RegisterRateThrottle(单元级,与 DEFAULT 无关)
- 匿名连续 POST /auth/users/ 第 6 次返回 429(override 压低 register 速率)

背景: create 此前仅吃全局 anon 20/min,而 /auth/register/ 为 RegisterRateThrottle
5/min → 注册限流口径绕过。RegisterRateThrottle 为 AnonRateThrottle 子类,
已认证管理端建号不受影响。
"""

import pytest
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.authusermanagement.views import AuthUserViewSet
from core.throttles import RegisterRateThrottle


CREATE_URL = "/api/v1/auth/users/"


def _viewset_with_action(action: str) -> AuthUserViewSet:
    viewset = AuthUserViewSet()
    viewset.action = action
    return viewset


# test.py 将 DEFAULT_THROTTLE_CLASSES 置空、rates 调至千万级;
# 429 用例需整块覆盖 rates(register=5/minute)。get_throttles 显式返回
# RegisterRateThrottle,故 DEFAULT_CLASSES=[] 下该 throttle 仍执行,
# 无需恢复默认类。
_THROTTLE_TEST_SETTINGS = {
    "REST_FRAMEWORK": {
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "10000000/minute",
            "user": "10000000/minute",
            "register": "5/minute",
            "login": "10000000/minute",
        },
    }
}


def _valid_payload(i: int) -> dict[str, str]:
    return {
        "auth_username": f"throttle_u{i}",
        "password": "Passw0rd@123",
        "password2": "Passw0rd@123",
        "email": f"throttle{i}@x.com",
        "auth_phone": f"1390000{i:04d}",
    }


class TestCreateThrottles:
    """get_throttles 单元断言"""

    def test_create_action_includes_register_rate_throttle(self):
        throttles = _viewset_with_action("create").get_throttles()
        assert any(isinstance(t, RegisterRateThrottle) for t in throttles)

    def test_non_create_action_excludes_register_rate_throttle(self):
        throttles = _viewset_with_action("list").get_throttles()
        assert not any(isinstance(t, RegisterRateThrottle) for t in throttles)


@pytest.mark.django_db
class TestCreateRateLimited:
    """匿名 create 第 6 次 429(与 /auth/register/ 同 5/min 口径)"""

    def test_sixth_anonymous_create_returns_429(self):
        from django.core.cache import cache

        cache.clear()
        client = APIClient()
        with override_settings(**_THROTTLE_TEST_SETTINGS):
            codes = []
            for i in range(6):
                resp = client.post(CREATE_URL, _valid_payload(i))
                codes.append(resp.status_code)
                # create 成功会种 auth cookie → 下一请求走 cookie 通道触发
                # CSRF 强制(BF-056)得 403,清 cookie 保持纯匿名口径
                client.cookies.clear()
        assert codes[:5] != [429] * 5, f"前 5 次不应被限流: {codes}"
        assert codes[5] == 429, f"第 6 次应 429, 实得 {codes}"

    def test_authenticated_create_not_blocked_by_register_throttle(self):
        """已认证请求不受 RegisterRateThrottle(Anon) 约束——管理端建号不受影响"""
        from django.core.cache import cache

        from apps.authusermanagement.models import AuthUser
        from core.tests import TEST_PASSWORD

        cache.clear()
        admin = AuthUser.objects.create_user(
            auth_username="throttle_admin",
            password=TEST_PASSWORD,
            auth_is_staff=True,
        )
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])
        client = APIClient()
        client.force_authenticate(user=admin)
        with override_settings(**_THROTTLE_TEST_SETTINGS):
            codes = []
            for i in range(6, 12):
                resp = client.post(CREATE_URL, _valid_payload(i))
                codes.append(resp.status_code)
        assert 429 not in codes, f"已认证 create 不应吃 register 限流: {codes}"
