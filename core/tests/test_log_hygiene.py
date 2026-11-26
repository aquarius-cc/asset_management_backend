"""日志卫生结构门 v2（OC-3/BF-208 口径固化）

两个 AST 扫描器 + 允许清单守卫 + 自测 + 行为断言：
- 结构门：生产代码（排除 tests/migrations/docs/conftest/隐藏目录）中
  exc_info 关键字与 logger.exception 恰为 0（BF-208 收口后）。
- message 守卫：logger.*(f"{e}" / str(e) / 惰性 %s 裸异常名) 恰等于 EXC_MSG_ALLOWLIST
  （gap1 残留 3 处登记下批；修完清空清单，守卫转红提醒）。
- 自测：tmp_path 夹具固化扫描器形态判定与排除规则（含 P-1/P-2 防误红锚）。
- 行为：_safe_log / GenericAuditService 写失败路径 capture_exception_safe 恰一次、
  日志只留 exception_type、原文与 exc_info 不落盘。
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest import mock

import pytest
from django.db import transaction
from django.test import TestCase


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# 文件相对路径 → 允许的 message 级 str(exc) 出现次数（登记下批，修完清空）
EXC_MSG_ALLOWLIST: dict[str, int] = {
    "core/exception_handler.py": 1,  # :91  f"权限错误: {exc}"
    "apps/assetmanagement/services/operation_log_service.py": 1,  # :96  f"...失败: {e}"
    "core/throttles.py": 1,  # :34  惰性 "%s" + exc
    # BF-208 守卫落盘时新发现 2 处（方案基线外），同批登记下批修
    "docker/feishu-webhook/app.py": 1,  # :188 惰性 "%s" + err
    "apps/notification/services/notification_service.py": 1,  # :133 死信日志惰性 %s + e
}

_EXCLUDED_PARTS = frozenset({"tests", "migrations", "docs"})
_EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        "htmlcov",
        "node_modules",
        "asset_management_backend.egg-info",
    }
)
# 当前实测收敛集合（不含 error/exception/ex）；新增异常别名须同步扩充, 勿视为全量语义词表
_EXC_NAMES = frozenset({"e", "exc", "exc_val", "err"})
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})


def _should_skip(rel: str) -> bool:
    """排除 tests/migrations/docs/conftest 及 rglob 不读 .gitignore 的隐藏/缓存目录。"""
    parts = rel.split("/")
    if parts[-1] == "conftest.py":
        return True
    if any(p in _EXCLUDED_PARTS for p in parts):
        return True
    return any(p.startswith(".") or p in _EXCLUDED_DIRS for p in parts[:-1])


def _is_logger_receiver(node: ast.AST, logger_names: set[str]) -> bool:
    """logger / logging / self.logger / getLogger(...) 四形态（偏严，防回潮优先）。"""
    if isinstance(node, ast.Name):
        return node.id in logger_names | {"logger", "log", "logging"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"logger", "log"}
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Attribute) and node.func.attr == "getLogger"
    return False


def _logger_names_of(tree: ast.AST) -> set[str]:
    return {
        n.targets[0].id  # type: ignore[attr-defined]
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == "getLogger"
    }


def _collect_unsafe_log_sites(root: Path | None = None) -> dict[str, int]:
    """结构门：exc_info 关键字 + logger.exception 的 文件 → 计数（BF-208 后应为空）。"""
    root = root or _BACKEND_ROOT
    sites: dict[str, int] = {}
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        if _should_skip(rel):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8-sig"), filename=rel)
        logger_names = _logger_names_of(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if any(kw.arg == "exc_info" for kw in node.keywords):
                sites[rel] = sites.get(rel, 0) + 1
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _LOG_METHODS
                and _is_logger_receiver(node.func.value, logger_names)
                and node.func.attr == "exception"
            ):
                sites[rel] = sites.get(rel, 0) + 1
    return sites


def _has_exc_in_message(call: ast.Call) -> bool:
    """message 级 str(exc) 三形态判定（含 P-1 精度）。"""
    # 形态②：直接实参 str(e)/repr(e)
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id in {"str", "repr"}
            and len(arg.args) == 1
            and isinstance(arg.args[0], ast.Name)
            and arg.args[0].id in _EXC_NAMES
        ):
            return True
    # 形态①：f-string 内裸 Name∈集合（Call 内 Name 不命中）
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if isinstance(arg, ast.JoinedStr):
            for v in arg.values:
                if isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name) and v.value.id in _EXC_NAMES:
                    return True
    # 形态③：惰性 %s/%r + 顶层位置实参裸 Name∈集合（P-1：非集合名 idx/item_id 不命中）
    if (
        call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        and ("%s" in call.args[0].value or "%r" in call.args[0].value)
    ):
        for a in call.args[1:]:
            if isinstance(a, ast.Name) and a.id in _EXC_NAMES:
                return True
    return False


def _collect_message_leaks(root: Path | None = None) -> dict[str, int]:
    """message 守卫：logger.* 异常原文落 message 的 文件 → 计数。"""
    root = root or _BACKEND_ROOT
    sites: dict[str, int] = {}
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        if _should_skip(rel):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8-sig"), filename=rel)
        logger_names = _logger_names_of(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _LOG_METHODS
                and _is_logger_receiver(node.func.value, logger_names)
                and _has_exc_in_message(node)
            ):
                sites[rel] = sites.get(rel, 0) + 1
    return sites


def test_no_unsafe_log_sites() -> None:
    assert not _collect_unsafe_log_sites(), "OC-3 违规（exc_info/logger.exception）"


def test_message_leak_sites_match_allowlist() -> None:
    sites = _collect_message_leaks()
    unexpected = {f: n for f, n in sites.items() if f not in EXC_MSG_ALLOWLIST}
    assert not unexpected, f"允许清单外 message 级 str(exc): {unexpected}"
    for f, exp in EXC_MSG_ALLOWLIST.items():
        assert sites.get(f, 0) == exp, f"{f} 计数漂移: 期望 {exp} 实际 {sites.get(f, 0)}"
    assert sum(sites.values()) == sum(EXC_MSG_ALLOWLIST.values())


# ── scanner 自测（§7.4 夹具，固化形态判定与排除规则）─────────────────────────


def _write(tmp_path: Path, rel: str, body: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


_BAD_BODY = """import logging

