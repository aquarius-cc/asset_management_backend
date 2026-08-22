"""
B-5 治理基线快照（Commit 0）

锁定 8 个未迁移批量端点的【当前】响应结构,作为 DR-1 收敛的行为基线:
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
    def test_batch_delete_missing_id_current_behavior(self, admin_client_fixture):
        """[将变更] 现状: AppValidationError 被写死为 VALIDATION_ERROR + str(e)"""
        url = reverse("damaged-assets-batch-delete")
        resp = admin_client_fixture.post(url, {"ids": ["NO_SUCH"]}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        _assert_batch_shape(data, success_key="success_ids")
        assert data["fail_count"] == 1
        fail = data["fail_items"][0]
        assert fail["error_code"] == "VALIDATION_ERROR"  # [将变更] → 透传 e.error_code
        assert "服务器内部错误" not in fail["error_message"]
        assert resp.data["message"] == "批量删除完成,成功 0 条,失败 1 条"


@pytest.mark.django_db
class TestWasteBaseline:
    def test_batch_delete_missing_id_current_behavior(
        self, admin_client_fixture, storage, asset_type
    ):
        """[将变更] 现状: Service 抛 WASTE_ASSET_NOT_FOUND 但被遮蔽为 INTERNAL_ERROR"""
        from apps.assetmanagement.models import Asset

        import datetime as _dt

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
        # [将变更] 现状: 无 AppValidationError 分支, WASTE_ASSET_NOT_FOUND 被遮蔽
        assert fail["error_code"] == "INTERNAL_ERROR"
        assert fail["error_message"] == "服务器内部错误"
