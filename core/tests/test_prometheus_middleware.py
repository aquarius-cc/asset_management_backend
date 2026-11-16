"""Prometheus 中间件 endpoint 标签回归（B2：route 模板替代正则归一化）。"""

from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.urls import resolve
from prometheus_client import REGISTRY

from core.prometheus_middleware import PrometheusMiddleware, _endpoint_label, _is_excluded_path


_REQUESTS = "asset_mgmt_http_requests_total"
_ERRORS = "asset_mgmt_http_errors_total"
_LATENCY_COUNT = "asset_mgmt_http_request_duration_seconds_count"
_ACTIVE = "asset_mgmt_http_active_requests"


def _value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _request(path: str, route: str | None = None) -> SimpleNamespace:
    match = SimpleNamespace(route=route) if route is not None else None
    return SimpleNamespace(method="GET", path=path, resolver_match=match)


def test_endpoint_label_uses_route_template():
    request = _request("/api/v1/users/42/", "api/v1/users/(?P<user_id>[^/.]+)/$")
    assert _endpoint_label(request) == "/api/v1/users/<user_id>/"


def test_endpoint_label_handles_root_and_unresolved():
    assert _endpoint_label(_request("/", "^$")) == "/"
    assert _endpoint_label(_request("/missing/")) == "{unresolved}"


def test_actual_asset_detail_route_removes_regex():
    match = resolve("/api/v1/assets/assets/ABC123/")
    label = _endpoint_label(SimpleNamespace(resolver_match=match))
    assert label == "/api/v1/assets/assets/<recordcode>/"
    assert "(?P<" not in label


@pytest.mark.parametrize(
    "path",
    ["/metrics/", "/health/", "/ready/", "/static/app.css", "/media/photo.png"],
)
def test_excluded_operational_paths_are_not_metered(path):
    calls: list[str] = []
    middleware = PrometheusMiddleware(lambda request: calls.append(request.path) or HttpResponse())
    before = _value(_REQUESTS, method="GET", endpoint=path, status_code="200")

    response = middleware(_request(path))

    assert response.status_code == 200
    assert calls == [path]
    assert _value(_REQUESTS, method="GET", endpoint=path, status_code="200") == before


def test_exclusion_is_exact_not_prefix_for_health():
    assert _is_excluded_path("/api/v1/health/") is False
    assert _is_excluded_path("/healthz/") is False


def test_resolved_route_is_metered_with_single_label_value():
    route = "api/v1/widgets/(?P<widget_id>[^/.]+)/$"
    endpoint = "/api/v1/widgets/<widget_id>/"
    labels = {"method": "GET", "endpoint": endpoint, "status_code": "201"}
    before_requests = _value(_REQUESTS, **labels)
    before_latency = _value(_LATENCY_COUNT, method="GET", endpoint=endpoint)
    before_active = _value(_ACTIVE)

    response = PrometheusMiddleware(lambda request: HttpResponse(status=201))(_request("/api/v1/widgets/99/", route))

    assert response.status_code == 201
    assert _value(_REQUESTS, **labels) == before_requests + 1
    assert _value(_LATENCY_COUNT, method="GET", endpoint=endpoint) == before_latency + 1
    assert _value(_ACTIVE) == before_active


def test_error_branch_uses_same_route_label_and_decrements_active():
    route = "api/v1/widgets/(?P<widget_id>[^/.]+)/$"
    endpoint = "/api/v1/widgets/<widget_id>/"
    labels = {"method": "GET", "endpoint": endpoint, "status_code": "500"}
    before_errors = _value(_ERRORS, **labels)
    before_requests = _value(_REQUESTS, **labels)
    before_active = _value(_ACTIVE)

    def raise_error(request):
        raise RuntimeError("boom")

    middleware = PrometheusMiddleware(raise_error)
    with pytest.raises(RuntimeError):
        middleware(_request("/api/v1/widgets/99/", route))

    assert _value(_ERRORS, **labels) == before_errors + 1
    assert _value(_REQUESTS, **labels) == before_requests + 1
    assert _value(_ACTIVE) == before_active