logger = logging.getLogger(__name__)

def f(e, exc, err):
    logger.debug("d", exc_info=True)
    logger.info("i", exc_info=True)
    logger.warning("w", exc_info=True)
    logger.error("x", exc_info=True)
    logger.exception("boom")
    logger.error("命中1: %s", err)
    logger.error(f"命中2: {exc}")
    logger.error("命中3", str(e))
"""


def test_scanner_detects_both_shapes_and_exclusions(tmp_path):
    """夹具 A：bad.py 5 处结构命中（4×exc_info + 1×logger.exception），排除目录不漏检不误检。"""
    _write(tmp_path, "utils/bad.py", _BAD_BODY)
    for excluded in ("tests", "migrations", "docs"):
        _write(tmp_path, f"{excluded}/x.py", _BAD_BODY)
    _write(tmp_path, "conftest.py", _BAD_BODY)
    _write(tmp_path, ".venv/lib/x.py", _BAD_BODY)
    assert _collect_unsafe_log_sites(tmp_path) == {"utils/bad.py": 5}


def test_message_leak_scanner_precision(tmp_path):
    """夹具 B：P-1/P-2 防误红锚 + 形态② str/repr 命中锚。"""
    body = """import logging

logger = logging.getLogger(__name__)

def compliant(e, exc, idx, item_id, exception_type, error_response):
    logger.error("批量操作第 %s 条异常(exception_type=%s)", idx, exception_type(e))
    logger.error("...%s", item_id, exception_type(e))
    logger.error("...", exception_type(e))
    error_response(message=str(exc))

