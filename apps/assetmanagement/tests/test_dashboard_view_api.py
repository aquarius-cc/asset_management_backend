"""
仪表盘 ViewSet API 测试

测试 DashboardViewSet 的5个统计端点:
- trend, department_distribution, type_distribution,
  expiring_assets, maintenance_reminders
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def authenticated_client(api_client, auth_user):
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.mark.django_db
class TestDashboardTrend:
    def test_trend_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)
        assert len(response.data["data"]) >= 30
        item = response.data["data"][0]
        assert "date" in item
        assert "new_assets" in item
        assert "distributed" in item
        assert "recovered" in item
        assert "scrapped" in item

    def test_trend_custom_days(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"days": 7})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 7

    def test_trend_days_capped_at_365(self, authenticated_client, asset):
        url = reverse("dashboard-trend")
        response = authenticated_client.get(url, {"days": 999})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 300


@pytest.mark.django_db
class TestDashboardDepartmentDistribution:
    def test_returns_list(self, authenticated_client, asset, user):
        url = reverse("dashboard-department-distribution")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_item_has_required_fields(self, authenticated_client, asset, user):
        url = reverse("dashboard-department-distribution")
        response = authenticated_client.get(url)
        if response.data["data"]:
            item = response.data["data"][0]
            assert "department_name" in item
            assert "asset_count" in item
            assert "percentage" in item


@pytest.mark.django_db
class TestDashboardTypeDistribution:
    def test_returns_list(self, authenticated_client, asset, asset_type):
        url = reverse("dashboard-type-distribution")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_item_has_required_fields(self, authenticated_client, asset, asset_type):
        url = reverse("dashboard-type-distribution")
        response = authenticated_client.get(url)
        if response.data["data"]:
            item = response.data["data"][0]
            assert "type_name" in item
            assert "count" in item
            assert "percentage" in item


@pytest.mark.django_db
class TestDashboardExpiringAssets:
    def test_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-expiring-assets")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)

    def test_custom_days(self, authenticated_client, asset):
        url = reverse("dashboard-expiring-assets")
        response = authenticated_client.get(url, {"days": 7})
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestDashboardMaintenanceReminders:
    def test_returns_list(self, authenticated_client, asset):
        url = reverse("dashboard-maintenance-reminders")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)


@pytest.mark.django_db
class TestDashboardRecentAssetRecordcodes:
    def test_returns_out_assets(self, authenticated_client, asset, user):
        """recent_asset_recordcodes 应返回出库记录（调用 get_recent_out_assets）"""
        from apps.assetmanagement.models import OutAsset

        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        url = reverse("dashboard-recent-asset-recordcodes")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert isinstance(response.data["data"], list)
