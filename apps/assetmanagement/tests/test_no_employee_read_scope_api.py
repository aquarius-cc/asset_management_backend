"""
AUD-21 授权可见性缺口 API 级回归(真实利用链,不可回退)

利用链:POST /api/v1/auth/register/ 自注册 → 账号天然无 Employee 绑定 →
原实现 get_department_codes_for_user 对无 Employee 返回 None(不限制) →
行级隔离读端点全部放行 = 自注册即全量可见。

收紧后(数据层根治,department_scope.py 无 Employee → 空集):自注册账号在
全部行级隔离读端点必须零行/全零,my-permissions 数据范围为空部门范围(拒绝)。

认证使用注册响应签发的 Bearer token(完整链路),不使用 force_authenticate 捷径,
以保证锚定的是"注册端点 → 读端点"这条真实可达路径。
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetOperationLog
from apps.usermanagement.models import Employee


User = get_user_model()

REGISTER_URL = "/api/v1/auth/register/"
OVERVIEW_URL = "/api/v1/dashboard/overview/"
LOGS_URL = "/api/v1/assets/operation-logs/"
MY_PERMISSIONS_URL = "/api/v1/auth/my-permissions/"


def _register(api_client: APIClient, username: str = "aud21reg") -> APIClient:
    """真实注册并把签发的 access token 装入 Bearer 通道,返回已认证客户端。"""
    # RegisterRateThrottle 5/minute 按 cache 计数,逐测清零防止串扰
    cache.clear()
    resp = api_client.post(
        REGISTER_URL,
        {
            "auth_username": username,
            "password": "Passw0rd@123",
            "password2": "Passw0rd@123",
            "email": f"{username}@x.com",
            "auth_phone": "13900000001",
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    assert resp.data["code"] == 0
    access = resp.data["data"]["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api_client


def _rows(response) -> list[dict]:
    """分页/非分页兼容的行提取。"""
    data = response.data["data"]
    return data["results"] if isinstance(data, dict) and "results" in data else data


@pytest.mark.django_db
class TestRegisteredUserReadScope:
    """自注册(无 Employee)账号读面全量拒绝 —— AUD-21 利用链回归"""

    @pytest.fixture
    def registered_client(self, api_client: APIClient) -> APIClient:
        return _register(api_client)

    def test_registered_user_sees_no_assets(self, registered_client: APIClient, asset: Asset) -> None:
        # DB 中确有资产(证明"看不见"源于行级隔离而非无数据)
        assert Asset.objects.filter(is_deleted=False).count() >= 1

        resp = registered_client.get(reverse("assets-list"))

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["code"] == 0
        assert _rows(resp) == []

    def test_registered_user_sees_no_employees(self, registered_client: APIClient, employee: Employee) -> None:
        assert Employee.objects.filter(is_deleted=False).count() >= 1

        resp = registered_client.get(reverse("employees-list"))

        assert resp.status_code == status.HTTP_200_OK
        assert _rows(resp) == []

    def test_registered_user_dashboard_totals_zero(self, registered_client: APIClient, asset: Asset) -> None:
        assert Asset.objects.filter(is_deleted=False).count() >= 1

        resp = registered_client.get(OVERVIEW_URL)

        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert data["total_assets"] == 0
        assert data["in_stock_assets"] == 0
        assert data["active_assets"] == 0
        assert data["total_distributed"] == 0
        assert data["total_recycled"] == 0

    def test_registered_user_sees_no_operation_logs(self, registered_client: APIClient, asset: Asset) -> None:
        AssetOperationLog.objects.create(asset_code=asset.asset_code, operation_type="create", description="seed")
        assert AssetOperationLog.objects.count() >= 1

        resp = registered_client.get(LOGS_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert _rows(resp) == []

    def test_registered_user_my_permissions_restricted(self, registered_client: APIClient) -> None:
        resp = registered_client.get(MY_PERMISSIONS_URL)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["data"]["data_scope"] == {
            "scope_type": "departments",
            "department_codes": [],
            "include_children": False,
        }
