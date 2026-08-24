"""
通知序列化器,提供 Notification 模型的序列化功能

类:
  - NotificationSerializer: 通知序列化器(将 notification_type 映射为 type)

调用链:
  本模块被 views.py 依赖
  本模块依赖 models.Notification
"""

from rest_framework import serializers

from apps.notification.models import Notification


class NotificationSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    通知序列化器

    用于通知列表的序列化,将 notification_type 映射为 type,
    并确保 created_at 使用 ISO 8601 格式。
    """

    type = serializers.CharField(source="notification_type", read_only=True)
    created_at = serializers.DateTimeField(format="iso-8601", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "title",
            "message",
            "priority",
            "is_read",
            "related_asset_code",
            "related_url",
            "created_at",
        ]
        read_only_fields = fields
