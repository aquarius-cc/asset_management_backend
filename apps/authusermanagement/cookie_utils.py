"""
JWT Cookie 读写工具(B-1/B-2/B-3 共用)

函数/方法:
  - set_auth_cookies: 双写 access/refresh Cookie(HttpOnly + SameSite=Lax + Secure(env))
  - delete_auth_cookies: 双删 Cookie
  - get_access_token / get_refresh_token: 从 Cookie 读取 token

调用链:
  views.LoginAPIView / RegisterAPIView / RBACTokenRefreshView / LogoutAPIView -> 本模块
  本模块依赖 config.settings(JWT_AUTH_COOKIE_* 配置)
"""

from typing import Any

from django.conf import settings
from django.middleware.csrf import get_token


def _cookie_base_attrs() -> dict[str, Any]:
    """Cookie 公共属性(B-5:Secure/SameSite 走 env)"""
    return {
        "httponly": True,
        "samesite": settings.JWT_AUTH_COOKIE_SAMESITE,
        "secure": settings.JWT_AUTH_COOKIE_SECURE,
        "path": "/",
    }


def set_auth_cookies(request: Any, response: Any, access_token: str, refresh_token: str | None = None) -> None:
    """
    双写认证 Cookie + 刷新 CSRF token Cookie(B-2/B-3 共用)

    - access_token: session cookie(浏览器关闭即失效,max_age=None)
    - refresh_token: 固定 7 天(max_age 由 env 可调)
    - csrftoken: 每次认证成功强制刷新(防 Login CSRF, 登录时重新绑定 token)
    """
    response.set_cookie(
        settings.JWT_AUTH_COOKIE_ACCESS,
        access_token,
        max_age=settings.JWT_AUTH_COOKIE_ACCESS_MAX_AGE,
        **_cookie_base_attrs(),
    )
    if refresh_token:
        response.set_cookie(
            settings.JWT_AUTH_COOKIE_REFRESH,
            refresh_token,
            max_age=settings.JWT_AUTH_COOKIE_REFRESH_MAX_AGE,
            **_cookie_base_attrs(),
        )
    # CSRF token: 认证成功后下发新的 csrftoken, 后续不安全方法需携带 X-CSRFToken
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        get_token(request),
        max_age=settings.CSRF_COOKIE_AGE,
        httponly=settings.CSRF_COOKIE_HTTPONLY,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        secure=settings.CSRF_COOKIE_SECURE,
        path=settings.CSRF_COOKIE_PATH,
    )


def delete_auth_cookies(response: Any) -> None:
    """删除 access/refresh Cookie"""
    response.delete_cookie(settings.JWT_AUTH_COOKIE_ACCESS, path="/")
    response.delete_cookie(settings.JWT_AUTH_COOKIE_REFRESH, path="/")


def get_access_token(request: Any) -> str | None:
    """从 Cookie 读取 access token"""
    return request.COOKIES.get(settings.JWT_AUTH_COOKIE_ACCESS)  # type: ignore[no-any-return]


def get_refresh_token(request: Any) -> str | None:
    """从 Cookie 读取 refresh token"""
    return request.COOKIES.get(settings.JWT_AUTH_COOKIE_REFRESH)  # type: ignore[no-any-return]
