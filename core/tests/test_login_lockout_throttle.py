"""
登录锁定节流：失败计数原子化（M-24 / BF-137）

M-24：`LoginLockoutThrottle.record_failure` 曾以 cache.get → +1 → cache.set
读改写更新失败计数，并发登录失败可丢计数、5 次锁定阈值被放大绕过。
修复口径：cache.add 种子（SETNX+TTL 原子）→ cache.incr（原子自增）→
cache.touch（复刻原每次 set 刷新 15 分钟 TTL 的滚动窗口语义）。

红点（对读改写实现必红）:
- test_record_failure_never_uses_get_set_read_modify_write —— mock cache 断言
  record_failure 不触达 cache.get / cache.set。

行为路径（mock cache，修复态精确断言调用）: 种入 / 自增 / add→incr 竞态过期
双回退 / 阈值 warning。集成（真实 LocMemCache）: 5 连败锁定 + record_success
解锁; 并发 10×20 精确计数（LocMemCache incr 线程安全）。

速率口径: 与 BF-128 同范式 monkeypatch.setattr(LoginLockoutThrottle, "rate", ...)
直设，绕 DRF THROTTLE_RATES 导入期快照（见 test_create_throttle.py 文件头）。
"""

import logging
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache

from core.throttles import LoginLockoutThrottle


# 【M-48】失败键 = username+IP 复合;_request() 默认无 META → IP 回退 unknown
FAIL_KEY = "login_fail_lock_u1_unknown"


