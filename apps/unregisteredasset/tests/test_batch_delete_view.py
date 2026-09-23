"""
未登记资产批量删除端点(views.batch_delete)直接行为测试

BR-4 B2 拆分前补充的 CT-4 回归锚:锁定 batch_delete 的成功路径、
四种失败结构(NOT_FOUND/STATUS_NOT_ALLOWED/VALIDATION_ERROR/INTERNAL_ERROR)
与权限门禁,防止拆分/下沉 Service 时行为走样。
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.services import UnregisteredAssetService
from core.exceptions import AppValidationError


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def admin_client_fixture(api_client, admin_auth_user):
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


@pytest.fixture
def regular_client(api_client, auth_user):
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.mark.django_db
class TestUnregisteredBatchDeleteView:
    def _url(self) -> str:
        return reverse("unregisteredasset:unregisteredasset-batch-delete")

    def test_batch_delete_empty_ids_returns_noop_200(self, admin_client_fixture):
        resp = admin_client_fixture.post(self._url(), {"ids": []}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert data["total"] == 0
        assert data["success_count"] == 0
        assert data["fail_count"] == 0

    def test_batch_delete_success(self, admin_client_fixture, unregistered_asset_s1):
        code = unregistered_asset_s1.unregistered_code
        resp = admin_client_fixture.post(self._url(), {"ids": [code]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert data["fail_count"] == 0
        assert data["success_ids"] == [code]
        assert data["fail_items"] == []
        assert UnregisteredAsset.objects.filter(unregistered_code=code).count() == 0
        assert UnregisteredAsset.all_objects.filter(unregistered_code=code).count() == 1

    def test_batch_delete_status_not_allowed(self, admin_client_fixture, unregistered_asset_s1):
        code = unregistered_asset_s1.unregistered_code
        UnregisteredAsset.objects.filter(unregistered_code=code).update(approval_status="approved")
        resp = admin_client_fixture.post(self._url(), {"ids": [code]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        data = resp.data["data"]
        assert data["success_count"] == 0
        assert data["fail_count"] == 1
        fail = data["fail_items"][0]
        assert fail["id"] == code
        assert fail["error_code"] == "STATUS_NOT_ALLOWED"
        assert "不允许删除" in fail["error_message"]

    def test_batch_delete_validation_error(self, admin_client_fixture, unregistered_asset_s1, monkeypatch):
        code = unregistered_asset_s1.unregistered_code

        def raising_delete(unregistered_code, operator_jobcode, operator_name=None):
            raise AppValidationError(detail="模拟验证失败")

        monkeypatch.setattr(UnregisteredAssetService, "delete", staticmethod(raising_delete))

        resp = admin_client_fixture.post(self._url(), {"ids": [code]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        fail = resp.data["data"]["fail_items"][0]
        assert fail["id"] == code
        assert fail["error_code"] == "VALIDATION_ERROR"
        assert fail["error_message"] == "模拟验证失败"

    def test_batch_delete_internal_error(self, admin_client_fixture, unregistered_asset_s1, monkeypatch):
        code = unregistered_asset_s1.unregistered_code

        def raising_delete(unregistered_code, operator_jobcode, operator_name=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(UnregisteredAssetService, "delete", staticmethod(raising_delete))

        resp = admin_client_fixture.post(self._url(), {"ids": [code]}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        fail = resp.data["data"]["fail_items"][0]
        assert fail["id"] == code
        assert fail["error_code"] == "INTERNAL_ERROR"
        assert fail["error_message"] == "服务器内部错误,请稍后重试"

    def test_batch_delete_mixed_success_and_fail(
        self, admin_client_fixture, unregistered_asset_s1, storage, asset_type, employee
    ):
        ok_code = unregistered_asset_s1.unregistered_code
        blocked = UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date="2024-06-02",
            discovery_location="会议室B",
            discovery_person=employee,
            asset_name="已审批阻断资产",
            unregistered_asset_type=asset_type,
            estimated_value=1000,
            unregistered_asset_storage=storage,
            approval_status="approved",
        )
        blocked_code = blocked.unregistered_code

        resp = admin_client_fixture.post(self._url(), {"ids": [ok_code, blocked_code]}, format="json")

        data = resp.data["data"]
        assert data["success_count"] == 1
        assert data["fail_count"] == 1
        assert data["success_ids"] == [ok_code]
        assert data["fail_items"][0]["id"] == blocked_code
        assert data["fail_items"][0]["error_code"] == "STATUS_NOT_ALLOWED"

    def test_batch_delete_requires_admin(self, regular_client, unregistered_asset_s1):
        resp = regular_client.post(self._url(), {"ids": [unregistered_asset_s1.unregistered_code]}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
