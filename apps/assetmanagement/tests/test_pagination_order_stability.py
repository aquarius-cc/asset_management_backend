# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\test_pagination_order_stability.py
"""
分页稳定性回归 (M-02 / NEW-02)

问题: 绕过 filter_queryset 的自定义 action (by-asset / by-date-range /
getcontractByname / global-search) 直接把 Selector 裸 filter() 结果交给
CustomPageNumberPagination。模型 Meta.ordering 缺失时 QuerySet 无序,
Django 分页器发 UnorderedObjectListWarning, PG 下 LIMIT/OFFSET 翻页
可能重复/丢行。

修复: 8 个模型补 Meta.ordering = ["-created_at", "-id"] (全序,
消除 created_at 微秒并列的残余不确定)。

每个端点断言三件套:
1. 不产生 UnorderedObjectListWarning
2. 两页 (page_size=2, 共 3 行) 无重复、无丢行
3. 返回序 == (-created_at, -id) 全序
"""

import warnings

import pytest
from django.core.paginator import UnorderedObjectListWarning
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import (
    Asset,
    BrokenAsset,
    Contract,
    FoundAsset,
    LostAsset,
    OutAsset,
    RecycleAsset,
    RepairAsset,
    WasteAsset,
)


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证普通用户客户端 (by-asset 系 action 读权限)"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_auth_user):
    """管理员认证客户端 (合同自定义读 action 需 asset_admin+)"""
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


def _fetch_two_pages(client, url, query=None):
    """按 page=1/2 取两页, 捕获 UnorderedObjectListWarning

    Returns:
        (page1_recordcodes, page2_recordcodes, count)
    """
    params = {"page_size": 2, **(query or {})}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = client.get(url, {**params, "page": 1})
        second = client.get(url, {**params, "page": 2})
    unordered = [w for w in caught if issubclass(w.category, UnorderedObjectListWarning)]
    assert unordered == [], f"UnorderedObjectListWarning 未消除: {[str(w.message) for w in unordered]}"
    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    page1 = [item["recordcode"] for item in first.data["data"]["results"]]
    page2 = [item["recordcode"] for item in second.data["data"]["results"]]
    count = first.data["data"]["count"]
    return page1, page2, count


def _assert_full_order(page1, page2, rows):
    """断言两页覆盖全部 3 行、无重复, 且顺序 == (-created_at, -id)"""
    expected = [row.recordcode for row in sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)]
    assert len(expected) == 3
    combined = page1 + page2
    assert len(set(combined)) == len(combined), f"翻页出现重复行: {combined}"
    assert set(combined) == set(expected), f"翻页出现丢行: got={combined} expected={expected}"
    assert combined == expected, f"分页序不符 (-created_at, -id): got={combined} expected={expected}"


@pytest.fixture
def extra_broken_rows(db, asset, employee):
    """同资产 3 条损坏记录 (asset_recordcode 是 FK, 可多条)"""
    return [
        BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason=f"原因{i}",
            broken_date="2024-09-01",
            broken_description=f"描述{i}",
            operator_employee=employee,
        )
        for i in range(3)
    ]


@pytest.fixture
def extra_lost_rows(db, asset, employee):
    """同资产 3 条遗失记录"""
    return [
        LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason=f"原因{i}",
            lost_date="2024-10-01",
            last_known_location=f"位置{i}",
            lost_description=f"描述{i}",
            operator_employee=employee,
        )
        for i in range(3)
    ]


@pytest.fixture
def extra_found_rows(db, asset, employee):
    """3 条找回记录 (lost_asset_recordcode 是 OneToOne, 需 3 条遗失记录)"""
    rows = []
    for i in range(3):
        lost = LostAsset.objects.create(
            asset_recordcode=asset,
            lost_reason=f"遗失原因{i}",
            lost_date="2024-10-01",
            last_known_location=f"位置{i}",
            lost_description=f"描述{i}",
            operator_employee=employee,
        )
        rows.append(
            FoundAsset.objects.create(
                lost_asset_recordcode=lost,
                asset_recordcode=asset,
                found_location=f"找回位置{i}",
                found_date="2024-11-01",
                found_description=f"找回描述{i}",
                operator_employee=employee,
            )
        )
    return rows


@pytest.fixture
def extra_repair_rows(db, asset, employee):
    """同资产 3 条维修记录

    repair_status 须置 completed: in_progress 受 uniq_active_repair_per_asset
    约束, 同资产只允许 1 条; completed 无约束可多条, by-asset 才有 >1 行可分页。
    """
    return [
        RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_reason=f"维修原因{i}",
            repair_date="2024-12-01",
            repair_description=f"维修描述{i}",
            repair_status=RepairAsset.RepairStatus.COMPLETED,
            operator_employee=employee,
        )
        for i in range(3)
    ]


@pytest.fixture
def extra_recycle_rows(db, asset, employee):
    """3 条回收记录 (outasset_recordcode 是 OneToOne, 需 3 条出库记录)"""
    rows = []
    for _ in range(3):
        outasset = OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        rows.append(
            RecycleAsset.objects.create(
                outasset_recordcode=outasset,
                asset_recordcode=asset,
                recycle_asset_date="2024-07-01",
                recycle_asset_number=1,
                operator_employee=employee,
            )
        )
    return rows


