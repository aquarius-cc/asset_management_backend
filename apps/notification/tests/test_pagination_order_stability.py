# d:\CodeDemo\asset_management_backend\apps\notification\tests\test_pagination_order_stability.py
"""
通知列表分页稳定性回归 (AUD-46 / 批次 G1, M-02 同型残留)

Notification.Meta.ordering = ["-created_at"] (models.py:72) —— 无决胜键:
created_at 并列 (批量发送/同毫秒写入, BF-145 后批量落库更常见) 时跨页次序未定义,
PG 下 LIMIT/OFFSET 可能重复/丢行。

修复: Meta.ordering → ["-created_at", "-id"] (-id 为 PK 决胜键,
与 M-02 八模型 (-created_at,-id) / BF-128 同模式, 语义中性)。

每个断言三件套:
1. 不产生 UnorderedObjectListWarning
2. 两页 (page_size=2) 无重复、无丢行、覆盖全集
3. 返回序 == (-created_at, -id) 全序 (Python 侧独立计算)
外加 Meta 源断言 (先红锚)。
"""

import warnings
from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.paginator import UnorderedObjectListWarning
from rest_framework import status
from rest_framework.test import APIClient

from apps.notification.models import Notification
from core.tests import TEST_PASSWORD


LIST_URL = "/api/v1/notifications/"
FIXED_CREATED_AT = datetime(2026, 10, 25, 8, 0, 0, tzinfo=UTC)


@pytest.fixture
def user_client(db):
    """普通登录用户 (通知列表按 recipient_jobcode == auth_username 隔离)"""
    User = get_user_model()
    user = User.objects.create_user(auth_username="NOTIFY_PAG", password=TEST_PASSWORD)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def notifications_with_created_tie(db, user_client):
    """created_at 并列夹具: 4 行覆写为同一 created_at (决胜只能靠 -id)

    created_at 为 auto_now_add, save() 时忽略赋值 → 建后 update_fields 覆写。
    """
    for i in range(1, 5):
        n = Notification.objects.create(
            recipient_jobcode="NOTIFY_PAG",
            notification_type="system",
            title=f"分页夹具通知{i}",
            message=f"分页夹具消息{i}",
        )
        n.created_at = FIXED_CREATED_AT
        n.save(update_fields=["created_at"])


def _expected_ids(rows) -> list[int]:
    """按 (-created_at, -id) 全序给出期望 id 序列 (Python 侧独立计算)"""
    return [n.id for n in sorted(rows, key=lambda n: (n.created_at, n.id), reverse=True)]


def _fetch_two_pages(client: APIClient):
    """按 page=1/2 取两页 (page_size=2), 捕获 UnorderedObjectListWarning"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = client.get(LIST_URL, {"page_size": 2, "page": 1})
        second = client.get(LIST_URL, {"page_size": 2, "page": 2})
    unordered = [w for w in caught if issubclass(w.category, UnorderedObjectListWarning)]
    assert unordered == [], f"UnorderedObjectListWarning 未消除: {[str(w.message) for w in unordered]}"
    assert first.status_code == status.HTTP_200_OK, first.data
    assert second.status_code == status.HTTP_200_OK, second.data
    page1 = [item["id"] for item in first.data["data"]["results"]]
    page2 = [item["id"] for item in second.data["data"]["results"]]
    return page1, page2, first.data["data"]["count"]


def _assert_full_order(page1: list[int], page2: list[int], expected: list[int]) -> None:
    """两页覆盖全部期望行、无重复, 且顺序 == (-created_at, -id) 全序"""
    combined = page1 + page2
    assert len(set(combined)) == len(combined), f"翻页出现重复行: {combined}"
    assert combined == expected, f"分页序不符 (-created_at,-id): got={combined} expected={expected}"


class TestNotificationPaginationStability:
    """notification_list 分页稳定性 (AUD-46 / 批次 G1)"""

    def test_meta_ordering_has_id_tiebreak(self):
        """修复源断言: Meta.ordering 须含 -id 决胜键 (先红锚: 修复前为 ['-created_at'])"""
        assert tuple(Notification._meta.ordering) == ("-created_at", "-id")

    def test_list_two_pages_cover_all_in_order(self, user_client, notifications_with_created_tie):
        page1, page2, count = _fetch_two_pages(user_client)
        expected = _expected_ids(Notification.objects.filter(recipient_jobcode="NOTIFY_PAG"))
        assert count == len(expected), f"count 应等于全集: count={count} expected={expected}"
        assert len(page1 + page2) == count, f"两页未覆盖全集: {page1 + page2} vs count={count}"
        _assert_full_order(page1, page2, expected)
