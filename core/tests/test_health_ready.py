"""
health/ready 冒烟测试（F-P2-1，OC-6 落地护栏）

覆盖:
1. /health/ 全依赖健康 → 200 + status=healthy + checks 含 database/redis
2. /health/ Redis 不可用 → 503 + status=unhealthy（database 仍 healthy）
3. /ready/ 全依赖就绪 → 200 + status=ready
4. /ready/ Redis 不可用 → 503 + 且响应体不泄露异常详情（H-3 安全要求）
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


def _fake_redis(monkeypatch: pytest.MonkeyPatch, *, ok: bool) -> None:
    """注入假 redis 模块：ok=True ping 成功；ok=False from_url 抛连接错误。"""
    module = types.ModuleType("redis")
    redis_cls = MagicMock()
    if ok:
        conn = MagicMock()
        conn.ping.return_value = True
        redis_cls.from_url.return_value = conn
    else:
        redis_cls.from_url.side_effect = ConnectionError("redis unavailable (injected)")
    module.Redis = redis_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", module)


@pytest.mark.django_db
class TestHealthEndpoint:
    """GET /health/ 冒烟"""

    def test_all_healthy_returns_200(self, client, monkeypatch):
        _fake_redis(monkeypatch, ok=True)
        resp = client.get("/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["redis"] == "healthy"
        assert data["version"] == "1.0.0"

    def test_redis_down_returns_503(self, client, monkeypatch):
        _fake_redis(monkeypatch, ok=False)
        resp = client.get("/health/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["redis"] == "unhealthy"


@pytest.mark.django_db
class TestReadyEndpoint:
    """GET /ready/ 冒烟"""

    def test_all_connected_returns_200(self, client, monkeypatch):
        _fake_redis(monkeypatch, ok=True)
        resp = client.get("/ready/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["service"] == "asset-management-backend"
        assert data["checks"]["database"] == "connected"
        assert data["checks"]["redis"] == "connected"

    def test_redis_down_returns_503_without_detail_leak(self, client, monkeypatch):
        """H-3：未认证探测不得暴露依赖异常详情"""
        _fake_redis(monkeypatch, ok=False)
        resp = client.get("/ready/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"] == "unavailable"
        body = resp.content.decode("utf-8")
        assert "redis unavailable (injected)" not in body
        assert "Traceback" not in body
