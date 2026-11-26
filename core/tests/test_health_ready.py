"""
health/ready 冒烟测试（F-P2-1，OC-6 落地护栏）

覆盖:
1. /health/ 全依赖健康 → 200 + status=healthy + checks 含 database/redis
2. /health/ Redis 不可用 → 503 + status=unhealthy（database 仍 healthy）
3. /ready/ 全依赖就绪 → 200 + status=ready
4. /ready/ Redis 不可用 → 503 + 且响应体不泄露异常详情（H-3 安全要求）
5. 批次 2 / M-03+M-04: 探测失败 WARNING 结构化脱敏日志(B1-B6)、超时/重试配置化(B7/B8)、
   静态护栏(H1 配置区间并入 B8 / H2 顶层禁 import redis 并入 B7)
"""

import ast
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.db.utils import OperationalError
from django.test.utils import CaptureQueriesContext

from core.json_formatter import StructuredJSONFormatter
from core.logging_filters import TraceIDFilter


SECRET_FIXTURE = "redis://:s3cr3t@redis:6379/0 postgresql://u:p@db:5432/prod"


def _fake_redis(monkeypatch: pytest.MonkeyPatch, *, ok: bool):
    """注入假 redis 模块：ok=True ping 成功；ok=False from_url 抛含凭据连接错误(批次 2 夹具改造)。"""
    module = types.ModuleType("redis")
    redis_cls = MagicMock()
    if ok:
        conn = MagicMock()
        conn.ping.return_value = True
        redis_cls.from_url.return_value = conn
    else:
        redis_cls.from_url.side_effect = ConnectionError(SECRET_FIXTURE)
    module.Redis = redis_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", module)
    return module


def _assert_structured_probe_log(record, *, ctx, expected):
    """B5 两档 helper(复刻 test_logging_console_trace.py:20-43 权威范式, 零中间件时序依赖)。"""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("core.logging_filters.get_current_trace_id", lambda: ctx)
        assert TraceIDFilter().filter(record) is True
        payload = json.loads(StructuredJSONFormatter().format(record))
    assert payload["trace_id"] == expected
    assert {"time", "level", "trace_id", "message", "module"} <= payload.keys()
    assert "exception" not in payload
    assert "s3cr3t" not in json.dumps(payload, ensure_ascii=False)


def _probe_log_records(caplog):
    return [r for r in caplog.records if r.name == "health" and r.levelno == logging.WARNING]


def _assert_no_secrets(msg: str) -> None:
    for secret in ("s3cr3t", "u:p", "redis:6379", "db:5432"):
        assert secret not in msg


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


