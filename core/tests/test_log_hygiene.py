"""日志卫生结构门（AST 扫描，OC-3/M-19「只记类型」口径固化）

断言生产代码（apps/ core/，排除 tests/ 与 migrations/）中
logger.*(..., exc_info=True) 恰为豁免白名单 3 处：
- apps/assetmanagement/audit.py ×2（调试上下文管理器 + _safe_log 容错契约，账本登记留痕）
- core/audit_service.py ×1（M-19 generic_audit_log 容错契约，账本登记留痕）

口径：文件集 + 每文件计数双断言（防行数碰巧相等回潮）；行号不锁（代码演进允许漂移）。
先红证据：结构门落盘时全仓命中 21 处，白名单仅 3 处 → 红；A5 批处置 18 处后转绿。
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest import mock

import pytest
from django.db import transaction
from django.test import TestCase

from core.error_reporting import capture_exception_safe


# 豁免白名单：文件相对路径 → 允许的 exc_info=True 出现次数
EXEMPT_FILE_COUNTS: dict[str, int] = {
    "apps/assetmanagement/audit.py": 2,
    "core/audit_service.py": 1,
}

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _collect_exc_info_sites() -> dict[str, int]:
    """AST 扫描生产代码，返回 文件相对路径 → exc_info=True 关键字出现次数。"""
    sites: dict[str, int] = {}
    for pkg in ("apps", "core"):
        for py in (_BACKEND_ROOT / pkg).rglob("*.py"):
            rel = py.relative_to(_BACKEND_ROOT).as_posix()
            # 测试与迁移不纳入（与 BR-6 口径一致）
            if "tests/" in rel or "/migrations/" in rel:
                continue
            tree = ast.parse(py.read_text(encoding="utf-8-sig"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "exc_info" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        sites[rel] = sites.get(rel, 0) + 1
    return sites


def test_exc_info_sites_match_exempt_whitelist() -> None:
    """结构门：exc_info=True 命中的文件集与计数恰等于豁免白名单"""
    sites = _collect_exc_info_sites()

    unexpected = {f: n for f, n in sites.items() if f not in EXEMPT_FILE_COUNTS}
    assert not unexpected, f"白名单外出现 exc_info=True（OC-3 口径违规）: {unexpected}"

    for exempt_file, expected in EXEMPT_FILE_COUNTS.items():
        actual = sites.get(exempt_file, 0)
        assert actual == expected, (
            f"{exempt_file} 豁免计数漂移: 期望 {expected}, 实际 {actual}（豁免属登记态契约，增删均须走台账留痕）"
        )

    # 总数收敛：不允许白名单文件出现未解释的多余命中
    total_exempt = sum(EXEMPT_FILE_COUNTS.values())
    assert sum(sites.values()) == total_exempt, f"exc_info=True 总命中 {sum(sites.values())} != 豁免总数 {total_exempt}"


class TestCaptureBehavior:
    """捕获出口行为断言：吞异常路径堆栈走 Sentry, 日志侧零 exc_info"""

    @pytest.mark.django_db
    def test_notification_failure_captured_once_and_no_exc_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """通知回调吞异常路径: capture_exception_safe 恰调用 1 次, 日志 record 无 exc_info"""
        from apps.notification.helpers import send_notification_on_commit
        from apps.notification.models import Notification

        mock_asset = mock.MagicMock()
        mock_asset.asset_code = "AST_CAP"
        with (
            mock.patch("apps.notification.helpers.notify_dept_managers", side_effect=RuntimeError("boom")),
            mock.patch("apps.notification.helpers.capture_exception_safe", wraps=capture_exception_safe) as spy,
            TestCase.captureOnCommitCallbacks(execute=True),
            transaction.atomic(),
        ):
            send_notification_on_commit(
                asset=mock_asset,
                notification_type=Notification.NotificationType.STATUS_CHANGE,
                title="t",
                message="m",
            )
        assert spy.call_count == 1

    def test_unhandled_exception_logged_without_exc_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """全局异常出口: 日志仅记类型, record.exc_info 必为 None, 原文不落盘"""
        from core.exception_handler import _handle_unhandled_exception

        with caplog.at_level(logging.ERROR):
            _handle_unhandled_exception(ValueError("sensitive-value"))
        records = [r for r in caplog.records if "未处理异常" in r.message]
        assert len(records) == 1
        record = records[0]
        assert record.exc_info is None
        assert record.getMessage() == "未处理异常(exception_type=ValueError)"
