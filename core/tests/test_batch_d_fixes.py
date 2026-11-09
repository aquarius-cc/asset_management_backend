"""
批次 D 修复验证测试 (M-11 / M-13 / M-08)

覆盖:
- M-11: change_asset_status 活跃待报废单锁内全出边拦截(见 test_asset_service.py)
- M-13: 审计写入 transaction.on_commit 延迟 + 失败不阻断主流程
- M-08: _safe_call_audit 外层调度失败分渠道计数(unregistered_safe_call),与内层
  unregistered_adapter 单次失败只计一处
"""

from unittest.mock import patch

from django.test import TestCase as DjangoTestCase
from prometheus_client import REGISTRY

from core.audit_service import GenericAuditService
from core.models_audit import AuditLog


METRIC = "asset_mgmt_audit_write_failed_total"


def _metric_value(channel: str) -> float | None:
    """指标取值范式与 test_audit_write_failure._metric_value 同源(prometheus REGISTRY 公开 API)"""
    return REGISTRY.get_sample_value(METRIC, {"channel": channel})


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
        """适配器异常不向调用方传播(P2-10 语义在延迟路径下保持)

        【M-08 指标注】本用例 patch 的是 UnregisteredAssetAuditAdapter.log_create 整个方法——
        模拟**包装层(调度)失败**,异常越过内层已计数场景直达外层 → unregistered_safe_call +1、
        unregistered_adapter +0;内层活吞点场景(适配器真实执行、OperationLogService 抛错)
        由 TestM08SafeCallAuditMetrics.test_inner_adapter_failure_counted_at_adapter 覆盖。
        """
        from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

        before_safe_call = _metric_value("unregistered_safe_call") or 0
        before_adapter = _metric_value("unregistered_adapter") or 0

        with patch.object(UnregisteredAssetAuditAdapter, "log_create", side_effect=RuntimeError("boom")):
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                self._call_audit()

        assert (_metric_value("unregistered_safe_call") or 0) == before_safe_call + 1
        assert (_metric_value("unregistered_adapter") or 0) == before_adapter


class TestM08SafeCallAuditMetrics:
    """M-08 阶段 A: 外层 _safe_call_audit 调度失败计 unregistered_safe_call;与内层无双计"""

    @staticmethod
    def _call_audit() -> None:
        from apps.unregisteredasset.services import _safe_call_audit

        _safe_call_audit("create", unregistered=None, operator_jobcode="U001")

    def test_inner_adapter_failure_counted_at_adapter(self, db):
        """内层活吞点: OperationLogService 抛错 → 内层 unregistered_adapter +1、外层 +0、主流程正常提交

        patch 的是适配器**内部**调用的 OperationLogService.log_operation——适配器真实执行,
        其宽 except inc 且不 re-raise,异常到不了外层(单次失败只计一处)。
        """
        from apps.assetmanagement.services.operation_log_service import OperationLogService

        before_safe_call = _metric_value("unregistered_safe_call") or 0
        before_adapter = _metric_value("unregistered_adapter") or 0

        with patch.object(OperationLogService, "log_operation", side_effect=RuntimeError("log db down")):
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                self._call_audit()

        assert (_metric_value("unregistered_adapter") or 0) == before_adapter + 1
        assert (_metric_value("unregistered_safe_call") or 0) == before_safe_call

    def test_dispatch_failure_counted_at_outer(self, db):
        """调度失败: getattr 取不到可调用的 log_<operation> → 外层 unregistered_safe_call +1、内层 +0

        patch 属性为非可调用对象,getattr(...)(...) 抛 TypeError——模拟延迟导入/取方法失败,
        适配器方法体从未进入,内层不计数。
        """
        from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

        before_safe_call = _metric_value("unregistered_safe_call") or 0
        before_adapter = _metric_value("unregistered_adapter") or 0

        with patch.object(UnregisteredAssetAuditAdapter, "log_create", "not-a-callable"):
            with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                self._call_audit()

        assert (_metric_value("unregistered_safe_call") or 0) == before_safe_call + 1
        assert (_metric_value("unregistered_adapter") or 0) == before_adapter
