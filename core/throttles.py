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

from core.request_context import RequestContextMiddleware


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
        logger.warning("%s: 无法读取请求数据: %s", owner, exc)
    return username or "anonymous"


def _client_ip(request: Any) -> str:
    """【M-48】登录失败键的客户端 IP

    复用中间件 _get_client_ip 单一信任边界(TRUST_PROXY_HEADERS 决定 XFF 是否可信);
    无 META 的构造请求(单测 SimpleNamespace)回退 "unknown",不抛异常。
    """
    if not hasattr(request, "META"):
        return "unknown"
    return RequestContextMiddleware._get_client_ip(request) or "unknown"


def _fail_key(username: str, request: Any) -> str:
    """【M-48】登录失败计数键 = username+IP 复合(单一实现 DR-1)

    allow_request / record_failure / record_success 三处调用点收敛到此,
    任一处改键格式三处同步,防 key 漂移导致锁定失效或泄漏。
    """
    return f"login_fail_{username}_{_client_ip(request)}"


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
        """以请求体中的 auth_username 为限流键

        【M-32】key 含类名前缀: 本类与 LoginLockoutThrottle 同挂登录视图且同
        scope="login",共享 throttle_login_{username} 会一请求双计 rate history
        (实际 ~2.5 次/分,收紧了配置的 5 次/分);类名前缀使两节流各自独立计数。
        """
        return f"throttle_{type(self).__name__}_{_extract_login_username(request, 'LoginRateThrottle')}"


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
        """登录锁定 rate history 键(【M-32】类名前缀与 LoginRateThrottle 隔离,
        避免共享 throttle_login_ 前缀双计;失败计数键 login_fail_ 不受影响)"""
        username = self._get_username(request)
        return f"throttle_{type(self).__name__}_{username}"

    def allow_request(self, request: Any, view: Any) -> bool:
        username = self._get_username(request)
        ip = _client_ip(request)
        fail_key = _fail_key(username, request)
        fail_count = cache.get(fail_key, 0)
        if fail_count >= self.LOCKOUT_THRESHOLD:
            logger.warning(f"登录锁定: {username}@{ip} 已失败 {fail_count} 次,锁定中")
            return False
        return super().allow_request(request, view)

    def _increment_fail_count(self, fail_key: str) -> int:
        """原子自增登录失败计数（M-24）

        add 种子（SETNX+TTL 原子）→ 已存在走 incr（原子自增，并发失败不丢计数）。
        incr 仅在键读取瞬间缺失时抛 ValueError（add 判在 → 键在其间过期的竞态），
        此时进入下一轮重试种入；两轮极端竞态后按新窗口 1 计，不抛出。
        全程不出现 get→set 读改写（原实现并发丢计数、5 次锁定阈值可被放大）。
        """
        for _attempt in range(2):
            if cache.add(fail_key, 1, self.LOCKOUT_DURATION):
                return 1
            try:
                return cache.incr(fail_key)
            except ValueError:
                logger.warning("登录失败计数键过期竞态，重试种入: %s", fail_key)
        return 1

    def record_failure(self, request: Any, view: Any) -> None:
        """登录失败时调用（原子计数 + 滚动窗口刷新）"""
        username = self._get_username(request)
        ip = _client_ip(request)
        fail_key = _fail_key(username, request)
        count = self._increment_fail_count(fail_key)
        # 滚动窗口: 每次失败刷新 15 分钟过期（复刻原 set 刷新 TTL 语义）
        cache.touch(fail_key, self.LOCKOUT_DURATION)
        if count >= self.LOCKOUT_THRESHOLD:
            logger.warning(f"登录锁定触发: {username}@{ip} 连续失败 {count} 次,锁定 15 分钟")

    def record_success(self, request: Any, view: Any) -> None:
        """登录成功时调用(仅清当前 IP 桶,【M-48】不误删其他 IP 的失败计数)"""
        cache.delete(_fail_key(self._get_username(request), request))
