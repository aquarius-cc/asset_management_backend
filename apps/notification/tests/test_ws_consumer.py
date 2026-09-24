"""WebSocket 通知消费者测试(含 JWT 最小认证对抗性用例)

说明: 消费者内 database_sync_to_async 会触发 close_old_connections(见
channels/db.py), 与 pytest-django 默认事务包装在 PostgreSQL 上存在连接竞争,
故此处使用 transaction=True(autocommit) 并保证每个测试使用唯一用户名/手机号。
"""

import itertools
from datetime import timedelta
from unittest import mock

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import re_path
from rest_framework_simplejwt.tokens import AccessToken

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.services import AuthService
from apps.notification.consumer import NotificationConsumer
from apps.notification.models import Notification
from core.tests import TEST_PASSWORD


WS_URL_PATTERN = r"ws/notifications/(?P<jobcode>\w+)/$"


def _app():
    return URLRouter([re_path(WS_URL_PATTERN, NotificationConsumer.as_asgi())])


def _ws_url(jobcode: str) -> str:
    return f"/ws/notifications/{jobcode}/"


def _make_comm(jobcode: str, token: str | None = None) -> WebsocketCommunicator:
    """创建带 Sec-WebSocket-Protocol 头的 communicator"""
    headers = []
    if token:
        headers.append((b"sec-websocket-protocol", token.encode("utf-8")))
    return WebsocketCommunicator(_app(), _ws_url(jobcode), headers=headers)


async def _connect(comm: WebsocketCommunicator) -> dict:
    """发送握手, 返回握手响应(accept 或 close)"""
    await comm.send_input({"type": "websocket.connect"})
    return await comm.receive_output()


_phone_seq = itertools.count(1)


def _make_user(name: str) -> AuthUser:
    seq = next(_phone_seq)
    return AuthUser.objects.create_user(
        auth_username=name,
        password=TEST_PASSWORD,
        auth_phone=f"138{seq:08d}",
    )


def _issue_access(user) -> str:
    return AuthService.issue_tokens(user)["access"]


def _reject_code(token: str | None, jobcode: str) -> int:
    """在单个事件循环内验证连接被拒绝, 返回关闭码"""

    async def scenario():
        comm = _make_comm(jobcode, token)
        response = await _connect(comm)
        return response["type"], response.get("code")

    resp_type, code = async_to_sync(scenario)()
    assert resp_type == "websocket.close"
    return code


@pytest.mark.django_db(transaction=True)
class TestNotificationWSConnect:
    def test_connect_with_valid_token_accepts(self):
        user = _make_user("ws_conn_a")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_conn_a", token)
            response = await _connect(comm)
            if response["type"] != "websocket.accept":
                return response.get("code"), None
            first = await comm.receive_json_from()
            await comm.disconnect()
            return None, first

        code, first = async_to_sync(scenario)()
        assert code is None
        assert first["type"] == "connected"

    def test_connect_without_token_rejected(self):
        assert _reject_code(None, "ws_none_a") == 4401

    def test_connect_with_garbage_token_rejected(self):
        assert _reject_code("not-a-jwt", "ws_none_b") == 4401

    def test_connect_with_expired_token_rejected(self):
        user = _make_user("ws_expired_a")
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=-timedelta(minutes=1))
        assert _reject_code(str(token), "ws_expired_a") == 4401

    def test_connect_inactive_user_rejected(self):
        user = _make_user("ws_inactive_a")
        token = _issue_access(user)
        user.auth_is_active = False
        user.save(update_fields=["auth_is_active"])
        assert _reject_code(token, "ws_inactive_a") == 4401

    def test_connect_with_refresh_token_rejected(self):
        user = _make_user("ws_refresh_a")
        refresh = AuthService.issue_tokens(user)["refresh"]
        assert _reject_code(refresh, "ws_refresh_a") == 4401

    def test_connect_jobcode_mismatch_rejected(self):
        user = _make_user("ws_mismatch_a")
        assert _reject_code(_issue_access(user), "ws_other_a") == 4403


