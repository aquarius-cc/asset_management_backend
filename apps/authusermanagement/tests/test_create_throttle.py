"""
注册限流口径（P2-03 历史 + BF-126 收口后口径）

历史: AuthUserViewSet.create 曾挂 RegisterRateThrottle 对齐 /auth/register/ 的 5/min 匿名口径。
【BF-126 收口】create 为 system_admin 单通道（匿名 401），匿名注册唯一入口 /auth/register/，
RegisterRateThrottle 自 create 的 get_throttles 分支整体移除；其 429 覆盖迁移至 register 端点。

断言:
- get_throttles: create / list 均不再含 RegisterRateThrottle（收口单元直证）
- 匿名连续 POST /auth/register/ 第 6 次返回 429（override 压低 register 速率）
- 已认证 system_admin create 连发不受 register 限流（管理端建号不受影响）
"""

import pytest
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.authusermanagement.views import AuthUserViewSet
from core.throttles import RegisterRateThrottle


REGISTER_URL = "/api/v1/auth/register/"
CREATE_URL = "/api/v1/auth/users/"


def _viewset_with_action(action: str) -> AuthUserViewSet:
    viewset = AuthUserViewSet()
    viewset.action = action
    return viewset


# test.py 将 DEFAULT_THROTTLE_CLASSES 置空、rates 调至千万级;
# 429 用例需整块覆盖 rates(register=5/minute)。RegisterAPIView 的
# throttle_classes=[RegisterRateThrottle] 为类属性显式挂载,故
# DEFAULT_CLASSES=[] 下该 throttle 仍执行,无需恢复默认类。
# 【镜像必填 DEFAULT_SCHEMA_CLASS】override 窗口内 URLConf 首次懒导入会
# 执行 @extend_schema 装饰,其回退链读 api_settings.DEFAULT_SCHEMA_CLASS;
# 本字典缺省时回落 DRF 内建 2-arg AutoSchema 并固化进 ExtendedSchema 基类,
# 同进程后续 schema 生成必炸 TypeError(spectacular get_operation 为 5-arg,
# 见 generators.py:175 鸡生蛋注释)。全字典镜像 project 配置防跨测试污染。
_THROTTLE_TEST_SETTINGS = {
    "REST_FRAMEWORK": {
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "10000000/minute",
            "user": "10000000/minute",
            "register": "5/minute",
            "login": "10000000/minute",
        },
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
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

    def test_sixth_anonymous_register_returns_429(self):
        from django.core.cache import cache

        cache.clear()
        client = APIClient()
        with override_settings(**_THROTTLE_TEST_SETTINGS):
            codes = []
            for i in range(6):
                resp = client.post(REGISTER_URL, _valid_payload(i))
                codes.append(resp.status_code)
                # register 成功会种 auth cookie → 下一请求走 cookie 通道触发
                # CSRF 强制(BF-056)得 403,清 cookie 保持纯匿名口径
                client.cookies.clear()
        assert codes[:5] != [429] * 5, f"前 5 次不应被限流: {codes}"
        assert codes[5] == 429, f"第 6 次应 429, 实得 {codes}"

    def test_authenticated_create_not_blocked_by_register_throttle(self):
        """已认证 system_admin create 连发不受 register 限流（收口后 create 无该 throttle）"""
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
