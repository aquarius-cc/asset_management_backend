"""M-PERF-02/03 性能门：硬盘列表与资产类型列表序列化 1+N→1（批次 2）。

先红锚：
- 硬盘：HardDiskSNSerializer 经 asset_recordcode.asset_code/.asset_name 触发每行 1 查询
  （select_related("asset_recordcode") 后 → 恒 1）。
- 资产类型：AssetTypeSerializer 经 parent.type_code 触发每行 1 查询
  （select_related("parent") 后 → 恒 1）。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.assetmanagement.models import HardDiskSN
from apps.assetmanagement.selectors.asset_selector import AssetTypeSelector
from apps.assetmanagement.selectors.hard_disk_sn_selector import HardDiskSNSelector
from apps.assetmanagement.serializers.base_model_serializers import (
    AssetTypeSerializer,
    HardDiskSNSerializer,
)
from apps.assetmanagement.tests.factories import AssetTypeFactory
from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db

_BATCH = 5


def _admin() -> Any:
    return AuthUser.objects.create_superuser(auth_username="PADMIN9", password=TEST_PASSWORD)


def _seed_disks(asset: Any, start: int, n: int) -> None:
    for i in range(start, start + n):
        HardDiskSN.objects.create(asset_recordcode=asset, harddisk_sn_code=f"SN_{i:03d}", harddisk_type="SSD")


def _serialize_disks(user: Any) -> int:
    qs = HardDiskSNSelector.get_queryset_for_user(user)
    return len(HardDiskSNSerializer(qs, many=True).data)


class TestHardDiskSNListSingleQuery:
    """M-PERF-02：硬盘列表序列化 1+N→1"""

    def test_disk_list_single_query(self, asset: Any, django_assert_num_queries) -> None:
        admin = _admin()
        # 先建 1 条再量 first（修 F1：避免首查建表干扰计数）
        _seed_disks(asset, 0, 1)
        _serialize_disks(admin)
        _seed_disks(asset, 1, _BATCH - 1)  # 补 BATCH 条

        with django_assert_num_queries(1):
            assert _serialize_disks(admin) == _BATCH


class TestAssetTypeListSingleQuery:
    """M-PERF-03：资产类型列表序列化 1+N→1"""

    def test_asset_type_list_single_query(self, asset_type: Any, django_assert_num_queries) -> None:
        child = AssetTypeFactory(type_code="ATCHILD1", type_name="子类型")
        child.parent = asset_type
        child.save()

        AssetTypeSelector.get_all_asset_types().first()  # warm-up
        with django_assert_num_queries(1):
            data = AssetTypeSerializer(AssetTypeSelector.get_all_asset_types(), many=True).data
        assert len(data) == 2
        # parent_type_code 字段真实取到（锚定 parent 访问发生）
        child_row = next(r for r in data if r["type_code"] == "ATCHILD1")
        assert child_row["parent_type_code"] == asset_type.type_code
