"""
NotificationSerializer 测试
"""

import pytest

from apps.notification.models import Notification
from apps.notification.serializers import NotificationSerializer


@pytest.mark.django_db
class TestNotificationSerializer:
    """NotificationSerializer 测试"""

    def test_serialize_single_notification(self):
        """测试序列化单条通知"""
        notification = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="approval",
            title="测试通知",
            message="这是一条测试通知",
            priority="high",
            is_read=False,
            related_asset_code="A001",
            related_url="/assets/A001",
        )

        serializer = NotificationSerializer(notification)
        data = serializer.data

        assert data["id"] == notification.id
        assert data["type"] == "approval"
        assert data["title"] == "测试通知"
        assert data["message"] == "这是一条测试通知"
        assert data["priority"] == "high"
        assert data["is_read"] is False
        assert data["related_asset_code"] == "A001"
        assert data["related_url"] == "/assets/A001"
        assert "created_at" in data

    def test_serialize_many_notifications(self):
        """测试序列化多条通知"""
        notifications = [
            Notification.objects.create(
                recipient_jobcode="EMP001",
                notification_type="approval",
                title=f"通知 {i}",
                message=f"消息 {i}",
                priority="medium",
                is_read=False,
            )
            for i in range(3)
        ]

        serializer = NotificationSerializer(notifications, many=True)
        data = serializer.data

        assert len(data) == 3
        for i, item in enumerate(data):
            assert item["title"] == f"通知 {i}"
            assert item["type"] == "approval"

    def test_notification_type_mapping(self):
        """测试 notification_type 映射为 type"""
        notification = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="status_change",
            title="状态变更",
            message="资产状态已变更",
            priority="low",
        )

        serializer = NotificationSerializer(notification)
        data = serializer.data

        assert "type" in data
        assert "notification_type" not in data
        assert data["type"] == "status_change"

    def test_created_at_iso_format(self):
        """测试 created_at 使用 ISO 8601 格式"""
        notification = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="system",
            title="系统通知",
            message="系统维护通知",
            priority="medium",
        )

        serializer = NotificationSerializer(notification)
        data = serializer.data

        assert "created_at" in data
        # ISO 8601 格式包含 T 和 +
        assert "T" in data["created_at"]

    def test_read_only_fields(self):
        """测试所有字段为只读"""
        notification = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="approval",
            title="测试",
            message="消息",
        )

        serializer = NotificationSerializer(notification)
        # 所有字段都应在 Meta.read_only_fields 中
        assert serializer.Meta.read_only_fields == serializer.Meta.fields

    def test_null_optional_fields(self):
        """测试可选字段为 null"""
        notification = Notification.objects.create(
            recipient_jobcode="EMP001",
            notification_type="system",
            title="测试",
            message="消息",
            related_asset_code=None,
            related_url=None,
        )

        serializer = NotificationSerializer(notification)
        data = serializer.data

        assert data["related_asset_code"] is None
        assert data["related_url"] is None
