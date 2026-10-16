"""
notification_list limit 参数校验测试（CodeReview20261014 M-1 / BF-095）

覆盖:
- limit=abc（非数字）→ 400 兜底为默认 20，不 500
- limit=-5（负数）→ max(limit, 1) 兜底，不触发 Django 负切片 AssertionError
- limit 超上限 → min(limit, 100) 钳制，不全表拉取
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.notification.models import Notification
from core.tests import TEST_PASSWORD


User = get_user_model()


def _create_notifications(jobcode: str, count: int) -> None:
    Notification.objects.bulk_create(
        Notification(
            recipient_jobcode=jobcode,
            notification_type="system",
            title=f"通知{i}",
            message="msg",
        )
        for i in range(count)
    )


@pytest.mark.django_db
class TestNotificationListLimit:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(auth_username="EMP020", password=TEST_PASSWORD)
        self.client.force_authenticate(user=self.user)

    def test_non_numeric_limit_falls_back_to_default(self):
        """limit=abc → ValueError 兜底为默认 20，响应 200"""
        _create_notifications("EMP020", 25)
        resp = self.client.get("/api/v1/notifications/", {"limit": "abc"})
        assert resp.status_code == 200
        assert len(resp.data["data"]) == 20

    def test_negative_limit_clamped_to_one(self):
        """limit=-5 → max(limit, 1) 兜底，不 500（负切片回归护栏）"""
        _create_notifications("EMP020", 3)
        resp = self.client.get("/api/v1/notifications/", {"limit": "-5"})
        assert resp.status_code == 200
        assert len(resp.data["data"]) == 1

    def test_oversized_limit_clamped_to_100(self):
        """limit 超上限 → min(limit, 100) 钳制，不全表拉取"""
        _create_notifications("EMP020", 101)
        resp = self.client.get("/api/v1/notifications/", {"limit": "100000000"})
        assert resp.status_code == 200
        assert len(resp.data["data"]) == 100
