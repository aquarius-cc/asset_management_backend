"""健康探测唯一实现(DR-1): DB / Redis 探测 + 脱敏失败日志(批次 2 / M-03+M-04)。

超时与重试次数取自 config/settings/base.py(AR-3/AR-4): 探针自身默认不重试
(HEALTH_REDIS_MAX_RETRIES=0, 行为与修复前一致); 重试判定由编排层承担
(docker-compose healthcheck retries=3 / interval=30s / timeout=10s)。
"""

import logging
import os

from django.conf import settings


logger = logging.getLogger("health")


def _log_failure(dependency: str, exc: Exception) -> None:
    # WARNING: health logger 未在 LOGGING["loggers"] 声明, effective level = root WARNING;
    # INFO/DEBUG 会被静默丢弃。禁 str(exc) / exc_info(formatter 会落异常与 traceback, OC-3/SC-1)。
    logger.warning(
        "health probe failed (dependency=%s, exception_type=%s)",
        dependency,
        type(exc).__name__,
    )


def probe_database() -> bool:
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            # [D-13①] 探针查询自身受 statement_timeout 会话级兜底（set_config 第三参 true
            # = 仅当前事务），防 DB 半死时探针挂死拖垮 healthcheck。
            # [D-13③] 空 REDIS_URL 时 probe_redis 必失败 → /health/ 探针 unhealthy
            # 属本地 fail-closed 预期（仅 runserver/pytest 场景，无编排层 env 注入），非缺陷。
            if connection.vendor == "postgresql" and settings.HEALTH_DB_STATEMENT_TIMEOUT_MS > 0:
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)", [str(settings.HEALTH_DB_STATEMENT_TIMEOUT_MS)]
                )
            cursor.execute("SELECT 1")
        return True
    except Exception as exc:
        _log_failure("database", exc)
        return False


def probe_redis() -> bool:
    # 函数内 import: test_health_ready.py 经 sys.modules 注入假 redis 模块,
    # 顶层 import 会让既有冒烟用例失效(H2 AST 护栏锁定, 并入 B7)。
    import redis

    redis_url = os.environ.get("REDIS_URL", "")
    total = max(0, settings.HEALTH_REDIS_MAX_RETRIES) + 1  # n<0 兜底: 至少探测 1 次并留 1 条日志
    for attempt in range(total):
        try:
            with redis.Redis.from_url(
                redis_url,
                socket_timeout=settings.HEALTH_REDIS_SOCKET_TIMEOUT_SECONDS,
            ) as conn:
                conn.ping()
            return True
        except Exception as exc:
            # 统一 except Exception: redis-py 6.2.0 异常不继承内建 ConnectionError(AR-1);
            # 探针幂等只读, 所有异常同样最多 total 次, 仅末次尝试记 1 条日志。
            if attempt == total - 1:
                _log_failure("redis", exc)
    return False
