"""
注册限流口径（P2-03 历史 + BF-126 收口后口径）

历史: AuthUserViewSet.create 曾挂 RegisterRateThrottle 对齐 /auth/register/ 的 5/min 匿名口径。
【BF-126 收口】create 为 system_admin 单通道（匿名 401），匿名注册唯一入口 /auth/register/，
RegisterRateThrottle 自 create 的 get_throttles 分支整体移除；其 429 覆盖迁移至 register 端点。

断言:
- get_throttles: create / list 均不再含 RegisterRateThrottle（收口单元直证）
- 匿名连续 POST /auth/register/ 第 6 次返回 429（monkeypatch 直设 rate=5/minute）
- 已认证 system_admin create 连发不受 register 限流（管理端建号不受影响）

【速率直设机制（BF-128 §六 存量红收口）】DRF 3.17+ 在 rest_framework.throttling 模块
首次导入时把 DEFAULT_THROTTLE_RATES 快照为 SimpleRateThrottle.THROTTLE_RATES 类属性
（throttling.py:66）；override_settings 仅刷新 api_settings 实例缓存、不回绑该类属性
——以 override 压速率是安慰剂，用例绿/红取决于进程首次导入时生效的 settings
（pytest.ini 默认 development 捕获 base register=5/minute 偶绿；本会话权威口径
--ds=config.settings.test 捕获 test.py 千万级必红）。故两用例统一
monkeypatch.setattr(RegisterRateThrottle, "rate", "5/minute")：SimpleRateThrottle.__init__
见 truthy rate 即跳过 get_rate()，与 settings 口径解耦（双口径同绿），退出自动还原。
"""

import pytest
from rest_framework.test import APIClient

from apps.authusermanagement.views import AuthUserViewSet
from core.throttles import RegisterRateThrottle


REGISTER_URL = "/api/v1/auth/register/"
CREATE_URL = "/api/v1/auth/users/"


def _viewset_with_action(action: str) -> AuthUserViewSet:
    viewset = AuthUserViewSet()
    viewset.action = action
    return viewset


def _valid_payload(i: int) -> dict[str, str]:
    return {
        "auth_username": f"throttle_u{i}",
        "password": "Passw0rd@123",
        "password2": "Passw0rd@123",
        "email": f"throttle{i}@x.com",
        "auth_phone": f"1390000{i:04d}",
    }


class TestCreateThrottles:
    """get_throttles 单元断言（BF-126 收口后 create 不再挂 RegisterRateThrottle）"""

    def test_create_action_excludes_register_rate_throttle(self):
        throttles = _viewset_with_action("create").get_throttles()
        assert not any(isinstance(t, RegisterRateThrottle) for t in throttles)

    def test_non_create_action_excludes_register_rate_throttle(self):
        throttles = _viewset_with_action("list").get_throttles()
        assert not any(isinstance(t, RegisterRateThrottle) for t in throttles)


@pytest.mark.django_db
class TestRegisterRateLimited:
    """匿名 register 第 6 次 429(5/min 口径)——BF-126 后唯一匿名注册入口"""

    def test_sixth_anonymous_register_returns_429(self, monkeypatch: pytest.MonkeyPatch):
        from django.core.cache import cache

        cache.clear()
        # 类属性直设：绕开 THROTTLE_RATES 导入期快照，对两种 settings 口径同生效
        monkeypatch.setattr(RegisterRateThrottle, "rate", "5/minute", raising=False)
        client = APIClient()
        codes = []
        for i in range(6):
            resp = client.post(REGISTER_URL, _valid_payload(i))
            codes.append(resp.status_code)
            # register 成功会种 auth cookie → 下一请求走 cookie 通道触发
            # CSRF 强制(BF-056)得 403,清 cookie 保持纯匿名口径
            client.cookies.clear()
        assert codes[:5] != [429] * 5, f"前 5 次不应被限流: {codes}"
        assert codes[5] == 429, f"第 6 次应 429, 实得 {codes}"

    def test_authenticated_create_not_blocked_by_register_throttle(self, monkeypatch: pytest.MonkeyPatch):
        """已认证 system_admin create 连发不受 register 限流（收口后 create 无该 throttle）"""
        from django.core.cache import cache

        from apps.authusermanagement.models import AuthUser
        from core.tests import TEST_PASSWORD

        cache.clear()
        # 同直设 5/minute：若 create 回归误挂 RegisterRateThrottle，第 6 次必 429 → 断言具杀伤力
        monkeypatch.setattr(RegisterRateThrottle, "rate", "5/minute", raising=False)
        admin = AuthUser.objects.create_user(
            auth_username="throttle_admin",
            password=TEST_PASSWORD,
            auth_is_staff=True,
        )
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])
        client = APIClient()
        client.force_authenticate(user=admin)
        codes = []
        for i in range(6, 12):
            resp = client.post(CREATE_URL, _valid_payload(i))
            codes.append(resp.status_code)
        assert 429 not in codes, f"已认证 create 不应吃 register 限流: {codes}"
