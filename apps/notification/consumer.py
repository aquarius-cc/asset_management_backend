"""
WebSocket 通知消费者 (JWT 最小认证)

接收实时通知推送,支持:
- 按用户工号分组推送
- 连接认证(JWT Token via Sec-WebSocket-Protocol 头, H-1 修复)
- 心跳保活
"""

import asyncio
import json
import logging
import time
from typing import Any, cast

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError

from apps.authusermanagement.models import AuthUser


logger = logging.getLogger(__name__)

_CLOSE_UNAUTHORIZED = 4401
_CLOSE_FORBIDDEN = 4403

# 【R5-02 节流】每连接 pong 固定窗口限流(前端心跳 30s/次, 远低于此阈值)
PONG_MAX_PER_WINDOW = 5
PONG_WINDOW_SECONDS = 10.0
# 【R5-02 消息合并】mark_read 延迟冲刷(0.5s 内合并为一次批量 UPDATE)
MARK_READ_FLUSH_DELAY = 0.5
MARK_READ_MAX_PENDING = 200  # 待写集合上限, 超限立即冲刷防膨胀


def _validate_token(raw_token: str) -> AuthUser:
    """用 SimpleJWT 校验 access token 并解析用户(复用 HTTP 认证链路, DR-1)"""
    auth = JWTAuthentication()
    validated = auth.get_validated_token(raw_token.encode("utf-8"))
    return cast(AuthUser, auth.get_user(validated))


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

    async def connect(self) -> None:
        """建立连接(先认证, 通过后加入用户专属通知组)"""
        self.jobcode = self.scope["url_route"]["kwargs"]["jobcode"]
        self.group_name = f"notifications_{self.jobcode}"

        # 【R5-02 节流/合并】连接级状态: pong 固定窗口计数 + mark_read 合并缓冲
        self._pong_window_start = 0.0
        self._pong_count = 0
        self._pending_mark_read: set[Any] = set()
        self._flush_task: asyncio.Task[Any] | None = None

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
        # 【BF-002 修复】前端以 subprotocol 方式传入 JWT(useNotification.ts), RFC 6455
        # 要求服务器握手响应必须回显所选子协议, 否则浏览器直接掐断连接。
        # 此处回显认证通过的 token 本身; 未通过认证的连接已在上方 close() 返回。
        await self.accept(subprotocol=self._extract_token())

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
            return await database_sync_to_async(_validate_token)(raw_token)  # type: ignore[no-any-return]
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
                return p  # type: ignore[no-any-return]
        return None

    async def disconnect(self, close_code: int) -> None:
        """断开连接(先冲刷待写 mark_read, 再收尾定时任务与组员身份)"""
        # 【F3 兜底】flush 失败不得阻断 group_discard, 否则 channel 永久泄漏在组内
        try:
            await self._flush_pending_mark_read()
        except Exception:
            logger.exception("WS disconnect flush failed", extra={"ws_jobcode": self.jobcode})
        # 【F2 竞态】不直接 cancel 在途 flush(可能掐死已弹出待写的 DB 写):
        # shield 等待其完成, 仅卡死(>2s)时才取消; 被 cancel 掐掉的 id 已由回灌兜底
        task = self._flush_task
        self._flush_task = None
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("WS in-flight flush failed", extra={"ws_jobcode": self.jobcode})
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data: str) -> None:
        """接收客户端消息(ping 节流限流, mark_read 合并批量写, R5-02)"""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        if msg_type == "ping":
            await self._send_pong_throttled()
        elif msg_type == "mark_read":
            notification_id = data.get("notification_id")
            # 【F6 类型校验】仅接受整数 id: 非可哈希值(list/dict)入集合会 TypeError 拆连接
            if isinstance(notification_id, int) and not isinstance(notification_id, bool):
                self._pending_mark_read.add(notification_id)
                # 超限立即冲刷, 防待写集合无限膨胀
                if len(self._pending_mark_read) >= MARK_READ_MAX_PENDING:
                    await self._flush_pending_mark_read()
                elif self._flush_task is None or self._flush_task.done():
                    self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _send_pong_throttled(self) -> None:
        """固定窗口限流回 pong: 窗口内超过 PONG_MAX_PER_WINDOW 则静默丢弃(客户端无 pong 依赖)"""
        now = time.monotonic()
        if now - self._pong_window_start >= PONG_WINDOW_SECONDS:
            self._pong_window_start = now
            self._pong_count = 0
        if self._pong_count >= PONG_MAX_PER_WINDOW:
            return
        self._pong_count += 1
        await self.send(text_data=json.dumps({"type": "pong"}))

    async def _delayed_flush(self) -> None:
        """延迟冲刷循环: 直到待写集合取空(【F1】防 DB await 间隙新入集合的 id 滞留不冲刷)"""
        while True:
            await asyncio.sleep(MARK_READ_FLUSH_DELAY)
            if not self._pending_mark_read:
                return
            try:
                await self._flush_pending_mark_read()
            except asyncio.CancelledError:
                raise
            except Exception:
                # ids 已回灌进 pending, 下一轮循环重试
                logger.exception("WS mark_read flush failed", extra={"ws_jobcode": self.jobcode})

    async def _flush_pending_mark_read(self) -> None:
        """取空待写集合并批量 UPDATE(保留 recipient_jobcode 作用域过滤, 越权防护不回退)"""
        if not self._pending_mark_read:
            return
        ids = list(self._pending_mark_read)
        self._pending_mark_read.clear()
        try:
            await self._mark_notifications_read(ids)
        except BaseException:
            # 【F4 回灌】写失败(含被 cancel)时把 id 并回待写集合, 防已弹出数据丢失
            self._pending_mark_read |= set(ids)
            raise

    @database_sync_to_async
    def _mark_notifications_read(self, notification_ids: list[Any]) -> None:
        """批量标记通知为已读(仅限本 jobcode 的通知)"""
        from apps.notification.models import Notification

        Notification.objects.filter(
            id__in=notification_ids,
            recipient_jobcode=self.jobcode,
        ).update(is_read=True)

    async def notification(self, event: dict[str, Any]) -> None:
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
