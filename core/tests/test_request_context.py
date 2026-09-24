"""
request_context 中间件 IP 溯源测试(#35 TRUST_PROXY_HEADERS 守卫)

覆盖:
1. 默认 False:伪造 X-Forwarded-For 不生效,仅信任 REMOTE_ADDR
2. True:信任可信代理,解析 X-Forwarded-For 首值(无 XFF 时回退 REMOTE_ADDR)
3. 默认值断言:base.py TRUST_PROXY_HEADERS 缺省必须为 False(安全默认)
"""

from pathlib import Path
from types import SimpleNamespace

from django.test import override_settings

from core.request_context import RequestContextMiddleware


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _req(**meta: str | None) -> SimpleNamespace:
    mutable: dict[str, str] = {}
    for key, value in meta.items():
        if value is not None:
            mutable[key] = value
    return SimpleNamespace(META=mutable)


class TestDefaultTrustsProxyHeadersDisabled:
    """默认 TRUST_PROXY_HEADERS=False —— 伪造 XFF 一律忽略"""

    def test_ignores_forged_xff(self):
        with override_settings(TRUST_PROXY_HEADERS=False):
            ip = RequestContextMiddleware._get_client_ip(
                _req(HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1", REMOTE_ADDR="192.168.1.5")
            )
        assert ip == "192.168.1.5"

    def test_ignores_xff_when_no_remote_addr(self):
        with override_settings(TRUST_PROXY_HEADERS=False):
            ip = RequestContextMiddleware._get_client_ip(_req(HTTP_X_FORWARDED_FOR="203.0.113.9"))
        assert ip is None

    def test_falls_back_to_remote_addr(self):
        with override_settings(TRUST_PROXY_HEADERS=False):
            ip = RequestContextMiddleware._get_client_ip(_req(REMOTE_ADDR="192.168.1.5"))
        assert ip == "192.168.1.5"


class TestTrustProxyHeadersEnabled:
    """TRUST_PROXY_HEADERS=True —— 解析 X-Forwarded-For 首值"""

    def test_parses_first_xff_value(self):
        with override_settings(TRUST_PROXY_HEADERS=True):
            ip = RequestContextMiddleware._get_client_ip(
                _req(HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1", REMOTE_ADDR="192.168.1.5")
            )
        assert ip == "203.0.113.9"

    def test_falls_back_to_remote_addr_when_no_xff(self):
        with override_settings(TRUST_PROXY_HEADERS=True):
            ip = RequestContextMiddleware._get_client_ip(_req(REMOTE_ADDR="192.168.1.5"))
        assert ip == "192.168.1.5"


class TestSecureDefaultSetting:
    """base.py 缺省必须是 False(安全默认,fail-closed)"""

    def test_default_is_false(self):
        src = (_BACKEND_ROOT / "config" / "settings" / "base.py").read_text(encoding="utf-8")
        assert 'TRUST_PROXY_HEADERS = config("TRUST_PROXY_HEADERS", default=False, cast=bool)' in src, (
            "base.py 缺少 TRUST_PROXY_HEADERS 且默认必须为 False"
        )
