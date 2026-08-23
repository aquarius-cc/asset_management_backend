"""
Prometheus 指标端点 (OC-4 落地)

暴露 /metrics/ 端点供 Prometheus 抓取。
包含: 请求总数、请求耗时直方图(P50/P90/P99)、活跃请求、错误计数。

注意: 此端点不需要认证(Prometheus 内部抓取),通过 urls.py 直接挂载。
"""

from typing import TYPE_CHECKING

from django.http import HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


if TYPE_CHECKING:
    from django.http import HttpRequest


# 按 HTTP 方法和路径模式分组的请求计数
REQUEST_COUNT = Counter(
    "asset_mgmt_http_requests_total",
    "HTTP 请求总数",
    ["method", "endpoint", "status_code"],
)

# 按 HTTP 方法和路径模式分组的请求耗时直方图
# buckets 覆盖 50ms~30s,覆盖从健康检查到慢查询全场景
REQUEST_LATENCY = Histogram(
    "asset_mgmt_http_request_duration_seconds",
    "请求耗时(秒)",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# 当前活跃请求数(Gauge,用于容量规划)
ACTIVE_REQUESTS = Gauge(
    "asset_mgmt_http_active_requests",
    "当前活跃请求数",
)

# 5xx 错误计数(用于告警)
ERROR_COUNT = Counter(
    "asset_mgmt_http_errors_total",
    "HTTP 5xx 错误总数",
    ["method", "endpoint", "status_code"],
)

# 数据库查询计数(用于检测慢查询)
DB_QUERY_COUNT = Counter(
    "asset_mgmt_db_queries_total",
    "数据库查询总数",
)

DB_QUERY_LATENCY = Histogram(
    "asset_mgmt_db_query_duration_seconds",
    "数据库查询耗时(秒)",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def metrics_view(request: "HttpRequest") -> HttpResponse:
    """
    Prometheus 指标端点

    返回格式符合 OpenMetrics 规范的文本格式。
    Prometheus 通过 scrape_interval 定期请求此端点。
    """
    return HttpResponse(
        generate_latest(),
        content_type=CONTENT_TYPE_LATEST,
    )
