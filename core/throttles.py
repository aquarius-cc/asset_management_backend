"""
自定义节流类

提供项目统一的频率限制:
- RegisterRateThrottle: 注册接口频率限制(5次/分钟/IP)
- LoginRateThrottle: 登录接口频率限制(5次/分钟/用户)
- LoginLockoutThrottle: 登录锁定(连续失败5次后锁定15分钟)
"""

import logging
from typing import Any

from django.core.cache import cache
from rest_framework.throttling import AnonRateThrottle


logger = logging.getLogger(__name__)


def _extract_login_username(request: Any, owner: str) -> str:
    """从登录请求中提取 auth_username(读取失败时回退 'anonymous')

    【DR-1 收敛】原 LoginRateThrottle.get_cache_key 与
    LoginLockoutThrottle._get_username 的完全重复实现。
    行为零变更: 异常捕获范围、日志文案(含类名前缀)、返回值与原实现逐字一致。
    """
    username = ""
    try:
        if hasattr(request, "data"):
            username = request.data.get("auth_username", "")
    except Exception as exc:
        # AI_REVIEW_NEEDED: silent except 为存量模式, 本次仅原样搬移未改变行为
        logger.warning("%s: 无法读取请求数据: %s", owner, exc)
    return username or "anonymous"


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

    按 auth_username 维度限流, 防止对单一账户暴力破解。
    与全局 AnonRateThrottle（IP 维度）形成双层防护。
    """

    scope = "login"

    def get_cache_key(self, request: Any, view: Any) -> Any:
        """以请求体中的 auth_username 为限流键"""
        return f"throttle_login_{_extract_login_username(request, 'LoginRateThrottle')}"


class LoginLockoutThrottle(AnonRateThrottle):
    """
    登录锁定:连续失败5次后锁定15分钟

    依据: 03-业务规则与状态机.md §4.6
    "连续登录失败 5 次后,账户锁定 15 分钟"

    使用 Django cache 存储失败计数,Redis 生产环境自动过期。
    """

    scope = "login"
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_DURATION = 15 * 60  # 15分钟

    def _get_username(self, request: Any) -> str:
        return _extract_login_username(request, "LoginLockoutThrottle")

    def get_cache_key(self, request: Any, view: Any) -> Any:
        username = self._get_username(request)
        return f"throttle_login_{username}"

    def allow_request(self, request: Any, view: Any) -> bool:
        username = self._get_username(request)
        fail_key = f"login_fail_{username}"
        fail_count = cache.get(fail_key, 0)
        if fail_count >= self.LOCKOUT_THRESHOLD:
            logger.warning(f"登录锁定: {username} 已失败 {fail_count} 次,锁定中")
            return False
        return super().allow_request(request, view)

    def record_failure(self, request: Any, view: Any) -> None:
        """登录失败时调用"""
        username = self._get_username(request)
        fail_key = f"login_fail_{username}"
        count = cache.get(fail_key, 0)
        cache.set(fail_key, count + 1, self.LOCKOUT_DURATION)
        if count + 1 >= self.LOCKOUT_THRESHOLD:
            logger.warning(f"登录锁定触发: {username} 连续失败 {count + 1} 次,锁定 15 分钟")

    def record_success(self, request: Any, view: Any) -> None:
        """登录成功时调用"""
        username = self._get_username(request)
        cache.delete(f"login_fail_{username}")
