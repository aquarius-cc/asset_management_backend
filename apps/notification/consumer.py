"""
WebSocket 通知消费者 (JWT 最小认证)

接收实时通知推送,支持:
- 按用户工号分组推送
- 连接认证(JWT Token via Sec-WebSocket-Protocol 头, H-1 修复)
- 心跳保活
"""

from typing import Any
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError

from apps.authusermanagement.models import AuthUser


logger = logging.getLogger(__name__)

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_FORBIDDEN = 4403


def _validate_token(raw_token: str) -> AuthUser:
    """用 SimpleJWT 校验 access token 并解析用户(复用 HTTP 认证链路, DR-1)"""
    auth = JWTAuthentication()
    validated = auth.get_validated_token(raw_token.encode("utf-8"))
    return auth.get_user(validated)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    通知 WebSocket 消费者 (JWT 最小认证)

    连接路径: /ws/notifications/<jobcode>/
    认证方式: Sec-WebSocket-Protocol 头携带 JWT (H-1)
    认证规则:
      - token 缺失/无效/过期/用户停用 -> 关闭 4401
      - token 身份 auth_username 与 URL jobcode 不一致 -> 关闭 4403(防冒充)
    推送格式: {"type": "notification", "data": {...}}
    心跳格式: {"type": "ping"} / {"type": "pong"}
    """

    async def connect(self):
        """建立连接(先认证, 通过后加入用户专属通知组)"""
        self.jobcode = self.scope["url_route"]["kwargs"]["jobcode"]
        self.group_name = f"notifications_{self.jobcode}"

        user = await self._authenticate()
        if user is None:
            await self.close(code=_CLOSE_UNAUTHORIZED)
            return
        if user.auth_username != self.jobcode:
            logger.warning("WS rejected: jobcode mismatch", extra={"ws_jobcode": self.jobcode})
            await self.close(code=_CLOSE_FORBIDDEN)
            return
        self.user = user

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send(
            text_data=json.dumps(
                {
                    "type": "connected",
                    "message": f"已连接通知频道: {self.jobcode}",
                }
            )
        )
        logger.info("WS connected", extra={"ws_jobcode": self.jobcode})

    async def _authenticate(self) -> AuthUser | None:
        """从 Sec-WebSocket-Protocol 头解析 token 并校验, 失败返回 None"""
        raw_token = self._extract_token()
        if not raw_token:
            logger.warning("WS rejected: missing token", extra={"ws_jobcode": self.jobcode})
            return None
        try:
            return await database_sync_to_async(_validate_token)(raw_token)
        except (TokenError, AuthenticationFailed):
            logger.warning("WS rejected: invalid token", extra={"ws_jobcode": self.jobcode})
            return None

    def _extract_token(self) -> str | None:
        """从 Sec-WebSocket-Protocol 头提取 JWT token (H-1 修复)"""
        headers = dict(self.scope.get("headers", []))
        protocol_raw = headers.get(b"sec-websocket-protocol", b"")
        if isinstance(protocol_raw, str):
            protocol_raw = protocol_raw.encode("utf-8")
        protocols = [p.strip().decode("utf-8") for p in protocol_raw.split(b",") if p.strip()]
        for p in protocols:
            if p.count(".") == 2 and len(p) > 20:
                return p
        return None

    async def disconnect(self, close_code):
        """断开连接"""
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

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
        处理通知组消息(由 channel_layer.group_send 触发)

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
        await self.send(
            text_data=json.dumps(
                {
                    "type": "notification",
                    "data": event["data"],
                }
            )
        )

    @database_sync_to_async
    def mark_notification_read(self, notification_id: Any) -> None:
        """标记通知为已读(仅限本 jobcode 的通知)"""
        from apps.notification.models import Notification

        Notification.objects.filter(
            id=notification_id,
            recipient_jobcode=self.jobcode,
        ).update(is_read=True)
