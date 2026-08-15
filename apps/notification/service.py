"""
通知服务

提供发送通知的统一入口,支持:
- 持久化存储(Notification 模型)
- WebSocket 实时推送(channel_layer.group_send)
- 同步版(供 Service 层调用)+ 异步版(供 Consumer 调用)
"""

import logging

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer

from apps.notification.models import Notification


logger = logging.getLogger(__name__)


def send_notification_sync(
    recipient_jobcode: str,
    notification_type: str,
    title: str,
    message: str,
    priority: str = "medium",
    related_asset_code: str | None = None,
    related_url: str | None = None,
) -> Notification:
    """
    同步版发送通知(供 Service 层调用)

    在事务提交后调用,确保数据一致性。
    WebSocket 推送失败不影响业务。
    """
    notification = Notification.objects.create(
        recipient_jobcode=recipient_jobcode,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        related_asset_code=related_asset_code,
        related_url=related_url,
    )

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notifications_{recipient_jobcode}",
            {
                "type": "notification",
                "data": {
                    "id": notification.id,
                    "type": notification_type,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "related_asset_code": related_asset_code,
                    "related_url": related_url,
                    "created_at": notification.created_at.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.warning(f"WebSocket 推送失败(通知已持久化): {e}")

    return notification


async def send_notification(
    recipient_jobcode: str,
    notification_type: str,
    title: str,
    message: str,
    priority: str = "medium",
    related_asset_code: str | None = None,
    related_url: str | None = None,
) -> Notification:
    """
    异步版发送通知(供 Consumer 等异步上下文调用)
    """
    notification = await database_create_notification(
        recipient_jobcode=recipient_jobcode,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        related_asset_code=related_asset_code,
        related_url=related_url,
    )

    try:
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"notifications_{recipient_jobcode}",
            {
                "type": "notification",
                "data": {
                    "id": notification.id,
                    "type": notification_type,
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "related_asset_code": related_asset_code,
                    "related_url": related_url,
                    "created_at": notification.created_at.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.warning(f"WebSocket 推送失败(通知已持久化): {e}")

    return notification


@database_sync_to_async
def database_create_notification(
    recipient_jobcode,
    notification_type,
    title,
    message,
    priority,
    related_asset_code,
    related_url,
):
    """持久化通知到数据库"""
    return Notification.objects.create(
        recipient_jobcode=recipient_jobcode,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        related_asset_code=related_asset_code,
        related_url=related_url,
    )
