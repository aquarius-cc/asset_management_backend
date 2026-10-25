# d:\CodeDemo\asset_management_backend\apps\unregisteredasset\tests\test_pagination_order_stability.py
"""
未登记资产列表分页稳定性回归 (AUD-46 / 批次 G1, M-02 同型残留)

两处无序点 (本文件):
- UnregisteredAsset.Meta.ordering = ["-created_at"] (models.py:263) —— 无决胜键,
  同毫秒 created_at 并列时跨页次序未定义, PG 下 LIMIT/OFFSET 可能重复/丢行
- UnregisteredAssetViewSet.ordering = ["-discovery_date"] (views.py:131) —— DRF 视图
  默认序 (OrderingFilter 的 default, 覆盖 Meta 序), 同日 discovery_date 并列时同型缺陷

修复: Meta → ["-created_at", "-id"]; 视图默认序 → ["-discovery_date", "-id"]
(-id 为 PK 决胜键, 与 M-02 八模型 (-created_at,-id) / BF-128 (-created_at,-id) 同模式,
语义中性不改现有排序观感。视图默认序不受 ordering_fields 约束, 且 -id 不加入
ordering_fields —— 避免扩大客户端可排序面 = 跨端契约变更)。

每个断言三件套:
1. 不产生 UnorderedObjectListWarning
2. 两页 (page_size=2) 无重复、无丢行、覆盖全集
3. 返回序 == 期望全序 (Python 侧独立计算)
外加修复源断言 (先红锚)。
"""

import warnings
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.paginator import UnorderedObjectListWarning
from rest_framework import status
from rest_framework.test import APIClient

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.views import UnregisteredAssetViewSet
from apps.usermanagement.models import Employee
from core.tests import TEST_PASSWORD


# 真实挂载: config/urls.py:160 "api/v1/unregisteredassets/" + router 前缀 "unregistered-assets"
LIST_URL = "/api/v1/unregisteredassets/unregistered-assets/"


@pytest.fixture
def admin_client(db):
    """superuser 客户端 (行级隔离: 仅 system_admin/superuser 可见全量)"""
    User = get_user_model()
    admin = User.objects.create_user(
        auth_username="unr_pag_admin",
        password=TEST_PASSWORD,
        auth_is_staff=True,
        is_superuser=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def assets_with_date_tie(db, admin_client):
    """同日并列夹具: 4 行 discovery_date 全同 (决胜只能靠 -id)

    Employee.employee_department 可空 → 最小 Employee 即可满足 FK 必填。
    scenario_type 取枚举首键 (避免硬编码键名漂移)。
    """
    person = Employee.objects.create(employee_jobcode="UNR_PAG_01", employee_name="分页夹具")
    scenario_key = UnregisteredAsset.ScenarioType.choices[0][0]
    for i in range(1, 5):
        UnregisteredAsset.objects.create(
            scenario_type=scenario_key,
            discovery_date=date(2026, 10, 20),
            discovery_location=f"分页夹具地点{i}",
            discovery_person=person,
            asset_name=f"分页夹具资产{i}",
        )


def _expected_ids(rows) -> list[int]:
    """按 (-discovery_date, -id) 全序给出期望 id 序列 (Python 侧独立计算)"""
    return [r.id for r in sorted(rows, key=lambda r: (r.discovery_date, r.id), reverse=True)]


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
    """两页覆盖全部期望行、无重复, 且顺序 == (-discovery_date, -id) 全序"""
    combined = page1 + page2
    assert len(set(combined)) == len(combined), f"翻页出现重复行: {combined}"
    assert combined == expected, f"分页序不符 (-discovery_date,-id): got={combined} expected={expected}"


class TestUnregisteredPaginationStability:
    """UnregisteredAssetViewSet list 分页稳定性 (AUD-46 / 批次 G1)"""

    def test_meta_ordering_has_id_tiebreak(self):
        """修复源断言: Meta.ordering 须含 -id 决胜键 (先红锚: 修复前为 ['-created_at'])"""
        assert tuple(UnregisteredAsset._meta.ordering) == ("-created_at", "-id")

    def test_view_default_ordering_has_id_tiebreak(self):
        """修复源断言: 视图默认序须含 -id 决胜键 (先红锚: 修复前为 ['-discovery_date'])"""
        assert tuple(UnregisteredAssetViewSet.ordering) == ("-discovery_date", "-id")

    def test_list_two_pages_cover_all_in_order(self, admin_client, assets_with_date_tie):
        page1, page2, count = _fetch_two_pages(admin_client)
        expected = _expected_ids(UnregisteredAsset.objects.all())
        assert count == len(expected), f"count 应等于全集: count={count} expected={expected}"
        assert len(page1 + page2) == count, f"两页未覆盖全集: {page1 + page2} vs count={count}"
        _assert_full_order(page1, page2, expected)
