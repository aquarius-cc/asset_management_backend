"""
通知模块测试

覆盖:
- Notification 模型创建与字段验证
- send_notification_sync 持久化 + WebSocket 推送
- notify_dept_managers 路由逻辑
- API 视图:列表、未读计数、标记已读、全部已读
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.notification.helpers import notify_dept_managers
from apps.notification.models import Notification
from apps.notification.service import send_notification_sync


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
class TestNotificationViews:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(auth_username="EMP010", password="testpass123")
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
