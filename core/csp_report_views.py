"""CSP 违规上报端点（【MA-15】C6）

浏览器把 securitypolicyviolation 事件以 JSON POST 到 /_csp-violation-report/。
普通 Django 视图（config/urls.py 根级惯例,与 health/ready/metrics 同层）:
- 仅 POST（405 拒绝其余方法）
- 16KB 上限（413 信封拒绝）
- 双 content-type: application/csp-report 与 application/reports+json 均可解析
- 固定字段白名单 + 截断 + 敏感标记脱敏（OC-3 口径,对齐 frontend_log_views）
- IP 限流: DEFAULT_THROTTLE_RATES["csp_report"]（纯 Django 视图,手动计数实现 DRF 同型桶）
- csrf_exempt: 浏览器原生 sendBeacon/CSP 上报无法携带 CSRF 头（同 B1 口径）
- 任何解析失败静默 204,绝不因日志写入失败影响响应
"""

import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


logger = logging.getLogger(__name__)

_REPORT_ENDPOINT = "csp_report"
_BODY_LIMIT_BYTES = 16 * 1024
# 固定字段白名单(值级截断由 _clip 完成,未登记字段整条丢弃)
_ALLOWED_FIELDS = (
    "document-uri",
    "referrer",
    "blocked-uri",
    "violated-directive",
    "effective-directive",
    "original-policy",
    "disposition",
    "status-code",
    "source-file",
    "line-number",
    "column-number",
)
_SENSITIVE_MARKERS = ("password", "token", "cookie", "authorization", "refresh", "access_token")
_MAX_VALUE_LEN = 256


def _clip(value: Any) -> str:
    """值级截断 + 敏感标记脱敏(OC-3: 字符串单值,非递归)"""
    text = str(value)[:_MAX_VALUE_LEN]
    lowered = text.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return "[REDACTED]"
    return text


def _throttle_by_ip(request: Any) -> bool:
    """纯 Django 视图限流: 复用 DEFAULT_THROTTLE_RATES['csp_report'] 的 'N/minute' 形态。

    返回 True = 已限流（应回 429）。
    """
    rates: dict[str, str] = getattr(settings, "DEFAULT_THROTTLE_RATES", {})
    rate = rates.get(_REPORT_ENDPOINT, "0/minute")
    limit = int(rate.split("/", 1)[0]) if rate.split("/", 1)[0].isdigit() else 0
    if limit <= 0:
        return True
    ip = request.META.get("REMOTE_ADDR", "unknown")
    cache_key = f"throttle:{_REPORT_ENDPOINT}:{ip}"
    count = cache.get(cache_key, 0) + 1
    cache.set(cache_key, count, 60)
    return bool(count > limit)


def _parse_report(request: Any) -> dict[str, Any] | None:
    """解析违规报告体（双 content-type）,失败返回 None。"""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    # application/reports+json 形态为 [{"type": "csp-violation-report", "body": {...}}]
    if isinstance(payload, list) and payload:
        payload = payload[0].get("body", payload[0])
    if not isinstance(payload, dict):
        return None
    return payload


def _record_violation(report: dict[str, Any]) -> None:
    """白名单字段落日志（固定消息 + extra 白名单,防注入）"""
    safe: dict[str, str] = {}
    for field in _ALLOWED_FIELDS:
        value = report.get(field)
        if value is not None:
            safe[field.replace("-", "_")] = _clip(value)
    logger.warning(
        "csp violation report",
        extra={"csp_report": json.dumps(safe, ensure_ascii=False)},
    )


@csrf_exempt
@require_POST
def csp_violation_report(request: Any) -> HttpResponse:
    if _throttle_by_ip(request):
        return JsonResponse({"code": 429, "message": "too many reports", "data": None}, status=429)
    if request.META.get("CONTENT_LENGTH") and int(request.META["CONTENT_LENGTH"]) > _BODY_LIMIT_BYTES:
        return JsonResponse({"code": 413, "message": "payload too large", "data": None}, status=413)
    report = _parse_report(request)
    if report is None:
        # 解析失败静默 204: 上报通道永不阻塞业务,也不给攻击者探测回执
        return HttpResponse(status=204)
    _record_violation(report)
    return HttpResponse(status=204)
