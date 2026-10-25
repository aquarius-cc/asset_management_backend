"""
通知服务

提供发送通知的统一入口,支持:
- 持久化存储(Notification 模型)
- WebSocket 实时推送(channel_layer.group_send)
- 同步版(供 Service 层调用)+ 异步版(供 Consumer 调用)
"""

import logging
from collections.abc import Sequence

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.db import transaction

from apps.notification.models import Notification


logger = logging.getLogger(__name__)


def push_notification_ws(notification: Notification) -> None:
    """推送单条已持久化通知到其收件人 WebSocket 群组。

    失败仅 warning 降级:通知已落库,用户刷新/重进仍可见,不构成数据丢失。
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError("channel layer 未配置")
        async_to_sync(channel_layer.group_send)(
            f"notifications_{notification.recipient_jobcode}",
            {
                "type": "notification",
                "data": {
                    "id": notification.id,
                    "type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message,
                    "priority": notification.priority,
                    "related_asset_code": notification.related_asset_code,
                    "related_url": notification.related_url,
                    "created_at": notification.created_at.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.warning(f"WebSocket 推送失败(通知已持久化): {e}")


def persist_notifications(
    recipients: Sequence[str],
    *,
    notification_type: str,
    title: str,
    message: str,
    priority: str = "medium",
    related_asset_code: str | None = None,
    related_url: str | None = None,
) -> list[Notification]:
    """
    批量持久化通知(BF-145/AUD-45): 一次 bulk_create,批失败降级逐条(单次重试),仍失败留死信日志。

    供 on_commit 回调(事务外)调用:内层 atomic 保证批写入原子;WS 推送由调用方
    对返回实例循环 push_notification_ws 承担,与持久化解耦。
    任何持久化失败不向调用方抛异常——通知丢失以 error 级死信日志(含完整重建载荷)兜底。
    """
    def _build(recipient_jobcode: str) -> Notification:
        return Notification(
            recipient_jobcode=recipient_jobcode,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            related_asset_code=related_asset_code,
            related_url=related_url,
        )

    try:
        with transaction.atomic():
            return list(Notification.objects.bulk_create([_build(r) for r in recipients]))
    except Exception as e:
        logger.warning(f"通知批量持久化失败,降级逐条写入: {e}")

    return _persist_individually(
        recipients,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        related_asset_code=related_asset_code,
        related_url=related_url,
    )


def _persist_individually(
    recipients: Sequence[str],
    *,
    notification_type: str,
    title: str,
    message: str,
    priority: str,
    related_asset_code: str | None,
    related_url: str | None,
) -> list[Notification]:
    """降级逐条写入(bulk 失败后调用): 单次重试应对瞬时 DB 抖动, 仍失败留 error 级死信日志。"""
    saved: list[Notification] = []
    for recipient_jobcode in recipients:
        for attempt in (1, 2):
            try:
                saved.append(
                    _create_notification(
                        recipient_jobcode=recipient_jobcode,
                        notification_type=notification_type,
                        title=title,
                        message=message,
                        priority=priority,
                        related_asset_code=related_asset_code,
                        related_url=related_url,
                    )
                )
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(
                        "通知持久化失败(死信,请人工补偿): recipient=%s type=%s title=%s "
                        "message=%s priority=%s related_asset_code=%s related_url=%s: %s",
                        recipient_jobcode,
                        notification_type,
                        title,
                        message,
                        priority,
                        related_asset_code,
                        related_url,
                        e,
                    )
    return saved


def _create_notification(
    recipient_jobcode: str,
    *,
    notification_type: str,
    title: str,
    message: str,
    priority: str,
    related_asset_code: str | None,
    related_url: str | None,
) -> Notification:
    """单条建库(降级路径专用, 内层 atomic): 失败由调用方捕获重试/死信。"""
    with transaction.atomic():
        return Notification.objects.create(
            recipient_jobcode=recipient_jobcode,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            related_asset_code=related_asset_code,
            related_url=related_url,
        )


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
    push_notification_ws(notification)
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
        if channel_layer is None:
            raise RuntimeError("channel layer 未配置")
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
    recipient_jobcode: str,
    notification_type: str,
    title: str,
    message: str,
    priority: str,
    related_asset_code: str | None,
    related_url: str | None,
) -> Notification:
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
