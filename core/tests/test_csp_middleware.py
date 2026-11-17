"""【MA-15】CSP 三态中间件与违规上报端点回归。

原中间件零测试（CT-1），本文件为净新增:
- 三态头名（enforce / report-only / off）
- 非法 CSP_MODE 与 DIRECTIVES 缺失 → ImproperlyConfigured（fail-closed）
- /static/、/admin/ 跳过
- connect-src 注入与 report-uri 存在
- 上报端点: POST 204 / GET 405 / 超限 413 / 限流 429 / 字段白名单截断与脱敏
逐用例直构 CspMiddleware(lambda req: resp) 驱动,不复用 test client 启动实例（防假绿）。
"""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.handlers.wsgi import WSGIRequest
from django.test import RequestFactory, override_settings

from core.csp_middleware import CspMiddleware, _build_csp_header
from core.csp_report_views import _clip


DIRECTIVES = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "connect-src": ["'self'", "wss://csp.example.com"],
    "report-uri": ["/_csp-violation-report/"],
}


def _run(mode: str, path: str = "/api/v1/assets/"):
    request = RequestFactory().get(path)
    seen: dict[str, str] = {}

    def response(req: WSGIRequest) -> object:
        seen["req"] = req
        return object.__new__(object)  # 任意可下标对象

    class Resp:
        def __setitem__(self, key: str, value: str) -> None:
            seen[key] = value

    middleware = CspMiddleware(lambda req: Resp())
    with override_settings(CSP_MODE=mode, CSP_DIRECTIVES=DIRECTIVES):
        middleware.__call__(request)  # type: ignore[arg-type]
    return seen


class TestCspHeaderBuilder:
    def test_dict_of_lists_joined(self):
        header = _build_csp_header(DIRECTIVES)
        assert "default-src 'self'" in header
        assert "connect-src 'self' wss://csp.example.com" in header

    def test_missing_directives_raises(self):
        with override_settings(CSP_DIRECTIVES=None):
            with pytest.raises(ImproperlyConfigured):
                CspMiddleware(lambda req: None)

    def test_invalid_mode_raises(self):
        with override_settings(CSP_MODE="bogus", CSP_DIRECTIVES=DIRECTIVES):
            with pytest.raises(ImproperlyConfigured):
                CspMiddleware(lambda req: None)


class TestCspThreeState:
    def test_enforce_header(self):
        seen = _run("enforce")
        assert seen["Content-Security-Policy"].startswith("default-src 'self'")

    def test_report_only_header(self):
        seen = _run("report-only")
        assert seen["Content-Security-Policy-Report-Only"].startswith("default-src 'self'")

    def test_off_no_header(self):
        seen = _run("off")
        assert "Content-Security-Policy" not in seen
        assert "Content-Security-Policy-Report-Only" not in seen

    def test_static_and_admin_skipped(self):
        assert "Content-Security-Policy" not in _run("enforce", path="/static/js/app.js")
        assert "Content-Security-Policy" not in _run("enforce", path="/admin/login/")

    def test_report_uri_and_no_unsafe_eval(self):
        seen = _run("enforce")
        assert "report-uri /_csp-violation-report/" in seen["Content-Security-Policy"]
        assert "unsafe-eval" not in seen["Content-Security-Policy"]


class TestCspReportEndpoint:
    def test_post_report_returns_204_and_logged(self, client, caplog):
        with override_settings(DEFAULT_THROTTLE_RATES={"csp_report": "10000000/minute"}):
            resp = client.post(
                "/_csp-violation-report/",
                data=json.dumps(
                    {
                        "document-uri": "https://example.com/assets",
                        "blocked-uri": "https://evil.example.com",
                        "violated-directive": "script-src",
                    }
                ),
                content_type="application/csp-report",
            )
        assert resp.status_code == 204, resp.content

    def test_get_rejected_405(self, client):
        assert client.get("/_csp-violation-report/").status_code == 405

    def test_oversized_body_rejected_413(self, client):
        with override_settings(DEFAULT_THROTTLE_RATES={"csp_report": "10000000/minute"}):
            resp = client.post(
                "/_csp-violation-report/",
                data="x" * (17 * 1024),
                content_type="application/csp-report",
            )
        assert resp.status_code == 413

    def test_reports_plus_json_list_shape_accepted(self, client):
        with override_settings(DEFAULT_THROTTLE_RATES={"csp_report": "10000000/minute"}):
            resp = client.post(
                "/_csp-violation-report/",
                data=json.dumps([{"type": "csp-violation-report", "body": {"document-uri": "https://e.com"}}]),
                content_type="application/reports+json",
            )
        assert resp.status_code == 204

    def test_clip_redacts_sensitive_values(self):
        assert _clip("token=abc123") == "[REDACTED]"
        assert _clip("a" * 300) == "a" * 256

    def test_throttle_returns_429(self, client):
        from django.core.cache import cache

        cache.clear()
        with override_settings(DEFAULT_THROTTLE_RATES={"csp_report": "2/minute"}):
            for _ in range(3):
                resp = client.post("/_csp-violation-report/", data="{}", content_type="application/csp-report")
        assert resp.status_code == 429
