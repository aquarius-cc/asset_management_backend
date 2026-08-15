"""
JWT 双通道认证类 (Bearer 优先, Cookie 兜底)

通道判定 (全端唯一实现, DR-1):
  - 请求携带 Authorization: Bearer 头且为有效 JWT 格式 -> bearer 通道 (移动端 / API 客户端 / 遗留前端)
  - 否则 -> cookie 通道 (PC 浏览器同源 HttpOnly Cookie)

认证规则:
  1. Bearer 头存在 -> 以 Bearer token 为准 (过期/无效抛 InvalidToken -> 401)
  2. 否则读取 JWT access Cookie, 严格校验 (过期/无效抛 InvalidToken -> 401)
  3. cookie 通道 + 非安全方法 -> 强制 CSRF 校验
  4. 通道信息写入 request.auth_channel 供日志/审计观测

调用链:
  config.settings.base.REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES -> 本模块
  视图层 (refresh/logout) 通道判定与 CSRF 兜底复用本模块
"""

from typing import Any

from django.conf import settings
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


_SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")


def get_auth_channel(request: Any) -> str:
    """返回请求所属认证通道: 'bearer' 或 'cookie'"""
    header = JWTAuthentication().get_header(request)
    if header is None:
        return "cookie"
    try:
        return "bearer" if JWTAuthentication().get_raw_token(header) else "cookie"
    except AuthenticationFailed:
        return "bearer"


def enforce_csrf(request: Any) -> None:
    """按 DRF SessionAuthentication.enforce_csrf 语义强制 CSRF 校验"""
    # Django test Client 默认置 request._dont_enforce_csrf_checks=True 跳过校验,
    # 此处显式复位, 保证测试与生产行为一致(生产环境该属性从未被设置)。
    request._dont_enforce_csrf_checks = False
    check = CSRFCheck(lambda request: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF Failed: {reason}")


def enforce_csrf_if_cookie_channel(request: Any) -> None:
    """
    AllowAny 端点 (refresh/logout) 的 CSRF 兜底:
    cookie 通道 (无 Bearer 头) 且携带 JWT refresh Cookie 时强制 CSRF 校验。
    """
    if get_auth_channel(request) == "bearer":
        return
    if request.COOKIES.get(settings.JWT_AUTH_COOKIE_REFRESH):
        enforce_csrf(request)


class JWTCookieAuthentication(JWTAuthentication):
    """
    双认证通道: Bearer 优先, Cookie 兜底 (浏览器同源场景).

    复用父类 JWTAuthentication 的 token 解析与 user 解析逻辑 (DR-1: 不另写解码).
    """

    def authenticate(self, request: Any) -> tuple[Any, Any] | None:
        channel = get_auth_channel(request)
        request.auth_channel = channel
        raw_token = self._resolve_raw_token(request, channel)
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        if channel == "cookie" and request.method not in _SAFE_METHODS:
            enforce_csrf(request)
        return user, validated_token

    def _resolve_raw_token(self, request: Any, channel: str) -> bytes | None:
        """Bearer 优先取 Authorization 头, 否则取 access Cookie"""
        if channel == "bearer":
            header = self.get_header(request)
            if header is None:
                return None
            return self.get_raw_token(header)
        cookie_token = request.COOKIES.get(settings.JWT_AUTH_COOKIE_ACCESS)
        return cookie_token.encode("utf-8") if cookie_token else None
