"""
前端错误日志上报端点(B1)

匿名接收前端结构化错误日志, 经固定字段白名单清洗后写入 frontend.error logger。
该端点不加 csrf_exempt: DRF APIView.as_view() 已封装 csrf_exempt(view),
authentication_classes=[] 关闭 SessionAuthentication 的 CSRF 校验路径。
"""

import json
import logging
from typing import Any

from django.http import HttpRequest
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from utils.response_utils import error_response, success_response


logger = logging.getLogger("frontend.error")

_MAX_BODY_BYTES = 16 * 1024
_MAX_MESSAGE_LENGTH = 2000
_MAX_ERROR_MESSAGE_LENGTH = 1000
_MAX_ROUTE_LENGTH = 512
_MAX_MODULE_LENGTH = 128
_MAX_TRACE_ID_LENGTH = 128
_MAX_SHORT_TEXT_LENGTH = 64
_MAX_CONTEXT_VALUE_LENGTH = 256
_MAX_CONTEXT_ITEMS = 20
_LEVELS = frozenset({"debug", "info", "warn", "error"})
_LEVEL_NUMBERS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}
_CONTEXT_KEYS = frozenset({"info", "route", "component", "action", "status"})
_SENSITIVE_MARKERS = (
    "password",
    "token",
    "access",
    "refresh",
    "cookie",
    "authorization",
    "phone",
    "id_card",
)


def _contains_sensitive_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def _clean_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_length]


def _safe_text(value: Any, max_length: int) -> str | None:
    text = _clean_text(value, max_length)
    if text is None:
        return None
    if _contains_sensitive_marker(text):
        return "[REDACTED]"
    return text


def _sanitize_context(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or raw_key not in _CONTEXT_KEYS:
            continue
        if not isinstance(raw_value, (str, int, float, bool)):
            continue
        text = str(raw_value)[:_MAX_CONTEXT_VALUE_LENGTH]
        if _contains_sensitive_marker(raw_key) or _contains_sensitive_marker(text):
            continue
        cleaned[raw_key] = text
        if len(cleaned) >= _MAX_CONTEXT_ITEMS:
            break
    return cleaned


def _build_extra(data: dict[str, Any]) -> dict[str, Any]:
    context = _sanitize_context(data.get("frontend_context"))
    return {
        "client_trace_id": _safe_text(data.get("client_trace_id"), _MAX_TRACE_ID_LENGTH),
        "client_time": _safe_text(data.get("client_time"), _MAX_SHORT_TEXT_LENGTH),
        "release": _safe_text(data.get("release"), _MAX_SHORT_TEXT_LENGTH),
        "env": _safe_text(data.get("env"), _MAX_SHORT_TEXT_LENGTH),
        "route": _safe_text(data.get("route"), _MAX_ROUTE_LENGTH),
        "frontend_module": _safe_text(data.get("frontend_module"), _MAX_MODULE_LENGTH),
        "error_type": _safe_text(data.get("error_type"), _MAX_MODULE_LENGTH),
        "error_message": _safe_text(data.get("error_message"), _MAX_ERROR_MESSAGE_LENGTH),
        "frontend_context": context,
    }


@extend_schema(
    request=inline_serializer(
        name="FrontendLogRequest",
        fields={
            "level": serializers.ChoiceField(choices=["debug", "info", "warn", "error"]),
            "message": serializers.CharField(max_length=_MAX_MESSAGE_LENGTH),
            "client_trace_id": serializers.CharField(required=False, max_length=_MAX_TRACE_ID_LENGTH),
            "client_time": serializers.CharField(required=False, max_length=_MAX_SHORT_TEXT_LENGTH),
            "release": serializers.CharField(required=False, max_length=_MAX_SHORT_TEXT_LENGTH),
            "env": serializers.CharField(required=False, max_length=_MAX_SHORT_TEXT_LENGTH),
            "route": serializers.CharField(required=False, max_length=_MAX_ROUTE_LENGTH),
            "frontend_module": serializers.CharField(required=False, max_length=_MAX_MODULE_LENGTH),
            "error_type": serializers.CharField(required=False, max_length=_MAX_MODULE_LENGTH),
            "error_message": serializers.CharField(required=False, max_length=_MAX_ERROR_MESSAGE_LENGTH),
            "frontend_context": serializers.DictField(required=False),
        },
    ),
    responses={
        200: inline_serializer(
            name="FrontendLogResponse",
            fields={
                "code": serializers.IntegerField(),
                "message": serializers.CharField(),
                "data": serializers.DictField(),
            },
        ),
        400: inline_serializer(
            name="FrontendLogBadRequest",
            fields={
                "code": serializers.IntegerField(),
                "message": serializers.CharField(),
                "data": serializers.DictField(),
            },
        ),
        413: inline_serializer(
            name="FrontendLogTooLarge",
            fields={
                "code": serializers.IntegerField(),
                "message": serializers.CharField(),
                "data": serializers.DictField(),
            },
        ),
        429: inline_serializer(
            name="FrontendLogThrottled",
            fields={
                "code": serializers.IntegerField(),
                "message": serializers.CharField(),
                "data": serializers.DictField(),
            },
        ),
    },
)
class FrontendLogView(APIView):
    """匿名前端日志上报(仅 POST), 固定字段白名单与 16KB 请求体上限。"""

    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "frontend_log"

    def post(self, request: HttpRequest) -> Response:
        try:
            raw_body = request.body
        except Exception:
            return error_response(message="请求体不可读", status_code=status.HTTP_400_BAD_REQUEST)
        if len(raw_body) > _MAX_BODY_BYTES:
            return error_response(message="日志载荷超过 16KB", status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        try:
            data = json.loads(raw_body)
        except (ValueError, TypeError):
            return error_response(message="日志载荷必须是 JSON 对象", status_code=status.HTTP_400_BAD_REQUEST)
        if not isinstance(data, dict):
            return error_response(message="日志载荷必须是 JSON 对象", status_code=status.HTTP_400_BAD_REQUEST)

        level = data.get("level")
        message = _clean_text(data.get("message"), _MAX_MESSAGE_LENGTH)
        if level not in _LEVELS or message is None:
            return error_response(message="level 与 message 必填且合法", status_code=status.HTTP_400_BAD_REQUEST)

        extra = _build_extra(data)
        logger.log(_LEVEL_NUMBERS[level], "frontend log received", extra=extra)
        return success_response()
