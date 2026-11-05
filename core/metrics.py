"""
Prometheus 指标端点 (OC-4 落地)

暴露 /metrics/ 端点供 Prometheus 抓取。
包含: 请求总数、请求耗时直方图(P50/P90/P99)、活跃请求、错误计数。

注意: [P3-10] METRICS_TOKEN 配置后需 `Authorization: Bearer <token>` 通过;
未配置(空) = 放行(Prometheus 内部抓取场景, 既有行为)。通过 urls.py 直接挂载。
"""

import hmac
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

# 审计写入失败计数(M-19): 审计缺痕属合规事件, 不能只有一行 error 日志
# 渠道: asset_operation_log(AuditLogger._safe_log) / generic_audit_log(GenericAuditService)
#      / unregistered_adapter(UnregisteredAssetAuditAdapter 自吞点)
AUDIT_WRITE_FAILED = Counter(
    "asset_mgmt_audit_write_failed_total",
    "审计日志写入失败总数",
    ["channel"],
)


def _metrics_request_authorized(request: "HttpRequest") -> bool:
    """[P3-10] metrics 端点 Bearer 鉴权(默认关闭)。

    空配置(METRICS_TOKEN 未设) → 放行 = 既有行为(Prometheus 内部抓取);
    配置后仅 `Authorization: Bearer <token>` 匹配通过(hmac.compare_digest
    恒定时间比较); 缺头/方案错/不匹配统一拒绝(不区分原因, 防探测)。
    """
    from django.conf import settings

    expected = getattr(settings, "METRICS_TOKEN", "")
    if not expected:
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth[len("Bearer ") :], expected)


def metrics_view(request: "HttpRequest") -> HttpResponse:
    """
    Prometheus 指标端点

    返回格式符合 OpenMetrics 规范的文本格式。
    Prometheus 通过 scrape_interval 定期请求此端点。
    [P3-10] METRICS_TOKEN 配置且 Bearer 不匹配时 401(默认关闭 = 放行)。
    """
    if not _metrics_request_authorized(request):
        return HttpResponse("unauthorized", status=401, content_type="text/plain")
    return HttpResponse(
        generate_latest(),
        content_type=CONTENT_TYPE_LATEST,
    )
