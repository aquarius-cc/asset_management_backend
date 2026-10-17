"""
notification_list 分页与过滤测试(P1-02 重构 / BF-095 → BF-097)

覆盖:
- 分页信封结构(data 为 7 键对象而非裸数组, 单层信封, 防二次包装回归)
- 默认分页 20 / page 参数 / page_size 参数 / >100 钳制 / 非法页码 404
- limit 参数已随 P1-02 移除: 传入被忽略, 恒走 page/page_size 分页
- is_read / notification_type / priority / keyword 过滤
- 跨用户隔离与未登录 401

历史: 原 3 个 M-1 limit 用例(BF-095)随 limit 参数移除作废, 由本文件取代。
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.notification.models import Notification
from core.tests import TEST_PASSWORD


User = get_user_model()

ENDPOINT = "/api/v1/notifications/"
PAGINATION_KEYS = {"count", "total_pages", "page", "page_size", "next", "previous", "results"}


def _create_notifications(jobcode: str, count: int, **overrides: object) -> None:
    defaults: dict[str, object] = {"notification_type": "system", "message": "msg"}
    defaults.update(overrides)
    Notification.objects.bulk_create(
        Notification(
            recipient_jobcode=jobcode,
            title=f"通知{i}",
            **defaults,  # type: ignore[arg-type]
        )
        for i in range(count)
    )


@pytest.mark.django_db
class TestNotificationListPagination:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(auth_username="EMP020", password=TEST_PASSWORD)
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_returns_401(self):
        """未登录访问 → 401(既有 IsAuthenticated 行为保持不变)"""
        client = APIClient()
        resp = client.get(ENDPOINT)
        assert resp.status_code == 401

    def test_response_data_is_paginated_envelope(self):
        """data 为 7 键分页对象而非裸数组(防回退裸数组回归)"""
        _create_notifications("EMP020", 3)
        resp = self.client.get(ENDPOINT)
        assert resp.status_code == 200
        assert isinstance(resp.data["data"], dict)
        assert set(resp.data["data"].keys()) == PAGINATION_KEYS

    def test_default_pagination_returns_20_of_30(self):
        """无参 → 第 1 页 20 条, count=30, total_pages=2"""
        _create_notifications("EMP020", 30)
        resp = self.client.get(ENDPOINT)
        data = resp.data["data"]
        assert resp.status_code == 200
        assert data["count"] == 30
        assert len(data["results"]) == 20
        assert data["total_pages"] == 2
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_second_page_returns_remainder(self):
        """page=2 → 剩余 10 条"""
        _create_notifications("EMP020", 30)
        resp = self.client.get(ENDPOINT, {"page": 2})
        data = resp.data["data"]
        assert resp.status_code == 200
        assert data["page"] == 2
        assert len(data["results"]) == 10

    def test_page_size_param_effective(self):
        """page_size=5 → 每页 5 条, total_pages=6"""
        _create_notifications("EMP020", 30)
        resp = self.client.get(ENDPOINT, {"page_size": 5})
        data = resp.data["data"]
        assert resp.status_code == 200
        assert data["page_size"] == 5
        assert len(data["results"]) == 5
        assert data["total_pages"] == 6

    def test_page_size_clamped_to_100(self):
        """page_size 超上限 → 钳制 100, 不全表拉取"""
        _create_notifications("EMP020", 150)
        resp = self.client.get(ENDPOINT, {"page_size": 100000000})
        data = resp.data["data"]
        assert resp.status_code == 200
        assert data["page_size"] == 100
        assert len(data["results"]) == 100

    def test_invalid_page_returns_404(self):
        """page=abc → DRF 非法页码 404(行为锁定)"""
        _create_notifications("EMP020", 3)
        resp = self.client.get(ENDPOINT, {"page": "abc"})
        assert resp.status_code == 404

    def test_limit_param_no_longer_effective(self):
        """limit=5 被忽略 → 恒走默认分页 20 条(锚定 limit 参数移除, BF-097)"""
        _create_notifications("EMP020", 30)
        resp = self.client.get(ENDPOINT, {"limit": "5"})
        data = resp.data["data"]
        assert resp.status_code == 200
        assert len(data["results"]) == 20


@pytest.mark.django_db
class TestNotificationListFilters:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(auth_username="EMP020", password=TEST_PASSWORD)
        self.client.force_authenticate(user=self.user)

    def test_is_read_true_filter(self):
        """is_read=true → 仅已读"""
        _create_notifications("EMP020", 3, is_read=False)
        _create_notifications("EMP020", 2, is_read=True)
        resp = self.client.get(ENDPOINT, {"is_read": "true"})
        assert resp.data["data"]["count"] == 2

    def test_is_read_false_filter(self):
        """is_read=false → 仅未读(非 true 值均按未读, 与历史行为一致)"""
        _create_notifications("EMP020", 3, is_read=False)
        _create_notifications("EMP020", 2, is_read=True)
        resp = self.client.get(ENDPOINT, {"is_read": "false"})
        assert resp.data["data"]["count"] == 3

    def test_notification_type_filter(self):
        """notification_type 精确匹配"""
        _create_notifications("EMP020", 2, notification_type="system")
        _create_notifications("EMP020", 1, notification_type="repair")
        resp = self.client.get(ENDPOINT, {"notification_type": "repair"})
        assert resp.data["data"]["count"] == 1

    def test_priority_filter(self):
        """priority 精确匹配"""
        _create_notifications("EMP020", 2, priority="normal")
        _create_notifications("EMP020", 1, priority="high")
        resp = self.client.get(ENDPOINT, {"priority": "high"})
        assert resp.data["data"]["count"] == 1

    def test_keyword_filter_matches_title(self):
        """keyword 命中标题"""
        Notification.objects.create(
            recipient_jobcode="EMP020", notification_type="system", title="磁盘更换提醒", message="A"
        )
        Notification.objects.create(
            recipient_jobcode="EMP020", notification_type="system", title="普通通知", message="B"
        )
        resp = self.client.get(ENDPOINT, {"keyword": "磁盘"})
        assert resp.data["data"]["count"] == 1

    def test_keyword_filter_matches_message(self):
        """keyword 命中内容(标题不含, message 含)"""
        Notification.objects.create(
            recipient_jobcode="EMP020", notification_type="system", title="标题无关", message="包含报废关键词"
        )
        Notification.objects.create(
            recipient_jobcode="EMP020", notification_type="system", title="另一标题", message="无关内容"
        )
        resp = self.client.get(ENDPOINT, {"keyword": "报废"})
        assert resp.data["data"]["count"] == 1

    def test_recipient_isolation(self):
        """跨用户隔离: 只能看见自己接收的通知"""
        _create_notifications("EMP020", 2)
        _create_notifications("EMP021", 5)
        resp = self.client.get(ENDPOINT)
        assert resp.data["data"]["count"] == 2
        own_ids = set(Notification.objects.filter(recipient_jobcode="EMP020").values_list("id", flat=True))
        assert {item["id"] for item in resp.data["data"]["results"]} <= own_ids
