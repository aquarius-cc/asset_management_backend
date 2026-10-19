"""
通知服务包(对齐 assetmanagement 结构)

对外统一入口:  send_notification_sync / send_notification / database_create_notification
"""

from apps.notification.services.notification_service import (
    database_create_notification,
    send_notification,
    send_notification_sync,
)


__all__ = [
    "database_create_notification",
    "send_notification",
    "send_notification_sync",
]
