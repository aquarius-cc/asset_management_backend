"""M-19 审计写失败可观测性测试

_safe_log 失败即计 asset_mgmt_audit_write_failed_total(channel 维度); strict=True 时
写失败向上抛出由外层事务整体回滚。指标断言走 prometheus_client 公开 API REGISTRY。
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.db import transaction
from prometheus_client import REGISTRY


# [M-16] audit 不得冷直连导入(入口次序敏感环): 必须先经 operation_log_service 链完整
# 加载, 再取 AuditLogger; isort 字母序会重排回危险次序, 故锁定导入区。
# isort: off
from apps.assetmanagement.services.operation_log_service import OperationLogService  # noqa: F401
from apps.assetmanagement.audit import AuditLogger

# isort: on
from apps.assetmanagement.audit import audit_operation
from apps.authusermanagement.audit_adapter import AuthAuditAdapter
from apps.usermanagement.audit_helper import safe_audit_log
from core.audit_failure import record_audit_failure
from core.audit_service import GenericAuditService
from core.models_audit import AuditLog


METRIC = "asset_mgmt_audit_write_failed_total"


def _metric_value(channel: str) -> float | None:
    return REGISTRY.get_sample_value(METRIC, {"channel": channel})


def _boom() -> None:
    raise RuntimeError("db down")


class TestSafeLogMetric:
    def test_non_strict_returns_false_and_increments(self):
        before = _metric_value("asset_operation_log") or 0

        result = AuditLogger._safe_log(_boom)

        assert result is False
        after = _metric_value("asset_operation_log") or 0
        assert after == before + 1

    def test_strict_raises_original_exception(self):
        with pytest.raises(RuntimeError, match="db down"):
            AuditLogger._safe_log(_boom, strict=True)

    @pytest.mark.django_db
    def test_generic_audit_service_failure_counted_not_raised(self):
        """GenericAuditService 写入失败: channel=generic_audit_log 计数 +1 且不上抛(on_commit 容错不变)"""
        before = _metric_value("generic_audit_log") or 0
        # 批次 2 / M-01(A5): 真实写失败只计一处——不得再计调度层渠道(防双计, §3 约束 8)
        before_dispatch = _metric_value("generic_audit_dispatch") or 0

        from django.test import TestCase

        # monkeypatch 必须包住 captureOnCommitCallbacks: _write_audit 在 commit 时才执行,
        # patch 作用域若在 atomic 内部退出, 回调执行时已恢复原实现(假绿)
        with pytest.MonkeyPatch.context() as mp:

            def broken_create(*args: object, **kwargs: object) -> AuditLog:
                raise RuntimeError("audit db down")

            mp.setattr(AuditLog.objects, "create", broken_create)
            with TestCase.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    GenericAuditService.log_operation(
                        record_code="EMP-TEST",
                        app_label="employee",
                        operation_type="update",
                        description="M-19 指标测试",
                    )

        after = _metric_value("generic_audit_log") or 0
        assert after == before + 1
        assert (_metric_value("generic_audit_dispatch") or 0) == before_dispatch


class TestDispatchLayerObservability:
    """批次 2 / M-01+M-02: 调度层失败分渠道计数(单次失败只计一处, §3 约束 8)。

    调度层渠道可达性: 写库异常在 _write_audit(audit_service.py:54-72)与 _safe_log
    (audit.py:94-108)内已吞并计数、on_commit(robust=True) 不外抛, 故本组用例一律
    patch 调度层入口(mock 服务方法 / 闭包外装配), 禁止用 mock DB 写失败打外层(假绿)。
    """

    def test_decorator_dispatch_failure_counts_and_swallows(self, caplog):
        """A1: 装饰器调度失败 → asset_audit_decorator +1、asset_operation_log +0、主流程不抛"""
        before_dispatch = _metric_value("asset_audit_decorator") or 0
        before_oplog = _metric_value("asset_operation_log") or 0

        class _FakeAsset:
            asset_code = "AST-BATCH2"

        with (
            caplog.at_level(logging.ERROR, logger="audit.failure"),
            patch(
                "apps.assetmanagement.audit.AuditLogger.log_asset_create",
                side_effect=RuntimeError("dispatch boom"),
            ),
        ):

            @audit_operation("create")
            def _create():
                return _FakeAsset()

            result = _create()

        assert result.asset_code == "AST-BATCH2"
        assert (_metric_value("asset_audit_decorator") or 0) == before_dispatch + 1
        assert (_metric_value("asset_operation_log") or 0) == before_oplog
        assert any("context=审计装饰器调度失败" in r.getMessage() for r in caplog.records)

    def test_decorator_non_create_branch_is_silent(self, caplog):
        """A2: 非 create 分支无日志无指标(装饰器仅对 create+asset_code 装配审计)"""
        before = _metric_value("asset_audit_decorator") or 0

        @audit_operation("update")
        def _update():
            return object()

        result = _update()

        assert result is not None
        assert (_metric_value("asset_audit_decorator") or 0) == before
        assert not any(r.name == "audit.failure" for r in caplog.records)

    def test_auth_adapter_three_methods_route_to_dispatch_channel(self, caplog):
        """A3: 认证域三方法 → generic_audit_dispatch +1×3、generic_audit_log +0、context 带认证域前缀"""
        user = SimpleNamespace(auth_username="emp-001", email="a@b.c")
        before_dispatch = _metric_value("generic_audit_dispatch") or 0
        before_generic = _metric_value("generic_audit_log") or 0

        cases = [
            ("log_register", "core.audit_service.GenericAuditService.log_create", user),
            ("log_login", "core.audit_service.GenericAuditService.log_login", user),
            ("log_logout", "core.audit_service.GenericAuditService.log_operation", "emp-001"),
        ]

        with caplog.at_level(logging.ERROR, logger="audit.failure"):
            for method_name, patch_target, arg in cases:
                with patch(patch_target, side_effect=RuntimeError("db down")):
                    getattr(AuthAuditAdapter, method_name)(arg)

        assert (_metric_value("generic_audit_dispatch") or 0) == before_dispatch + 3
        assert (_metric_value("generic_audit_log") or 0) == before_generic
        ctx_logs = [r.getMessage() for r in caplog.records if "context=认证域-" in r.getMessage()]
        assert len(ctx_logs) == 3

    def test_safe_audit_log_thin_delegate_keeps_context(self, caplog):
        """A4: usermanagement 薄委托 → generic_audit_dispatch +1、error_context 文案保持"""
        before = _metric_value("generic_audit_dispatch") or 0

        with caplog.at_level(logging.ERROR, logger="audit.failure"):
            safe_audit_log(_boom, error_context="测试上下文")

        assert (_metric_value("generic_audit_dispatch") or 0) == before + 1
        assert any("context=测试上下文" in r.getMessage() for r in caplog.records)

    def test_metric_self_failure_does_not_break_caller(self, caplog):
        """A6: 指标自身失败 → 隔离不放大(主流程不抛)、留 ERROR 日志"""
        fake_counter = MagicMock()
        fake_counter.labels.return_value.inc.side_effect = ValueError("metric registry broken")

        with (
            caplog.at_level(logging.ERROR, logger="audit.failure"),
            patch("core.audit_failure.AUDIT_WRITE_FAILED", fake_counter),
        ):
            record_audit_failure(channel="probe", context="指标自毁", exc=RuntimeError("boom"))

        messages = [r.getMessage() for r in caplog.records]
        assert any("审计失败指标自增异常" in m for m in messages)
        assert any("context=指标自毁" in m for m in messages)
