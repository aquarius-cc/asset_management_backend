"""
自定义节流类

提供项目统一的频率限制:
- RegisterRateThrottle: 注册接口频率限制(5次/分钟/IP)
- LoginRateThrottle: 登录接口频率限制(5次/分钟/用户)
"""

import logging

from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)


class RegisterRateThrottle(AnonRateThrottle):
    """
    注册接口频率限制

    使用 scope='register',在 settings 中配置具体频率。
    默认 5次/分钟,防止批量注册攻击。
    """

    scope = "register"


class LoginRateThrottle(AnonRateThrottle):
    """
    登录接口频率限制（H-4）

    按 auth_username 维度限流，防止对单一账户暴力破解。
    与全局 AnonRateThrottle（IP 维度）形成双层防护。
    """

    scope = "login"

    def get_cache_key(self, request, view):
        """以请求体中的 auth_username 为限流键"""
        username = ""
        try:
            if hasattr(request, "data"):
                username = request.data.get("auth_username", "")
        except Exception:
            pass
        if not username:
            username = "anonymous"
        return f"throttle_login_{username}"
