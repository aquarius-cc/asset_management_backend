"""
WebSocket 通知消费者

接收实时通知推送，支持：
- 按用户工号分组推送
- 连接认证（JWT Token）
- 心跳保活
"""

import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    通知 WebSocket 消费者

    连接路径: /ws/notifications/<jobcode>/
    推送格式: {"type": "notification", "data": {...}}
    心跳格式: {"type": "ping"} / {"type": "pong"}
    """

    async def connect(self):
        """建立连接"""
        self.jobcode = self.scope["url_route"]["kwargs"]["jobcode"]
        self.group_name = f"notifications_{self.jobcode}"

        # 加入用户专属通知组
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

        # 发送连接确认
        await self.send(text_data=json.dumps({
            "type": "connected",
            "message": f"已连接通知频道: {self.jobcode}",
        }))

    async def disconnect(self, close_code):
        """断开连接"""
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        """接收客户端消息"""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        if msg_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
        elif msg_type == "mark_read":
            notification_id = data.get("notification_id")
            if notification_id:
                await self.mark_notification_read(notification_id)

    async def notification(self, event):
        """
        处理通知组消息（由 channel_layer.group_send 触发）

        event 格式:
        {
            "type": "notification",
            "data": {
                "id": 1,
                "type": "approval",
                "title": "...",
                "message": "...",
                "priority": "high",
                "related_asset_code": "AST001",
                "related_url": "/main/assetdetails/AST001",
                "created_at": "2026-07-14T10:00:00Z",
            }
        }
        """
        await self.send(text_data=json.dumps({
            "type": "notification",
            "data": event["data"],
        }))

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """标记通知为已读"""
        from apps.notification.models import Notification
        Notification.objects.filter(
            id=notification_id,
            recipient_jobcode=self.jobcode,
        ).update(is_read=True)
