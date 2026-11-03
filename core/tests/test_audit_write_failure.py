"""M-19 审计写失败可观测性测试

_safe_log 失败即计 asset_mgmt_audit_write_failed_total(channel 维度); strict=True 时
写失败向上抛出由外层事务整体回滚。指标断言走 prometheus_client 公开 API REGISTRY。
"""

import pytest
from django.db import transaction
from prometheus_client import REGISTRY


# [M-16] audit 不得冷直连导入(入口次序敏感环): 必须先经 operation_log_service 链完整
# 加载, 再取 AuditLogger; isort 字母序会重排回危险次序, 故锁定导入区。
# isort: off
from apps.assetmanagement.services.operation_log_service import OperationLogService  # noqa: F401
from apps.assetmanagement.audit import AuditLogger

# isort: on
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
