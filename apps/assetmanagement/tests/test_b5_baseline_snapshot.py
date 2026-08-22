"""
B-5 治理基线快照(Commit 0)

锁定 8 个未迁移批量端点的【当前】响应结构, 作为 DR-1 收敛的行为基线:
- A/B 组(标准形态): 迁移后这些断言应原样通过(零行为变更证明)
- C 组(damaged/waste): 锁定【迁移前】的差异化错误码/文案,
  Commit 2 迁移时在同一 diff 中显式更新为新期望值

注意: 标注 [将变更] 的断言在 Service 层迁移提交中必须同步更新,
并在 commit message 中列出前后对照。
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def admin_client_fixture(api_client, admin_auth_user):
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


def _assert_batch_shape(data, *, success_key: str) -> None:
    """标准五键结构断言"""
    assert set(data.keys()) == {
        "total", "success_count", "fail_count", success_key, "fail_items",
    }


# ==================== B 组: 标准形态端点(迁移后断言不变) ====================
@pytest.mark.django_db
class TestStandardDeleteBaselines:
    """5 个标准 batch_delete 端点的结构基线"""

    def test_asset_type_batch_delete(self, admin_client_fixture, asset_type):
        url = reverse("asset-types-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": [asset_type.type_code]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        _assert_batch_shape(resp.data["data"], success_key="success_ids")
        assert resp.data["message"] == "批量删除完成,成功 1 条,失败 0 条"

    def test_contract_batch_delete(self, admin_client_fixture, contract):
        url = reverse("contracts-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": [contract.contract_code]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        _assert_batch_shape(resp.data["data"], success_key="success_ids")
        assert resp.data["message"] == "批量删除完成,成功 1 条,失败 0 条"

    def test_storage_batch_delete(self, admin_client_fixture, storage):
        url = reverse("storages-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": [storage.storage_code]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        _assert_batch_shape(resp.data["data"], success_key="success_ids")
        assert resp.data["message"] == "批量删除完成,成功 1 条,失败 0 条"

    def test_out_asset_batch_delete(self, admin_client_fixture, outasset):
        url = reverse("out-assets-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": [outasset.recordcode]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        _assert_batch_shape(resp.data["data"], success_key="success_ids")
        assert resp.data["message"] == "批量删除完成,成功 1 条,失败 0 条"

    def test_recycle_asset_batch_delete(self, admin_client_fixture, recycle_asset):
        url = reverse("recycle-assets-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": [recycle_asset.recordcode]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        _assert_batch_shape(resp.data["data"], success_key="success_ids")
        # 注意: recycle 删除有资产状态前置条件, 计数不锁定, 仅锁 message 格式
        assert resp.data["message"].startswith("批量删除完成,成功 ")
        assert resp.data["message"].endswith("条")


# ==================== C 组: 行为将变更的端点(迁移时更新断言) ====================
@pytest.mark.django_db
class TestDamagedBaseline:
    def test_batch_delete_missing_id_after_dr1(self, admin_client_fixture):
        """[已变更 commit e85b6cf+本次] 错误码透传: VALIDATION_ERROR → DAMAGED_ASSET_NOT_FOUND

        前端证据: 无 error_code 分支消费(b5-frontend-error-code-search.md)。
        """
        url = reverse("damaged-assets-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": ["NO_SUCH"]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        _assert_batch_shape(data, success_key="success_ids")
        assert data["fail_count"] == 1
        fail = data["fail_items"][0]
        assert fail["error_code"] == "DAMAGED_ASSET_NOT_FOUND"
        assert fail["error_message"] == "待报废记录 NO_SUCH 不存在"
        assert resp.data["message"] == "批量删除完成,成功 0 条,失败 1 条"


@pytest.mark.django_db
class TestWasteBaseline:
    def test_batch_delete_missing_id_after_dr1(
        self, admin_client_fixture, storage, asset_type
    ):
        """[已变更 commit e85b6cf+本次] WASTE_ASSET_NOT_FOUND 不再被遮蔽为 INTERNAL_ERROR"""
        import datetime as _dt

        from apps.assetmanagement.models import Asset

        Asset.objects.create(
            asset_code="W_BASE_1", asset_name="基线资产",
            asset_purchase_price=1, asset_type_recordcode=asset_type,
            asset_storage_recordcode=storage,
            asset_purchase_date=_dt.date.today(),
            asset_entry_date=_dt.date.today(),
        )
        url = reverse("waste-assets-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": ["W_BASE_1"]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        _assert_batch_shape(data, success_key="success_ids")
        assert data["fail_count"] == 1
        fail = data["fail_items"][0]
        # 迁移后: 透传 Service 原生错误码(比原计划的 NOT_FOUND 更精确)
        assert fail["error_code"] == "WASTE_ASSET_NOT_FOUND"
        assert fail["error_message"] == "已报废记录 W_BASE_1 不存在"


@pytest.mark.django_db
class TestManyVsItemwiseEquivalence:
    """B-5 Commit 3 前置证明: many=True 与逐条序列化输出等价(AssetTypeSerializer)"""

    def test_many_equals_itemwise(self, asset_type):
        from apps.assetmanagement.serializers import AssetTypeSerializer

        items = [asset_type, asset_type]
        many_output = AssetTypeSerializer(items, many=True).data
        itemwise_output = [AssetTypeSerializer(item).data for item in items]
        assert many_output == itemwise_output