def violating(owner, e, exc):
    logger.warning("%s: ...%s", owner, exc)
    logger.error(f"失败: {e}")
    logger.error("失败", str(exc))
    logger.error("失败", repr(e))
"""
    _write(tmp_path, "utils/m.py", body)
    assert _collect_message_leaks(tmp_path) == {"utils/m.py": 4}


# ── 行为断言（§7.1，patch 消费模块名）────────────────────────────────────────


def _error_records(caplog: pytest.LogCaptureFixture, substr: str) -> list:
    return [r for r in caplog.records if substr in r.getMessage()]


class TestAuditSafeLogBehavior:
    """AuditLogger._safe_log 失败路径：capture 恰一次、零 exc_info、原文不落盘"""

    def test_safe_log_non_strict_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        import apps.assetmanagement.services  # noqa: F401  先触发包初始化，避免 audit↔services 循环导入
        from apps.assetmanagement.audit import AuditLogger
        from core.metrics import AUDIT_WRITE_FAILED

        counter = AUDIT_WRITE_FAILED.labels(channel="asset_operation_log")
        with (
            mock.patch("apps.assetmanagement.audit.capture_exception_safe") as spy,
            caplog.at_level(logging.ERROR),
        ):
            before = counter._value.get()
            result = AuditLogger._safe_log(mock.MagicMock(side_effect=RuntimeError("db down")))
            delta = counter._value.get() - before
        assert result is False
        assert spy.call_count == 1
        assert delta == 1
        records = _error_records(caplog, "日志记录失败")
        assert len(records) == 1
        record = records[0]
        assert record.exc_info is None
        assert "db down" not in record.getMessage()
        assert "exception_type=RuntimeError" in record.getMessage()

    def test_safe_log_strict_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        import apps.assetmanagement.services  # noqa: F401  先触发包初始化，避免 audit↔services 循环导入
        from apps.assetmanagement.audit import AuditLogger

        with (
            mock.patch("apps.assetmanagement.audit.capture_exception_safe") as spy,
            caplog.at_level(logging.ERROR),
        ):
            with pytest.raises(RuntimeError, match="db down"):
                AuditLogger._safe_log(mock.MagicMock(side_effect=RuntimeError("db down")), strict=True)
        assert spy.call_count == 0
        records = _error_records(caplog, "日志记录失败")
        assert len(records) == 1
        assert records[0].exc_info is None
        assert "db down" not in records[0].getMessage()


class TestGenericAuditServiceFailureBehavior:
    """GenericAuditService 写失败：capture 恰一次、日志含 exception_type、指标 +1"""

    @pytest.mark.django_db
    def test_write_failure_captured_once_and_no_exc_info(self, caplog: pytest.LogCaptureFixture) -> None:
        from core.audit_service import GenericAuditService
        from core.metrics import AUDIT_WRITE_FAILED

        counter = AUDIT_WRITE_FAILED.labels(channel="generic_audit_log")
        before = counter._value.get()
        with (
            mock.patch(
                "core.audit_service.AuditLog.objects.create",
                side_effect=RuntimeError("db down"),
            ),
            mock.patch("core.audit_service.capture_exception_safe") as spy,
            TestCase.captureOnCommitCallbacks(execute=True),
            transaction.atomic(),
            caplog.at_level(logging.ERROR),
        ):
            GenericAuditService.log_operation("RC_BF208", "app", "op", "desc")
        # on_commit 回调在 atomic 退出时执行, 指标增量须在 with 外读取
        delta = counter._value.get() - before
        assert spy.call_count == 1
        assert delta == 1
        records = _error_records(caplog, "通用审计日志记录失败")
        assert len(records) == 1
        record = records[0]
        assert record.exc_info is None
        assert "db down" not in record.getMessage()
        assert "exception_type=RuntimeError" in record.getMessage()
