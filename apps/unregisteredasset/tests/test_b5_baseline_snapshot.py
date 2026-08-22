"""
unregisteredasset 批量端点基线快照（B-5 Commit 0）

锁定该独立 app 的差异化契约(与其他端点根本不同, 不参与 B-5 收敛):
- 超限返回 400 即时拒绝(而非 200+fail_items)
- 失败条目错误码为 CREATE_FAILED(单码制)
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def admin_client_fixture(api_client, admin_auth_user):
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


@pytest.mark.django_db
class TestUnregisteredBatchBaseline:
    def _url(self, action: str) -> str:
        return reverse(f"unregisteredasset:unregisteredasset-{action}")

    def test_batch_create_oversize_returns_400(self, admin_client_fixture):
        """[契约差异-保留] 超限契约: 400 即时拒绝, 不同于标准端点的 200+fail_items"""
        items = [{"asset_name": f"x{i}"} for i in range(101)]
        resp = admin_client_fixture.post(self._url("batch-create"), {"items": items}, format="json")
        # 【B-10 已修复】原状: error_response 误用 data= 参数致 TypeError -> 500
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["message"] == "单次批量创建不能超过 100 条"

    def test_batch_create_fail_item_after_dr1(self, admin_client_fixture):
        """[已变更 本次] CREATE_FAILED 单码制消灭, 异常分层透传注册错误码"""
        # 缺必填字段的条目 → DRF 校验失败 → AppValidationError/ValidationError 分支
        resp = admin_client_fixture.post(
            self._url("batch-create"),
            {"items": [{"asset_name": "缺字段条目"}]},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert set(data.keys()) == {
            "total", "success_count", "fail_count", "success_items", "fail_items",
        }
        assert data["fail_count"] == 1
        fail = data["fail_items"][0]
        assert set(fail.keys()) == {"index", "error_code", "error_message", "input_data"}
        assert fail["error_code"] not in ("CREATE_FAILED", "INTERNAL_ERROR")
        assert fail["input_data"] == {"asset_name": "缺字段条目"}

    def test_batch_delete_missing_id(self, admin_client_fixture):
        """batch_delete: 不存在记录的 fail 结构"""
        resp = admin_client_fixture.post(
            self._url("batch-delete"), {"ids": ["UNR-NOTEXIST"]}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert data["fail_count"] == 1
        assert data["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_delete_oversize_returns_400(self, admin_client_fixture):
        """[契约差异-保留] 超限契约: 400 即时拒绝"""
        resp = admin_client_fixture.post(
            self._url("batch-delete"), {"ids": [f"UNR-{i}" for i in range(101)]}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
