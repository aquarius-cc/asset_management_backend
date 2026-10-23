# d:\CodeDemo\Python\asset_management_backend\apps\authusermanagement\tests\test_user_pagination_order_stability.py
"""
用户列表分页稳定性回归 (BF-128 §六 批外收口)

登记定性订正 (Fact-1): 原登记称 views.py:118/:167 两处分页「无序」部分失实——
AuthUser.Meta.ordering = ["auth_username"] 自 2026-07-15 (ada969cf) 已存在,
UnorderedObjectListWarning 实测不触发 (系按「无 created_at」类推漏查 models.py:192)。
真实残留是并列决胜缺失: auth_username 仅条件唯一 (condition=auth_is_active=True,
migrations/0001_initial.py:39), list 可同时含同名 active+inactive 行,
仅按 auth_username 排序时并列行跨页次序未定义, PG 下 LIMIT/OFFSET 可能重复/丢行。

修复: Meta.ordering 加决胜键 → ["auth_username", "auth_id"] (auth_id 为 PK,
models.py:110; 与 M-02 八模型 (-created_at,-id) 同模式; 语义中性不改现有字母序 UX)。

每个端点断言三件套:
1. 不产生 UnorderedObjectListWarning
2. 两页 (page_size=2) 无重复、无丢行、覆盖全集
3. 返回序 == (auth_username, auth_id) 升序全序
外加 Meta 源断言 (先红锚: 修复前为 ["auth_username"])。
"""

import warnings

import pytest
from django.core.paginator import UnorderedObjectListWarning
from rest_framework import status
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


LIST_URL = "/api/v1/auth/users/"
LIST_ACTIVE_URL = "/api/v1/auth/users/list_active/"


@pytest.fixture
def admin_client(db):
    """system_admin 客户端 (list / list_active 均需 IsSystemAdmin)"""
    admin = AuthUser.objects.create_user(
        auth_username="sysadmin_pag",
        password=TEST_PASSWORD,
        auth_phone="13900000001",
        auth_is_staff=True,
        is_superuser=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def users_with_name_tie(db):
    """同名并列夹具: inactive dup 先建 (auth_id 更小) + aaa + active dup

    加上 admin_client 的 sysadmin_pag 共 4 行;
    修复后 (auth_username, auth_id) 序: aaa, dup(inact), dup(act), sysadmin_pag
    page_size=2 时并列对恰好跨页边界: page1=[aaa, dup_inact], page2=[dup_act, sysadmin]。
    夹具可插入性: auth_username 字段级无 unique, 仅条件唯一 (active 行) →
    active+inactive 同名两行不触发 IntegrityError; recordcode 由 save() 自动发号。
    """
    AuthUser.objects.create_user(
        auth_username="dup",
        password=TEST_PASSWORD,
        auth_phone="13900000002",
        auth_is_active=False,
    )
    AuthUser.objects.create_user(auth_username="aaa", password=TEST_PASSWORD, auth_phone="13900000003")
    AuthUser.objects.create_user(
        auth_username="dup",
        password=TEST_PASSWORD,
        auth_phone="13900000004",
    )


def _expected_ids(rows) -> list[int]:
    """按 (auth_username, auth_id) 升序全序给出期望 auth_id 序列 (Python 侧独立计算)"""
    return [u.auth_id for u in sorted(rows, key=lambda u: (u.auth_username, u.auth_id))]


def _fetch_two_pages(client, url: str):
    """按 page=1/2 取两页 (page_size=2), 捕获 UnorderedObjectListWarning

    Returns:
        (page1_auth_ids, page2_auth_ids, count)
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = client.get(url, {"page_size": 2, "page": 1})
        second = client.get(url, {"page_size": 2, "page": 2})
    unordered = [w for w in caught if issubclass(w.category, UnorderedObjectListWarning)]
    assert unordered == [], f"UnorderedObjectListWarning 未消除: {[str(w.message) for w in unordered]}"
    assert first.status_code == status.HTTP_200_OK, first.data
    assert second.status_code == status.HTTP_200_OK, second.data
    page1 = [item["auth_id"] for item in first.data["data"]["results"]]
    page2 = [item["auth_id"] for item in second.data["data"]["results"]]
    return page1, page2, first.data["data"]["count"]


def _assert_full_order(page1: list[int], page2: list[int], expected: list[int]) -> None:
    """两页覆盖全部期望行、无重复, 且顺序 == (auth_username, auth_id) 升序"""
    combined = page1 + page2
    assert len(set(combined)) == len(combined), f"翻页出现重复行: {combined}"
    assert combined == expected, f"分页序不符 (auth_username, auth_id): got={combined} expected={expected}"


class TestUserListPaginationStability:
    """AuthUserViewSet list / list_active 分页稳定性 (BF-128 §六 批外收口)"""

    def test_meta_ordering_has_username_tiebreak(self):
        """修复源断言: Meta.ordering 须含 auth_id 决胜键 (先红锚: 修复前为 ['auth_username'])"""
        assert tuple(AuthUser._meta.ordering) == ("auth_username", "auth_id")

    def test_list_two_pages_cover_all_in_order(self, admin_client, users_with_name_tie):
        page1, page2, count = _fetch_two_pages(admin_client, LIST_URL)
        expected = _expected_ids(AuthUser.objects.all())
        assert count == len(expected), f"count 应等于全集: count={count} expected={expected}"
        assert len(page1 + page2) == count, f"两页未覆盖全集: {page1 + page2} vs count={count}"
        _assert_full_order(page1, page2, expected)

    def test_list_active_two_pages_cover_all_in_order(self, admin_client, users_with_name_tie):
        page1, page2, count = _fetch_two_pages(admin_client, LIST_ACTIVE_URL)
        expected = _expected_ids(AuthUser.objects.filter(auth_is_active=True))
        assert count == len(expected), f"count 应等于 active 全集: count={count} expected={expected}"
        assert len(page1 + page2) == count, f"两页未覆盖全集: {page1 + page2} vs count={count}"
        _assert_full_order(page1, page2, expected)
