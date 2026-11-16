"""前端错误日志上报端点回归（B1）。"""

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, SimpleTestCase
from django.urls import path
from django.views.decorators.csrf import csrf_protect

from core.frontend_log_views import FrontendLogView


_URL = "/api/v1/frontend-logs/"


def _payload(**overrides):
    base = {
        "level": "error",
        "message": "Vue render failed",
        "client_trace_id": "trace-abc",
        "client_time": "2026-11-16T10:00:00+08:00",
        "release": "v1.2.3",
        "env": "production",
        "route": "/assets/",
        "frontend_module": "AssetDetail",
        "error_type": "TypeError",
        "error_message": "x is undefined",
        "frontend_context": {"route": "/assets/", "status": "failed"},
    }
    base.update(overrides)
    return base


def _post(client: Client, body):
    if isinstance(body, bytes):
        return client.post(_URL, data=body, content_type="application/json")
    return client.post(_URL, data=json.dumps(body), content_type="application/json")


def _csrf_control(request):
    return HttpResponse("ok")


urlpatterns = [
    path("api/v1/frontend-logs/", FrontendLogView.as_view()),
    path("__csrf-control/", csrf_protect(_csrf_control)),
]


@pytest.mark.urls(__name__)
class TestFrontendLogEndpoint(SimpleTestCase):
    def test_post_logs_whitelisted_fields_and_returns_success_envelope(self):
        logger = patch("core.frontend_log_views.logger").start()
        response = _post(Client(), _payload())

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"] == {}
        logger.log.assert_called_once()
        level, message = logger.log.call_args.args
        extra = logger.log.call_args.kwargs["extra"]
        assert level == 40
        assert message == "frontend log received"
        assert extra == {
            "client_trace_id": "trace-abc",
            "client_time": "2026-11-16T10:00:00+08:00",
            "release": "v1.2.3",
            "env": "production",
            "route": "/assets/",
            "frontend_module": "AssetDetail",
            "error_type": "TypeError",
            "error_message": "x is undefined",
            "frontend_context": {"route": "/assets/", "status": "failed"},
        }

    def test_unknown_context_keys_and_sensitive_values_are_dropped(self):
        logger = patch("core.frontend_log_views.logger").start()
        response = _post(
            Client(),
            _payload(
                frontend_context={
                    "unknown": "value",
                    "password": "s3cr3t",
                    "token": "abc",
                    "route": "/assets/",
                    "authorization": "Bearer abc",
                },
                error_message="token=s3cr3t",
            ),
        )

        assert response.status_code == 200
        extra = logger.log.call_args.kwargs["extra"]
        assert extra["frontend_context"] == {"route": "/assets/"}
        assert extra["error_message"] == "[REDACTED]"
        assert "s3cr3t" not in json.dumps(extra, ensure_ascii=False)

    def test_missing_or_invalid_fields_are_rejected(self):
        cases = [
            _payload(level="fatal"),
            _payload(message=""),
            _payload(message="   "),
            _payload(message=123),
            {**_payload(), "message": None},
        ]
        for payload in cases:
            response = _post(Client(), payload)
            assert response.status_code == 400
            assert response.json()["code"] == 400

    def test_oversized_body_is_rejected_before_parse(self):
        response = _post(Client(), b'{"message":"' + b"a" * 17000 + b'"}')
        assert response.status_code == 413
        assert response.json()["code"] == 413

    def test_invalid_json_is_rejected(self):
        response = _post(Client(), b"{not-json")
        assert response.status_code == 400
        assert response.json()["code"] == 400

    def test_throttle_limit_applies(self):
        from rest_framework.throttling import ScopedRateThrottle

        class TwoPerMinuteThrottle(ScopedRateThrottle):
            rate = "2/minute"

        client = Client()
        payload = _payload()
        with (
            patch.object(FrontendLogView, "throttle_classes", [TwoPerMinuteThrottle]),
            patch.object(TwoPerMinuteThrottle, "get_rate", return_value="2/minute"),
        ):
            cache.clear()
            statuses = [_post(client, payload).status_code for _ in range(3)]

        assert statuses == [200, 200, 429]

    def test_view_accepts_without_csrf_token(self):
        logger = patch("core.frontend_log_views.logger").start()
        response = _post(Client(enforce_csrf_checks=True), _payload())
        assert response.status_code == 200
        logger.log.assert_called_once()

    def test_csrf_control_view_requires_token(self):
        response = Client(enforce_csrf_checks=True).post("/__csrf-control/")
        assert response.status_code == 403