@pytest.mark.django_db
class TestProbeObservability:
    """批次 2 / M-03+M-04: 探测失败可观测 + 零敏感信息泄露(OC-3/SC-1)。"""

    def test_health_db_failure_503_and_single_warning_no_leak(self, client, monkeypatch, caplog):
        """B1: DB 失败 → 503 + 响应体逐键不变 + 恰 1 条 WARNING + 零敏感串 + X-Request-ID 透传"""
        _fake_redis(monkeypatch, ok=True)
        with (
            caplog.at_level(logging.WARNING, logger="health"),
            patch("django.db.connection.cursor", side_effect=OperationalError(SECRET_FIXTURE)),
        ):
            resp = client.get("/health/", HTTP_X_REQUEST_ID="req-batch2-abc")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"] == "unhealthy"
        assert data["checks"]["redis"] == "healthy"
        assert data["version"] == "1.0.0"
        assert resp["X-Request-ID"] == "req-batch2-abc"
        records = _probe_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "dependency=database" in msg
        assert "OperationalError" in msg
        _assert_no_secrets(msg)

    def test_health_redis_failure_503_and_single_warning_no_leak(self, client, monkeypatch, caplog):
        """B2: Redis 失败 → 503 + 响应体逐键不变 + 恰 1 条 WARNING(含类型名, 零敏感串)"""
        _fake_redis(monkeypatch, ok=False)
        with caplog.at_level(logging.WARNING, logger="health"):
            resp = client.get("/health/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"] == "healthy"
        assert data["checks"]["redis"] == "unhealthy"
        records = _probe_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "dependency=redis" in msg
        assert "ConnectionError" in msg
        _assert_no_secrets(msg)

    def test_ready_db_failure_503_and_single_warning_no_leak(self, client, monkeypatch, caplog):
        """B3: /ready/ DB 失败 → 503 + 响应体逐键不变 + 1 条 WARNING + 响应体/日志零泄露"""
        _fake_redis(monkeypatch, ok=True)
        with (
            caplog.at_level(logging.WARNING, logger="health"),
            patch("django.db.connection.cursor", side_effect=OperationalError(SECRET_FIXTURE)),
        ):
            resp = client.get("/ready/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["service"] == "asset-management-backend"
        assert data["checks"]["database"] == "unavailable"
        assert data["checks"]["redis"] == "connected"
        assert "s3cr3t" not in resp.content.decode("utf-8")
        records = _probe_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "dependency=database" in msg
        assert "OperationalError" in msg
        _assert_no_secrets(msg)

    def test_ready_redis_failure_503_and_single_warning_no_leak(self, client, monkeypatch, caplog):
        """B4: /ready/ Redis 失败 → 503 + 1 条 WARNING + 响应体/日志零泄露"""
        _fake_redis(monkeypatch, ok=False)
        with caplog.at_level(logging.WARNING, logger="health"):
            resp = client.get("/ready/")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"] == "unavailable"
        assert "s3cr3t" not in resp.content.decode("utf-8")
        records = _probe_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "dependency=redis" in msg
        assert "ConnectionError" in msg
        _assert_no_secrets(msg)

    def test_structured_fields_two_trace_contexts(self, client, monkeypatch, caplog):
        """B5: 结构化字段两档(请求链路内透传 + 无上下文兜底), 零中间件时序依赖"""
        _fake_redis(monkeypatch, ok=False)
        with caplog.at_level(logging.WARNING, logger="health"):
            client.get("/health/")
        records = _probe_log_records(caplog)
        assert len(records) == 1
        for ctx, expected in (("req-batch2-fixed", "req-batch2-fixed"), (None, "-")):
            _assert_structured_probe_log(records[0], ctx=ctx, expected=expected)

    def test_probe_logs_have_no_exc_info(self, client, monkeypatch, caplog):
        """B6: traceback 封死——record.exc_info 必须为 None(formatter 二次泄露面)"""
        _fake_redis(monkeypatch, ok=False)
        with patch("django.db.connection.cursor", side_effect=OperationalError(SECRET_FIXTURE)):
            with caplog.at_level(logging.WARNING, logger="health"):
                client.get("/ready/")
        records = _probe_log_records(caplog)
        assert len(records) == 2
        assert all(r.exc_info is None for r in records)

    def test_probe_socket_timeout_from_settings(self, client, monkeypatch):
        """B7: 超时取自配置(AR-4) + H2 AST 护栏(health_probe 顶层禁 import redis)"""
        module = _fake_redis(monkeypatch, ok=True)
        original = getattr(settings, "HEALTH_REDIS_SOCKET_TIMEOUT_SECONDS", None)
        monkeypatch.setattr(settings, "HEALTH_REDIS_SOCKET_TIMEOUT_SECONDS", 7, raising=False)
        client.get("/health/")
        assert module.Redis.from_url.call_args.kwargs["socket_timeout"] == 7
        monkeypatch.setattr(settings, "HEALTH_REDIS_SOCKET_TIMEOUT_SECONDS", original, raising=False)
        client.get("/health/")
        assert module.Redis.from_url.call_args.kwargs["socket_timeout"] == 3
        # H2 AST 护栏: health_probe.py 模块顶层不得 import redis(假模块注入依赖函数内 import)
        source = (Path(__file__).resolve().parents[2] / "core" / "health_probe.py").read_text(encoding="utf-8")
        for node in ast.parse(source).body:
            if isinstance(node, ast.Import):
                assert all(alias.name != "redis" for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "redis"

    def test_probe_retry_from_settings(self, client, monkeypatch, caplog):
        """B8: 重试次数取自配置 + H1 区间护栏(int 且 0 ≤ n ≤ 1) + n=-1 运行时兜底"""
        # H1 静态护栏: 配置存在、int、0 ≤ n ≤ 1(修复前以 getattr 兜住 AttributeError 面)
        n_retries = getattr(settings, "HEALTH_REDIS_MAX_RETRIES", None)
        assert isinstance(n_retries, int) and 0 <= n_retries <= 1
        module = _fake_redis(monkeypatch, ok=False)
        with caplog.at_level(logging.WARNING, logger="health"):
            client.get("/health/")
        assert module.Redis.from_url.call_count == 1
        assert len(_probe_log_records(caplog)) == 1
        monkeypatch.setattr(settings, "HEALTH_REDIS_MAX_RETRIES", 1, raising=False)
        module_retried = _fake_redis(monkeypatch, ok=False)
        client.get("/health/")
        assert module_retried.Redis.from_url.call_count == 2
        # n=-1 运行时兜底: max(0, n) → 仍 1 次探测 + 1 条 WARNING(防 range(0) 静默恒红)
        monkeypatch.setattr(settings, "HEALTH_REDIS_MAX_RETRIES", -1, raising=False)
        module_clamped = _fake_redis(monkeypatch, ok=False)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="health"):
            client.get("/health/")
        assert module_clamped.Redis.from_url.call_count == 1
        assert len(_probe_log_records(caplog)) == 1


class TestProbeDatabaseStatementTimeout:
    """[D-13①] probe_database statement_timeout 兜底: PG 注入 set_config, 非 PG 跳过"""

    def test_real_connection_probe_healthy(self, db):
        """真连接行为锚：probe_database healthy；PG 下注入 set_config，其他 vendor 跳过"""
        from django.db import connection

        from core.health_probe import probe_database

        with CaptureQueriesContext(connection) as ctx:
            assert probe_database() is True
        has_set_config = any("set_config" in q["sql"] for q in ctx.captured_queries)
        if connection.vendor == "postgresql":
            assert has_set_config
        else:
            assert not has_set_config

    def test_pg_vendor_injects_set_config(self, monkeypatch):
        """PG 分支: 执行 set_config('statement_timeout', ...) 且探针 healthy"""
        from unittest.mock import MagicMock

        from core import health_probe

        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.vendor = "postgresql"
        monkeypatch.setattr("django.db.connection", conn)
        monkeypatch.setattr(settings, "HEALTH_DB_STATEMENT_TIMEOUT_MS", 3000, raising=False)
        assert health_probe.probe_database() is True
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        assert any("set_config" in sql for sql in executed)

    def test_pg_zero_timeout_skips_set_config(self, monkeypatch):
        """HEALTH_DB_STATEMENT_TIMEOUT_MS=0: PG 下也跳过(显式关闭兜底)"""
        from unittest.mock import MagicMock

        from core import health_probe

        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        conn.vendor = "postgresql"
        monkeypatch.setattr("django.db.connection", conn)
        monkeypatch.setattr(settings, "HEALTH_DB_STATEMENT_TIMEOUT_MS", 0, raising=False)
        assert health_probe.probe_database() is True
        executed = [call.args[0] for call in cursor.execute.call_args_list]
        assert not any("set_config" in sql for sql in executed)
