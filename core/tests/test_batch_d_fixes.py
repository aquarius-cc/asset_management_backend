"""
批次 D 修复验证测试 (M-11 / M-13)

覆盖:
- M-11: change_asset_status 活跃待报废单锁内全出边拦截(见 test_asset_service.py)
- M-13: 审计写入 transaction.on_commit 延迟 + 失败不阻断主流程
"""

from unittest.mock import patch

from django.test import TestCase as DjangoTestCase

from core.audit_service import GenericAuditService
from core.models_audit import AuditLog


# ── M-13: GenericAuditService 审计写入延迟至提交后 ────────────────────────────


class TestM13GenericAuditOnCommit:
    """M-13: 通用审计日志 on_commit 延迟写入 + 失败吞并"""

    def test_log_create_deferred_until_commit(self, db):
        """事务内 log_create 不立即落库;on_commit 回调登记 1 个,恒返回 None

        注意: captureOnCommitCallbacks 在 with 块退出时(finally)才填充 callbacks,
        因此回调计数断言必须放在块外(Django 实现语义)。
        """
        with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
            result = GenericAuditService.log_create(record_code="M13-1", app_label="core", description="延迟写验证")
            assert AuditLog.objects.count() == 0
        assert len(callbacks) == 1
        assert result is None

    def test_log_create_executed_on_commit(self, db):
        """execute=True 在 with 块退出时执行回调,审计行落库(提交后语义)"""
        with DjangoTestCase.captureOnCommitCallbacks(execute=True):
            GenericAuditService.log_create(record_code="M13-2", app_label="core", description="提交后落库")
        assert AuditLog.objects.count() == 1

    def test_log_operation_failure_swallowed_and_logged(self, db, caplog):
        """审计写入异常不向调用方传播,logger.error 留痕,返回 None"""
        with patch.object(AuditLog.objects, "create", side_effect=RuntimeError("db down")):
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                result = GenericAuditService.log_operation(
                    record_code="M13-3",
                    app_label="core",
                    operation_type="create",
                    description="失败吞并验证",
                )
        assert result is None
        assert any("通用审计日志记录失败" in record.getMessage() for record in caplog.records)


# ── M-13: unregisteredasset 审计适配器 on_commit 延迟 ──────────────────────────


class TestM13SafeCallAuditOnCommit:
    """M-13: _safe_call_audit 适配器调用 on_commit 延迟 + 失败吞并"""

    @staticmethod
    def _call_audit() -> None:
        from apps.unregisteredasset.services import _safe_call_audit

        _safe_call_audit("create", unregistered=None, operator_jobcode="U001")

    def test_safe_call_audit_deferred_until_commit(self, db):
        """事务内适配器不立即调用;提交后回调执行时才调用(回调填充/执行均在 with 退出时)"""
        from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

        with patch.object(UnregisteredAssetAuditAdapter, "log_create") as mock_log:
            with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
                self._call_audit()
                mock_log.assert_not_called()
            assert len(callbacks) == 1
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                self._call_audit()
            mock_log.assert_called_once()

    def test_safe_call_audit_failure_swallowed(self, db):
        """适配器异常不向调用方传播(P2-10 语义在延迟路径下保持)"""
        from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

        with patch.object(UnregisteredAssetAuditAdapter, "log_create", side_effect=RuntimeError("boom")):
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                self._call_audit()