@pytest.fixture
def extra_waste_rows(db, storage, asset_type, user):
    """3 条报废记录 (asset_recordcode 是 OneToOne, 需 3 个资产)"""
    rows = []
    for i in range(3):
        asset = Asset.objects.create(
            asset_code=f"AW{i:03d}",
            asset_name=f"报废测试资产{i}",
            asset_purchase_price=100.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_entry_person_recordcode=user,
            asset_current_status="scrapped",
        )
        rows.append(WasteAsset.objects.create(asset_recordcode=asset, waste_asset_date="2024-08-01"))
    return rows


@pytest.fixture
def extra_contracts(db):
    """3 条同名合同 (contract_code 唯一, 名称共用搜索关键词)"""
    return [
        Contract.objects.create(
            contract_code=f"CP{i:03d}",
            contract_name="分页稳定性合同",
            contract_amount=10000.00,
            contract_status="purchasing",
            contract_type="service",
        )
        for i in range(3)
    ]


@pytest.mark.django_db
class TestByAssetPaginationStability:
    """by-asset 系 action: selector 裸 filter() 直接分页, 依赖 Meta.ordering 兜底"""

    def test_broken_by_asset_two_pages_stable(self, authenticated_client, asset, extra_broken_rows):
        """损坏记录 by-asset: 两页覆盖 3 行无重复丢行, 序为 (-created_at, -id)"""
        url = reverse("broken-assets-by-asset", kwargs={"asset_code": asset.asset_code})
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_broken_rows)

    def test_lost_by_asset_two_pages_stable(self, authenticated_client, asset, extra_lost_rows):
        """遗失记录 by-asset: 两页覆盖 3 行无重复丢行, 序为 (-created_at, -id)"""
        url = reverse("lost-assets-by-asset", kwargs={"asset_code": asset.asset_code})
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_lost_rows)

    def test_found_by_asset_two_pages_stable(self, authenticated_client, asset, extra_found_rows):
        """找回记录 by-asset: 两页覆盖 3 行无重复丢行, 序为 (-created_at, -id)"""
        url = reverse("found-assets-by-asset", kwargs={"asset_code": asset.asset_code})
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_found_rows)

    def test_damaged_by_asset_pagination_ordered(self, authenticated_client, asset, damaged_asset):
        """待报废记录 by-asset: 无序分页发 UnorderedObjectListWarning, 修复后消除

        uq_damaged_asset_active_asset 约束下同资产仅 1 条未删待报废记录,
        无法构造 >1 行的两页场景, 但分页器对无序单行列表同样告警,
        故断言无告警 + 单行结果确定。
        """
        url = reverse("damaged-assets-by-asset", kwargs={"asset_recordcode": asset.asset_code})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            response = authenticated_client.get(url, {"page_size": 2})
        unordered = [w for w in caught if issubclass(w.category, UnorderedObjectListWarning)]
        assert unordered == [], f"UnorderedObjectListWarning 未消除: {[str(w.message) for w in unordered]}"
        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert response.data["data"]["count"] == 1
        assert [item["recordcode"] for item in results] == [damaged_asset.recordcode]

    def test_recycle_by_asset_two_pages_stable(self, authenticated_client, asset, extra_recycle_rows):
        """回收记录 by-asset: 两页覆盖 3 行无重复丢行, 序为 (-created_at, -id)"""
        url = reverse("recycle-assets-by-asset", kwargs={"asset_recordcode_code": asset.asset_code})
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_recycle_rows)

    def test_repair_by_asset_two_pages_stable(self, authenticated_client, asset, extra_repair_rows):
        """维修记录 by-asset: 两页覆盖 3 行无重复丢行, 序为 (-created_at, -id)"""
        url = reverse("repair-assets-by-asset", kwargs={"asset_code": asset.asset_code})
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_repair_rows)


@pytest.mark.django_db
class TestOtherUnorderedPaginationActions:
    """其余两处绕过 filter_queryset 的分页 action"""

    def test_waste_by_date_range_two_pages_stable(self, authenticated_client, extra_waste_rows):
        """报废记录 by-date-range: get_queryset() 直接分页, 两页覆盖 3 行无重复丢行"""
        url = reverse("waste-assets-by-date-range")
        page1, page2, count = _fetch_two_pages(authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_waste_rows)

    def test_contract_get_by_name_two_pages_stable(self, admin_authenticated_client, extra_contracts):
        """合同 getcontractByname: search_contracts 裸 filter() 分页, 序为 (-created_at, -id)"""
        url = reverse("contracts-getcontractByname", kwargs={"name": "分页稳定性合同"})
        page1, page2, count = _fetch_two_pages(admin_authenticated_client, url)
        assert count == 3
        _assert_full_order(page1, page2, extra_contracts)

    def test_contract_global_search_two_pages_stable(self, admin_authenticated_client, extra_contracts):
        """合同 global-search: search_contracts 裸 filter() 分页, 序为 (-created_at, -id)"""
        url = reverse("contracts-global-search")
        page1, page2, count = _fetch_two_pages(admin_authenticated_client, url, {"keyword": "分页稳定性合同"})
        assert count == 3
        _assert_full_order(page1, page2, extra_contracts)
