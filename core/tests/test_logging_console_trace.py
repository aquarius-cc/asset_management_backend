"""M-23 回归护栏：console 通道 trace_id 接线与 formatter 耦合（OC-1/OC-2）.

分层结构：运行时断言读 settings fixture（受 --ds 影响）；AST 断言读源码文件
（不受共享 dict / 环境守卫影响，为权威判定层）。
"""

import ast
import json
import logging
from pathlib import Path

import pytest

from core.json_formatter import StructuredJSONFormatter
from core.logging_filters import TraceIDFilter


SETTINGS_DIR = Path(__file__).resolve().parents[2] / "config" / "settings"


@pytest.mark.parametrize(
    ("context_value", "expected"),
    [
        ("req-abc-123", "req-abc-123"),  # 请求链路内
        (None, "-"),  # 启动期 / 管理命令 / celery 等无请求上下文
    ],
)
def test_trace_id_field_always_present(monkeypatch, context_value, expected):
    """OC-2 字段完整性：有/无请求上下文，trace_id 都必须出现在格式化结果中"""
    monkeypatch.setattr("core.logging_filters.get_current_trace_id", lambda: context_value)
    record = logging.LogRecord(
        name="probe",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="启动期日志",
        args=(),
        exc_info=None,
    )
    assert TraceIDFilter().filter(record) is True
    assert record.trace_id == expected
    payload = json.loads(StructuredJSONFormatter().format(record))
    assert payload["trace_id"] == expected
    assert {"time", "level", "trace_id", "message", "module"} <= payload.keys()


def test_simple_formatter_requires_trace_filter(settings):
    """耦合护栏：simple 含 {trace_id} → 每个消费它的 handler 都必须挂 TraceIDFilter"""
    assert "{trace_id}" in settings.LOGGING["formatters"]["simple"]["format"]
    for name, handler in settings.LOGGING["handlers"].items():
        if handler.get("formatter") == "simple":
            assert "trace_id" in handler.get("filters", []), f"{name} 未挂 TraceIDFilter"


def test_base_console_is_single_source_of_trace_filter(settings):
    """base console 统一挂 filter（M-23 DR-1 收敛）；file 仍为 OC-2 权威 JSON 载体"""
    assert settings.LOGGING["handlers"]["console"]["filters"] == ["trace_id"]
    assert settings.LOGGING["handlers"]["file"]["formatter"] == "json"


def _console_overrides(path: Path) -> dict[str, object]:
    """从源码 AST 提取对 LOGGING['handlers']['console'][*] 的全部赋值（避开同进程 dict 污染）"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                key = ast.unparse(target)  # repr 风格：键一律单引号
                if "LOGGING['handlers']['console']" in key:
                    out[key] = ast.literal_eval(node.value)
    return out


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("development", {}),
        ("test", {"LOGGING['handlers']['console']['level']": "WARNING"}),
    ],
)
def test_nonprod_console_overrides(env, expected):
    """dev/test 不得再覆写 console 的 filters / formatter（未来新增 handler 覆写漂移即红）"""
    assert _console_overrides(SETTINGS_DIR / f"{env}.py") == expected


def test_production_console_keeps_json_only_override():
    """D4-A′ 精确快照：删 filters 覆写（下沉 base）、留 formatter=json；多一行/少一行即红"""
    assert _console_overrides(SETTINGS_DIR / "production.py") == {
        "LOGGING['handlers']['console']['level']": "INFO",
        "LOGGING['handlers']['console']['formatter']": "json",
    }


def _dict_entry(node: ast.Dict, key: str) -> ast.expr:
    """取 ast.Dict 中指定常量键的值节点；缺失即 KeyError。"""
    for k, v in zip(node.keys, node.values, strict=False):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    raise KeyError(key)


def _base_rest_framework_level(path: Path) -> object:
    """AST 提取模块级 LOGGING['loggers']['rest_framework']['level']。

    兼容 LOGGING = {...} 与 LOGGING: dict[...] = {...}（AnnAssign）；
    仅对 level 常量 literal_eval，避免 LOGGING 内 BASE_DIR/... BinOp 报错。
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    logging_node = next(
        (
            n.value
            for n in ast.walk(tree)
            if (
                (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "LOGGING")
                or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LOGGING" for t in n.targets))
            )
            and isinstance(n.value, ast.Dict)
        ),
        None,
    )
    assert isinstance(logging_node, ast.Dict), "LOGGING 字典字面量未找到"
    loggers = _dict_entry(logging_node, "loggers")
    rest = _dict_entry(loggers, "rest_framework")
    level = _dict_entry(rest, "level")
    return ast.literal_eval(level)


def test_base_rest_framework_logger_level_is_info():
    """M-HYG-06：base 默认不得为 DEBUG（生产产生低价值高频日志）；生产覆写 WARNING 更严"""
    assert _base_rest_framework_level(SETTINGS_DIR / "base.py") == "INFO"
