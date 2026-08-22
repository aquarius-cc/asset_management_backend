"""
Prometheus 请求指标采集中间件

自动采集每个 HTTP 请求的:
- 请求计数 (按 method/endpoint/status_code 分组)
- 请求耗时直方图 (按 method/endpoint 分组)
- 活跃请求 Gauge
- 5xx 错误计数

endpoint 归一化: 将动态路径参数(如 /api/v1/users/42/) 映射为静态模式
(/api/v1/users/{id}/),防止高基数标签导致 Prometheus 内存爆炸。
"""

import re
import time
from typing import TYPE_CHECKING, Callable

from core.metrics import ACTIVE_REQUESTS, ERROR_COUNT, REQUEST_COUNT, REQUEST_LATENCY

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


# 动态路径 → 静态模式的归一化规则
# 按匹配优先级从高到低排列
_PATH_PATTERNS = [
    # UUID
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "{uuid}"),
    # 纯数字 ID
    (re.compile(r"/\d+/"), "/{id}/"),
    # JWT token 路径(如 /token/blacklist/)
    (re.compile(r"/token/blacklist/"), "/token/blacklist/"),
]


def _normalize_path(path: str) -> str:
    """将动态路径归一化为静态模式,防止高基数标签"""
    for pattern, replacement in _PATH_PATTERNS:
        path = pattern.sub(replacement, path)
    return path


class PrometheusMiddleware:
    """Django 中间件: 采集 Prometheus 指标"""

    def __init__(self, get_response: "Callable[[HttpRequest], HttpResponse]") -> None:
        self.get_response = get_response

    def __call__(self, request: "HttpRequest") -> "HttpResponse":
        # 排除 /metrics/ 自身,避免递归计数
        if request.path == "/metrics/":
            return self.get_response(request)

        endpoint = _normalize_path(request.path)
        method = request.method

        ACTIVE_REQUESTS.inc()
        start_time = time.monotonic()

        try:
            response = self.get_response(request)
        except Exception:
            # 请求处理异常: 计数 5xx 并重新抛出
            ERROR_COUNT.labels(method=method, endpoint=endpoint, status_code=500).inc()
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=500).inc()
            raise
        finally:
            ACTIVE_REQUESTS.dec()

        duration = time.monotonic() - start_time
        status_code = response.status_code

        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

        if 500 <= status_code < 600:
            ERROR_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()

        return response