def _request(username: str = "lock_u1", ip: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(data={"auth_username": username}, META={"REMOTE_ADDR": ip} if ip else {})


def _throttle() -> LoginLockoutThrottle:
    return LoginLockoutThrottle()


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    # 兜底旧读改写实现可运行（当前实现走 get→set，红由断言驱动而非报错驱动）
    fake.get.return_value = 0
    monkeypatch.setattr("core.throttles.cache", fake)
    return fake


class TestRecordFailureAtomicity:
    """M-24 红点与 mock 路径：禁读改写、走 add/incr/touch 原子链"""

    def test_record_failure_never_uses_get_set_read_modify_write(self, fake_cache: MagicMock) -> None:
        """record_failure 不得触达 cache.get / cache.set 读改写"""
        _throttle().record_failure(_request(), None)
        fake_cache.get.assert_not_called()
        fake_cache.set.assert_not_called()

    def test_first_failure_seeds_counter_with_ttl(self, fake_cache: MagicMock) -> None:
        """首次失败以 add 种入计数 1 并带 15 分钟 TTL"""
        fake_cache.add.return_value = True
        _throttle().record_failure(_request(), None)
        fake_cache.add.assert_called_once_with(FAIL_KEY, 1, LoginLockoutThrottle.LOCKOUT_DURATION)
        fake_cache.touch.assert_called_once_with(FAIL_KEY, LoginLockoutThrottle.LOCKOUT_DURATION)

    def test_existing_counter_increments_atomically(self, fake_cache: MagicMock) -> None:
        """键已存在走 incr 原子自增，不读改写"""
        fake_cache.add.return_value = False
        fake_cache.incr.return_value = 3
        _throttle().record_failure(_request(), None)
        fake_cache.incr.assert_called_once_with(FAIL_KEY)
        fake_cache.set.assert_not_called()

    def test_threshold_failure_logs_lockout_warning(
        self, fake_cache: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """自增到阈值 5 次时输出锁定 warning"""
        fake_cache.add.return_value = False
        fake_cache.incr.return_value = LoginLockoutThrottle.LOCKOUT_THRESHOLD
        with caplog.at_level(logging.WARNING, logger="core.throttles"):
            _throttle().record_failure(_request(), None)
        assert "登录锁定触发" in caplog.text
        assert "lock_u1" in caplog.text

    def test_expiry_race_after_add_reseeds_counter(self, fake_cache: MagicMock) -> None:
        """add 判键在、incr 时键已过期：重试种入计为新窗口 1"""
        fake_cache.add.side_effect = [False, True]
        fake_cache.incr.side_effect = ValueError("key expired")
        _throttle().record_failure(_request(), None)
        assert fake_cache.add.call_count == 2
        fake_cache.incr.assert_called_once_with(FAIL_KEY)

    def test_expiry_race_with_concurrent_winner_takes_value(self, fake_cache: MagicMock) -> None:
        """add 判键在、incr 时键过期、并发已抢先种入：取并发真值"""
        fake_cache.add.side_effect = [False, False]
        fake_cache.incr.side_effect = [ValueError("key expired"), 7]
        _throttle().record_failure(_request(), None)
        assert fake_cache.add.call_count == 2
        assert fake_cache.incr.call_count == 2

    def test_double_expiry_race_counts_fresh_window(self, fake_cache: MagicMock) -> None:
        """双轮竞态仍失败：按新窗口 1 计，不抛异常"""
        fake_cache.add.side_effect = [False, False]
        fake_cache.incr.side_effect = [
            ValueError("key expired"),
            ValueError("key expired"),
        ]
        _throttle().record_failure(_request(), None)
        assert fake_cache.add.call_count == 2
        fake_cache.touch.assert_called_once_with(FAIL_KEY, LoginLockoutThrottle.LOCKOUT_DURATION)


@pytest.mark.django_db
class TestLoginLockoutBehavior:
    """真实 cache 行为回归：阈值锁定、成功解锁、并发零丢失"""

    def setup_method(self) -> None:
        cache.clear()

    def teardown_method(self) -> None:
        cache.clear()

    def test_five_failures_lock_account_then_success_unlocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """连败 5 次后拒请求，record_success 后立即放行"""
        monkeypatch.setattr(LoginLockoutThrottle, "rate", "1000/minute", raising=False)
        throttle = _throttle()
        request = _request()
        for _ in range(LoginLockoutThrottle.LOCKOUT_THRESHOLD - 1):
            throttle.record_failure(request, None)
        assert throttle.allow_request(request, None) is True
        throttle.record_failure(request, None)
        assert throttle.allow_request(request, None) is False
        throttle.record_success(request, None)
        assert throttle.allow_request(request, None) is True

    def test_concurrent_record_failures_lose_no_count(self) -> None:
        """10 线程 × 20 次并发失败计数精确等于 200（读改写实现必丢）"""
        request = _request()
        threads = [
            threading.Thread(target=lambda: [_throttle().record_failure(request, None) for _ in range(20)])
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert cache.get(FAIL_KEY) == 200

    def test_allow_request_locked_accounts_do_not_call_rate_throttle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """已锁定账户在 allow_request 前置分支被拒，不再进入速率限流"""
        monkeypatch.setattr(LoginLockoutThrottle, "rate", "1000/minute", raising=False)
        throttle = _throttle()
        request = _request()
        for _ in range(LoginLockoutThrottle.LOCKOUT_THRESHOLD):
            throttle.record_failure(request, None)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(type(throttle).__mro__[1], "allow_request", lambda self, req, view: True)
            assert throttle.allow_request(request, None) is False

    def test_same_username_different_ips_count_independently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """【M-48】同用户名跨 IP 独立计数:单 IP 连败锁定不影响该用户名其他 IP"""
        monkeypatch.setattr(LoginLockoutThrottle, "rate", "1000/minute", raising=False)
        throttle = _throttle()
        req_a = _request(ip="198.51.100.1")
        req_b = _request(ip="198.51.100.2")
        for _ in range(LoginLockoutThrottle.LOCKOUT_THRESHOLD):
            throttle.record_failure(req_a, None)
        assert throttle.allow_request(req_a, None) is False
        assert throttle.allow_request(req_b, None) is True

    def test_record_success_clears_only_current_ip_bucket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """【M-48】成功解锁只清当前 IP 桶,不误删其他 IP 的失败计数"""
        monkeypatch.setattr(LoginLockoutThrottle, "rate", "1000/minute", raising=False)
        throttle = _throttle()
        req_a = _request(ip="198.51.100.1")
        req_b = _request(ip="198.51.100.2")
        for _ in range(LoginLockoutThrottle.LOCKOUT_THRESHOLD):
            throttle.record_failure(req_a, None)
        throttle.record_success(req_b, None)
        assert throttle.allow_request(req_a, None) is False
        assert throttle.allow_request(req_b, None) is True


class TestHelperCallChain:
    """record_failure 与 helper 的调用链结构断言（防回归到内联读改写）"""

    def test_helper_exists_and_returns_int(self, fake_cache: MagicMock) -> None:
        """_increment_fail_count 返回整型计数"""
        fake_cache.add.return_value = True
        result: Any = _throttle()._increment_fail_count(FAIL_KEY)
        assert isinstance(result, int)
        assert result == 1
