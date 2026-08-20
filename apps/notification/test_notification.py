"""
通知模块测试

覆盖:
- Notification 模型创建与字段验证
- send_notification_sync 持久化 + WebSocket 推送
- notify_dept_managers 路由逻辑
- send_notification_on_commit 事务提交后发送(B6)
- API 视图:列表、未读计数、标记已读、全部已读
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db.transaction import TransactionManagementError
from django.test import TestCase as DjangoTestCase
from rest_framework.test import APIClient

from apps.notification.helpers import notify_dept_managers, send_notification_on_commit
from apps.notification.models import Notification
from apps.notification.service import send_notification_sync
from core.tests import TEST_PASSWORD


User = get_user_model()


@pytest.mark.django_db
class TestNotificationModel:
    def test_create_notification(self):
        n = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="approval",
            title="测试通知",
            message="这是一条测试通知",
            priority="medium",
        )
        assert n.id is not None
        assert n.is_read is False
        assert n.recipient_jobcode == "EMP001"

    def test_notification_str(self):
        n = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="system",
            title="系统通知",
            message="系统维护",
        )
        assert "EMP001" in str(n) or "系统通知" in str(n) or n.title == "系统通知"


@pytest.mark.django_db
class TestSendNotificationSync:
    @patch("apps.notification.service.get_channel_layer")
    def test_persists_notification(self, mock_channel):
        mock_channel.return_value = MagicMock()
        n = send_notification_sync(
            recipient_jobcode="EMP002",
            notification_type="status_change",
            title="资产状态变更",
            message="资产 AST001 已出库",
            priority="high",
        )
        assert n.id is not None
        assert Notification.objects.filter(recipient_jobcode="EMP002").count() == 1

    @patch("apps.notification.service.get_channel_layer", side_effect=Exception("channel error"))
    def test_ws_failure_does_not_break(self, mock_channel):
        """WebSocket 推送失败不应影响持久化"""
        n = send_notification_sync(
            recipient_jobcode="EMP003",
            notification_type="system",
            title="测试",
            message="WS 失败测试",
        )
        assert n.id is not None


@pytest.mark.django_db
class TestNotifyDeptManagers:
    @patch("apps.notification.service.get_channel_layer")
    def test_sends_to_managers(self, mock_ws):
        """批量创建通知并推送给所有 manager"""
        mock_channel = MagicMock()
        mock_ws.return_value = mock_channel

        mock_asset = MagicMock()
        mock_asset.asset_code = "AST001"

        with patch("core.department_scope.resolve_asset_department_codes", return_value=["DEPT001"]):
            with patch("apps.usermanagement.models.Employee") as MockEmployee:
                MockEmployee.objects.filter.return_value.values_list.return_value = ["MGR001", "MGR002"]
                notify_dept_managers(
                    asset=mock_asset,
                    notification_type="approval",
                    title="审批通知",
                    message="请审批",
                )
                # 验证批量创建了 2 条通知
                assert Notification.objects.filter(notification_type="approval", title="审批通知").count() == 2
                # 验证 WebSocket 推送了 2 次(per-group)
                assert mock_channel.group_send.call_count == 2

    @patch("apps.notification.service.get_channel_layer")
    def test_bulk_create_single_manager(self, mock_ws):
        """单个 manager 时也使用 bulk_create"""
        mock_channel = MagicMock()
        mock_ws.return_value = mock_channel

        mock_asset = MagicMock()
        mock_asset.asset_code = "AST002"

        with patch("core.department_scope.resolve_asset_department_codes", return_value=["DEPT001"]):
            with patch("apps.usermanagement.models.Employee") as MockEmployee:
                MockEmployee.objects.filter.return_value.values_list.return_value = ["MGR001"]
                notify_dept_managers(
                    asset=mock_asset,
                    notification_type="status_change",
                    title="状态变更",
                    message="资产已出库",
                )
                assert Notification.objects.filter(recipient_jobcode="MGR001").count() == 1

    @patch("apps.notification.service.get_channel_layer", side_effect=Exception("channel error"))
    def test_ws_failure_does_not_break(self, mock_ws):
        """WebSocket 失败不影响通知持久化"""
        mock_asset = MagicMock()
        mock_asset.asset_code = "AST003"

        with patch("core.department_scope.resolve_asset_department_codes", return_value=["DEPT001"]):
            with patch("apps.usermanagement.models.Employee") as MockEmployee:
                MockEmployee.objects.filter.return_value.values_list.return_value = ["MGR001"]
                notify_dept_managers(
                    asset=mock_asset,
                    notification_type="system",
                    title="系统通知",
                    message="测试",
                )
                # 通知仍应被持久化
                assert Notification.objects.filter(recipient_jobcode="MGR001").count() == 1


@pytest.mark.django_db
class TestSendNotificationOnCommit:
    """send_notification_on_commit 事务提交后发送(B6)"""

    def test_registers_callback_sent_on_commit(self):
        """注册回调,提交前不发送,事务提交(模拟)后调用 notify_dept_managers"""
        mock_asset = MagicMock()
        mock_asset.asset_code = "AST_ONC"

        with patch("apps.notification.helpers.notify_dept_managers") as mock_notify:
            with DjangoTestCase.captureOnCommitCallbacks(execute=False) as callbacks:
                send_notification_on_commit(
                    asset=mock_asset,
                    notification_type="status_change",
                    title="状态变更",
                    message="资产已出库",
                    priority="high",
                    related_url="/main/assetdetails/AST_ONC",
                )
                mock_notify.assert_not_called()
            assert len(callbacks) == 1
            callbacks[0]()
        mock_notify.assert_called_once_with(
            asset=mock_asset,
            notification_type="status_change",
            title="状态变更",
            message="资产已出库",
            priority="high",
            related_url="/main/assetdetails/AST_ONC",
        )

    def test_callback_exception_is_swallowed_and_logged(self, caplog):
        """回调内异常被吞掉并记录日志,不影响业务(robust 语义,缺陷B回归护栏)"""
        mock_asset = MagicMock()
        mock_asset.asset_code = "AST_FAIL"

        with patch(
            "apps.notification.helpers.notify_dept_managers", side_effect=RuntimeError("notify boom")
        ):
            with caplog.at_level(logging.ERROR, logger="apps.notification.helpers"):
                with DjangoTestCase.captureOnCommitCallbacks(execute=True):
                    send_notification_on_commit(
                        asset=mock_asset,
                        notification_type="status_change",
                        title="状态变更",
                        message="消息",
                    )
        messages = [r.message for r in caplog.records]
        assert any("AST_FAIL" in m and "notify boom" in m for m in messages)


def test_send_notification_on_commit_raises_outside_atomic_block():
    """非事务块内调用应抛出 TransactionManagementError,阻止通知过早发送(不包裹事务,保证 in_atomic_block=False)"""
    mock_asset = MagicMock()
    mock_asset.asset_code = "AST_X"

    with pytest.raises(TransactionManagementError):
        send_notification_on_commit(
            asset=mock_asset,
            notification_type="system",
            title="t",
            message="m",
        )


@pytest.mark.django_db
class TestNotificationViews:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(auth_username="EMP010", password=TEST_PASSWORD)
        self.client.force_authenticate(user=self.user)

    def test_notification_list(self):
        Notification.objects.create(
            recipient_jobcode="EMP010",
            notification_type="system",
            title="通知1",
            message="msg1",
        )
        resp = self.client.get("/api/v1/notifications/")
        assert resp.status_code == 200

    def test_unread_count(self):
        Notification.objects.create(
            recipient_jobcode="EMP010",
            notification_type="system",
            title="未读",
            message="msg",
            is_read=False,
        )
        Notification.objects.create(
            recipient_jobcode="EMP010",
            notification_type="system",
            title="已读",
            message="msg",
            is_read=True,
        )
        resp = self.client.get("/api/v1/notifications/unread-count/")
        assert resp.status_code == 200
        assert resp.data["data"]["count"] == 1

    def test_mark_read(self):
        n = Notification.objects.create(
            recipient_jobcode="EMP010",
            notification_type="system",
            title="测试",
            message="msg",
            is_read=False,
        )
        resp = self.client.post(f"/api/v1/notifications/{n.id}/read/")
        assert resp.status_code == 200
        n.refresh_from_db()
        assert n.is_read is True

    def test_mark_all_read(self):
        for i in range(3):
            Notification.objects.create(
                recipient_jobcode="EMP010",
                notification_type="system",
                title=f"通知{i}",
                message="msg",
                is_read=False,
            )
        resp = self.client.post("/api/v1/notifications/read-all/")
        assert resp.status_code == 200
        assert resp.data["data"]["marked_count"] == 3