@pytest.mark.django_db(transaction=True)
class TestNotificationWSProtocol:
    def test_ping_returns_pong(self):
        user = _make_user("ws_proto_a")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_proto_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            await comm.send_json_to({"type": "ping"})
            pong = await comm.receive_json_from()
            await comm.disconnect()
            return pong

        assert async_to_sync(scenario)()["type"] == "pong"

    def test_malformed_json_ignored(self):
        user = _make_user("ws_proto_b")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_proto_b", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            await comm.send_to(text_data="{not-json")
            await comm.send_json_to({"type": "ping"})
            pong = await comm.receive_json_from()
            await comm.disconnect()
            return pong

        assert async_to_sync(scenario)()["type"] == "pong"

    def test_mark_read_scoped_to_own_jobcode(self):
        user = _make_user("ws_read_a")
        token = _issue_access(user)
        notif = Notification.objects.create(
            recipient_jobcode="ws_read_a",
            notification_type=Notification.NotificationType.APPROVAL,
            title="title",
            message="message",
        )

        async def scenario():
            comm = _make_comm("ws_read_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            await comm.send_json_to({"type": "mark_read", "notification_id": notif.id})
            await comm.disconnect()

        async_to_sync(scenario)()
        notif.refresh_from_db()
        assert notif.is_read is True

    def test_mark_read_foreign_notification_not_marked(self):
        _make_user("ws_read_owner")
        intruder = _make_user("ws_read_intruder")
        token = _issue_access(intruder)
        notif = Notification.objects.create(
            recipient_jobcode="ws_read_owner",
            notification_type=Notification.NotificationType.APPROVAL,
            title="title",
            message="message",
        )

        async def scenario():
            comm = _make_comm("ws_read_intruder", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            await comm.send_json_to({"type": "mark_read", "notification_id": notif.id})
            await comm.disconnect()

        async_to_sync(scenario)()
        notif.refresh_from_db()
        assert notif.is_read is False

    def test_receive_group_push(self):
        user = _make_user("ws_push_a")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_push_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                "notifications_ws_push_a",
                {
                    "type": "notification",
                    "data": {
                        "id": 1,
                        "type": "approval",
                        "title": "审批",
                        "message": "待审批",
                        "priority": "high",
                        "related_asset_code": "AST001",
                        "related_url": "/main/assetdetails/AST001",
                        "created_at": "2026-07-14T10:00:00Z",
                    },
                },
            )
            data = await comm.receive_json_from()
            await comm.disconnect()
            return data

        data = async_to_sync(scenario)()
        assert data["type"] == "notification"
        assert data["data"]["title"] == "审批"

    def test_group_push_isolation(self):
        user = _make_user("ws_push_iso_a")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_push_iso_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                "notifications_ws_push_iso_b",
                {"type": "notification", "data": {"id": 99, "title": "他组消息"}},
            )
            received_nothing = await comm.receive_nothing(timeout=0.3)
            await comm.send_json_to({"type": "ping"})
            pong = await comm.receive_json_from()
            await comm.disconnect()
            return received_nothing, pong

        received_nothing, pong = async_to_sync(scenario)()
        assert received_nothing is True
        assert pong["type"] == "pong"


@pytest.mark.django_db(transaction=True)
class TestNotificationWSThrottle:
    """R5-02: pong 节流与 mark_read 合并冲刷"""

    def test_pong_throttled_after_window_limit(self):
        """窗口内连发 ping 超过 PONG_MAX_PER_WINDOW 后, 超限部分静默丢弃(仅前 N 条收到 pong)"""
        user = _make_user("ws_throttle_a")
        token = _issue_access(user)

        async def scenario():
            comm = _make_comm("ws_throttle_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            total = 10  # > PONG_MAX_PER_WINDOW(5)
            for _ in range(total):
                await comm.send_json_to({"type": "ping"})
            # 仅前 5 条 ping 得到 pong(确定性收包, 避开 asgiref timeout 的 CancelledError 传播)
            for _ in range(5):
                msg = await comm.receive_json_from(timeout=1)
                assert msg["type"] == "pong"
            # 超限部分静默丢弃: 短暂等待后不应再有任何消息
            received_nothing = await comm.receive_nothing(timeout=0.3)
            await comm.disconnect()
            return received_nothing

        received_nothing = async_to_sync(scenario)()
        assert received_nothing is True

    def test_mark_read_merged_into_single_update(self):
        """同一窗口内多条 mark_read 合并为一次批量 UPDATE(计数断言单次调用, 且含全部 id)"""
        user = _make_user("ws_merge_a")
        token = _issue_access(user)
        notif_a = Notification.objects.create(
            recipient_jobcode="ws_merge_a",
            notification_type=Notification.NotificationType.APPROVAL,
            title="a",
            message="a",
        )
        notif_b = Notification.objects.create(
            recipient_jobcode="ws_merge_a",
            notification_type=Notification.NotificationType.APPROVAL,
            title="b",
            message="b",
        )

        async def scenario():
            comm = _make_comm("ws_merge_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            # 审核强化: 类级替换 _mark_notifications_read 计数调用,
            # 验证两条 id 合并为"单次批量写"而非逐条写
            with (
                mock.patch("apps.notification.consumer.MARK_READ_FLUSH_DELAY", 0.05),
                mock.patch.object(
                    NotificationConsumer, "_mark_notifications_read", new=mock.AsyncMock()
                ) as fake,
            ):
                await comm.send_json_to({"type": "mark_read", "notification_id": notif_a.id})
                await comm.send_json_to({"type": "mark_read", "notification_id": notif_b.id})
                await comm.disconnect()  # disconnect 先冲刷剩余待写
            return [list(c.args[0]) for c in fake.await_args_list]

        calls = async_to_sync(scenario)()
        # 两条 id 合并为一次调用(含 disconnect 冲刷, 不允许逐条写)
        assert len(calls) == 1
        assert set(calls[0]) == {notif_a.id, notif_b.id}

    def test_mark_read_flushed_on_immediate_disconnect(self):
        """发完 mark_read 立即 disconnect: 冲刷必须先于 group_discard, 已读仍生效(坑1 回归护栏)"""
        user = _make_user("ws_flush_a")
        token = _issue_access(user)
        notif = Notification.objects.create(
            recipient_jobcode="ws_flush_a",
            notification_type=Notification.NotificationType.APPROVAL,
            title="t",
            message="m",
        )

        async def scenario():
            comm = _make_comm("ws_flush_a", token)
            response = await _connect(comm)
            assert response["type"] == "websocket.accept"
            await comm.receive_json_from()
            await comm.send_json_to({"type": "mark_read", "notification_id": notif.id})
            await comm.disconnect()  # 不等待 0.5s 延迟, 直接断开

        async_to_sync(scenario)()
        notif.refresh_from_db()
        assert notif.is_read is True
