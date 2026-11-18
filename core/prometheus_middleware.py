"""
Prometheus 请求指标采集中间件

自动采集每个 HTTP 请求的:
- 请求计数 (按 method/endpoint/status_code 分组)
- 请求耗时直方图 (按 method/endpoint 分组)
- 活跃请求 Gauge
- 5xx 错误计数

endpoint 归一化: 优先使用 Django resolver_match.route 的静态模板
(/api/v1/users/<user_id>/), 不再对实际路径跑正则猜测, 防止高基数标签导致
Prometheus 内存爆炸; 未解析路由统一记为 {unresolved}。
"""

import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.metrics import ACTIVE_REQUESTS, ERROR_COUNT, REQUEST_COUNT, REQUEST_LATENCY


if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


_EXCLUDED_EXACT = frozenset({"/metrics/", "/health/", "/ready/"})
_EXCLUDED_PREFIXES = ("/static/", "/media/")
_UNRESOLVED_ENDPOINT = "{unresolved}"
_ROUTE_PARAM_RE = re.compile(r"\(\?P<([A-Za-z_][A-Za-z0-9_]*)>[^)]*\)")


def _is_excluded_path(path: str) -> bool:
    """运维端点不进入业务指标, 避免抓取/探针污染请求统计。"""
    return path in _EXCLUDED_EXACT or path.startswith(_EXCLUDED_PREFIXES)


def _endpoint_label(request: "HttpRequest") -> str:
    """从路由模板生成低基数 endpoint 标签, 不含实际路径参数。"""
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None)
    if not isinstance(route, str) or not route:
        return _UNRESOLVED_ENDPOINT
    normalized = route.removeprefix("^").removesuffix("$")
    normalized = _ROUTE_PARAM_RE.sub(r"<\1>", normalized)
    return "/" + normalized.lstrip("/")


class PrometheusMiddleware:
    """Django 中间件, 采集 Prometheus 指标"""

    def __init__(self, get_response: "Callable[[HttpRequest], HttpResponse]") -> None:
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        if _is_excluded_path(request.path):
            return self.get_response(request)

        method = request.method
        ACTIVE_REQUESTS.inc()
        start_time = time.monotonic()

        try:
            response = self.get_response(request)
        except Exception:
            endpoint = _endpoint_label(request)
            ERROR_COUNT.labels(method=method, endpoint=endpoint, status_code=500).inc()
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=500).inc()
            raise
        finally:
            ACTIVE_REQUESTS.dec()

        endpoint = _endpoint_label(request)
        duration = time.monotonic() - start_time
        status_code = response.status_code

        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

        if 500 <= status_code < 600:
            ERROR_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()

        return response
