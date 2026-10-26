"""登录双节流缓存键隔离(M-32 / BF-142)

LoginRateThrottle 与 LoginLockoutThrottle 同挂登录视图(authusermanagement
views.py throttle_classes)且同 scope="login",get_cache_key 曾均返回
throttle_login_{username}: 同一 rate-history 键被两节流各插一次,一请求双计
→ 5 次/分配置实际 ~2.5 次/分(收紧方向,报告 M-32/AUD-37)。

修复: key 加 type(self).__name__ 类名前缀,两节流 history 各自独立;
login_fail_{username}_{ip} 失败计数键已按 M-48 改为 username+IP 复合
(BF-137 原子计数语义不变,见 test_login_lockout_throttle)。

红点(对共享 key 旧实现必红):
- test_keys_are_distinct_and_class_prefixed —— 同 request 两 get_cache_key 相等。
- test_fifth_allowed_sixth_blocked —— 5/minute 下共享 key 第 3 轮即被拒。

速率口径: 与 BF-128 同范式 monkeypatch.setattr(X, "rate", ...) 直设,
绕 THROTTLE_RATES 导入期快照(见 test_create_throttle.py 文件头)。
"""

from types import SimpleNamespace

import pytest
from django.core.cache import cache

from core.throttles import LoginLockoutThrottle, LoginRateThrottle


def _request(username: str = "throttle_key_u1") -> SimpleNamespace:
    return SimpleNamespace(data={"auth_username": username})


class TestLoginThrottleCacheKeySeparation:
    """get_cache_key 类名前缀(M-32 核心红点)"""

    def test_keys_are_distinct_and_class_prefixed(self) -> None:
        """同 request 下两节流 key 必不同且各含类名前缀(旧实现两 key 相等)"""
        request = _request()
        rate_key = LoginRateThrottle().get_cache_key(request, None)
        lock_key = LoginLockoutThrottle().get_cache_key(request, None)
        assert rate_key == "throttle_LoginRateThrottle_throttle_key_u1"
        assert lock_key == "throttle_LoginLockoutThrottle_throttle_key_u1"
        assert rate_key != lock_key

    def test_key_falls_back_to_anonymous_when_username_missing(self) -> None:
        """缺 auth_username 回退 anonymous(_extract_login_username 口径保持)"""
        request = SimpleNamespace(data={})
        assert LoginRateThrottle().get_cache_key(request, None) == "throttle_LoginRateThrottle_anonymous"
        assert LoginLockoutThrottle().get_cache_key(request, None) == "throttle_LoginLockoutThrottle_anonymous"


@pytest.mark.django_db
class TestRateHistoryIsolationBehavior:
    """行为级: 双节流各自按配置 5 次/分计数(共享 key 时第 3 轮即双拒)"""

    def setup_method(self) -> None:
        cache.clear()

    def teardown_method(self) -> None:
        cache.clear()

    def test_fifth_allowed_sixth_blocked_with_both_throttles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """5/minute: 第 1-5 轮双节流均放行,第 6 轮双拒(修复态唯一可能)"""
        monkeypatch.setattr(LoginRateThrottle, "rate", "5/minute", raising=False)
        monkeypatch.setattr(LoginLockoutThrottle, "rate", "5/minute", raising=False)
        request = _request()
        rate_throttle = LoginRateThrottle()
        lock_throttle = LoginLockoutThrottle()
        for _round in range(5):
            assert rate_throttle.allow_request(request, None) is True
            assert lock_throttle.allow_request(request, None) is True
        assert rate_throttle.allow_request(request, None) is False
        assert lock_throttle.allow_request(request, None) is False

    def test_histories_stored_under_separate_keys(self) -> None:
        """cache 键面直证: 两键各自独立存 history,互不读写"""
        request = _request()
        rate_key = LoginRateThrottle().get_cache_key(request, None)
        lock_key = LoginLockoutThrottle().get_cache_key(request, None)
        cache.set(rate_key, [1.0], 60)
        cache.set(lock_key, [2.0, 3.0], 60)
        assert cache.get(rate_key) == [1.0]
        assert cache.get(lock_key) == [2.0, 3.0]
