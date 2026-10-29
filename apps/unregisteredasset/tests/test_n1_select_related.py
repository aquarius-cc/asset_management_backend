"""
M-04: UnregisteredAsset 读路径 N+1 回归断言（与 M-10 同批，互为护栏）。

三条链的口径（merge-audit-20261029 M-04 修正版）:
- 列表 N 行: query 数与 N 无关（ListSerializer 仅消费 discovery_person.employee_name）
- 导出 N 行: query 数与 N 无关（export_columns 仅 discovery_person__* 两列）
- 详情单对象: 固定 O(1)，钉绝对条数上限 ≤5，不追求常数

先红后绿: 修复前 list/export 的 query 数随 N 线性增长（N+1），用例必红；
get_queryset_for_user 补 select_related("discovery_person") 后转绿。
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db(transaction=True)

BATCH = 3  # 第二轮比第一轮多造的行数


def _seed_rows(employee, storage, asset_type, start: int, count: int):
    from apps.unregisteredasset.models import UnregisteredAsset

    rows = []
    for i in range(start, start + count):
        rows.append(
            UnregisteredAsset.objects.create(
                unregistered_code=f"UNREG-M04-{i:04d}",
                scenario_type="s1_no_record",
                discovery_date="2024-07-01",
                discovery_location="测试地点",
                discovery_person=employee,
                asset_name=f"N+1回归资产{i}",
                unregistered_asset_type=asset_type,
                unregistered_asset_storage=storage,
                approval_status="pending",
            )
        )
    return rows


def _count_list_queries(admin_auth_user) -> int:
    client = APIClient()
    client.force_authenticate(user=admin_auth_user)
    url = reverse("unregisteredasset:unregisteredasset-list")
    client.get(url)  # 热身: 排除首轮建连/会话初始化噪声, 只量业务查询
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == status.HTTP_200_OK, response.data
    return len(ctx.captured_queries)


def _count_export_queries(admin_auth_user) -> int:
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.unregisteredasset.views import UnregisteredAssetViewSet

    url = reverse("unregisteredasset:unregisteredasset-export-excel")
    request = APIRequestFactory().get(url)
    force_authenticate(request, user=admin_auth_user)
    UnregisteredAssetViewSet.as_view({"get": "export_excel"})(request)  # 热身
    with CaptureQueriesContext(connection) as ctx:
        response = UnregisteredAssetViewSet.as_view({"get": "export_excel"})(request)
    assert response.status_code == status.HTTP_200_OK
    return len(ctx.captured_queries)


class TestListNoN1:
    """列表: query 数不随 N 增长（先红: N+1 使两轮相差 BATCH）"""

    def test_list_queries_constant(self, admin_auth_user, employee, storage, asset_type):
        _seed_rows(employee, storage, asset_type, 1, BATCH)
        first = _count_list_queries(admin_auth_user)

        _seed_rows(employee, storage, asset_type, 1 + BATCH, BATCH)
        second = _count_list_queries(admin_auth_user)

        assert first == second, (
            f"M-04 N+1: 行数 {BATCH}→{2 * BATCH} 时列表查询数 {first}→{second}，"
            "列表层缺 select_related('discovery_person')"
        )


class TestExportNoN1:
    """导出: query 数不随 N 增长"""

    def test_export_queries_constant(self, admin_auth_user, employee, storage, asset_type):
        _seed_rows(employee, storage, asset_type, 1, BATCH)
        first = _count_export_queries(admin_auth_user)

        _seed_rows(employee, storage, asset_type, 1 + BATCH, BATCH)
        second = _count_export_queries(admin_auth_user)

        assert first == second, (
            f"M-04 N+1: 行数 {BATCH}→{2 * BATCH} 时导出查询数 {first}→{second}，"
            "导出同源 queryset 缺 select_related('discovery_person')"
        )


class TestDetailBounded:
    """详情: 单对象 O(1)，钉绝对条数上限（不追求常数）"""

    def test_detail_queries_bounded(self, admin_auth_user, unregistered_asset_s1):
        client = APIClient()
        client.force_authenticate(user=admin_auth_user)
        url = reverse(
            "unregisteredasset:unregisteredasset-detail",
            kwargs={"unregistered_code": unregistered_asset_s1.unregistered_code},
        )
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(ctx.captured_queries) <= 5, (
            f"M-04: 详情查询数 {len(ctx.captured_queries)} 超过上限 5，详情序列化出现意外逐字段查询"
        )
