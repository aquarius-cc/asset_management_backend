"""
BatchDeleteViewMixin 骨架单测(批次③落地契约)

锁定全仓批删视图统一行为:
  1. 空 ids → 200 全零 noop(前端已有禁用态双层防护, 400 契约已废止)
  2. batch_delete_prefilter 钩子生效(ids 透传前可改写)
  3. 默认 passes_user=False 时不传 user, 仅传 operator
  4. passes_user=True + 覆写 batch_delete_invoke 注入 user 可透传
"""

from typing import Any

import pytest
from rest_framework import serializers

from apps.authusermanagement.models import AuthUser
from core.batch_mixins import BaseBatchDeleteSerializer, BatchDeleteViewMixin


class _StubDeleteSerializer(BaseBatchDeleteSerializer):
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="stub ids")


class _FakeRequest:
    def __init__(self, data: dict[str, Any], user: Any) -> None:
        self.data = data
        self.user = user


class _StubView(BatchDeleteViewMixin):
    batch_delete_serializer = _StubDeleteSerializer
    batch_delete_service = staticmethod(
        lambda ids, **kw: {
            "total": len(ids),
            "success_count": len(ids),
            "fail_count": 0,
            "success_ids": list(ids),
            "fail_items": [],
        }
    )


@pytest.mark.django_db
class TestBatchDeleteViewMixin:
    def _view(self) -> _StubView:
        return _StubView()

    def _request(self, ids, user) -> _FakeRequest:
        return _FakeRequest({"ids": ids}, user)

    def test_empty_ids_returns_noop_200(self) -> None:
        view = self._view()
        resp = view.batch_delete(self._request([], AuthUser.objects.create_user(auth_username="OP001")))
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["total"] == 0
        assert data["success_count"] == 0
        assert data["fail_count"] == 0

    def test_prefilter_hook_transforms_ids(self) -> None:
        class FilteredView(_StubView):
            def batch_delete_prefilter(self, ids, request):  # type: ignore[override]
                return ["prefiltered"]

        captured: dict[str, Any] = {}

        def service(ids, **kw):
            captured["ids"] = ids
            return {
                "total": len(ids),
                "success_count": len(ids),
                "fail_count": 0,
                "success_ids": list(ids),
                "fail_items": [],
            }

        view = FilteredView()
        view.batch_delete_service = service  # type: ignore[assignment]
        resp = view.batch_delete(self._request(["raw-1", "raw-2"], AuthUser.objects.create_user(auth_username="OP002")))
        assert resp.status_code == 200
        assert captured["ids"] == ["prefiltered"]
        assert resp.data["data"]["total"] == 1

    def test_default_no_user_kwarg_only_operator(self) -> None:
        user = AuthUser.objects.create_user(auth_username="OP003")
        captured: dict[str, Any] = {}

        def service(ids, **kw):
            captured.update(kw)
            return {
                "total": len(ids),
                "success_count": len(ids),
                "fail_count": 0,
                "success_ids": list(ids),
                "fail_items": [],
            }

        view = _StubView()
        view.batch_delete_service = service  # type: ignore[assignment]
        view.batch_delete(self._request(["A"], user))
        assert captured["operator_jobcode"] == "OP003"
        assert captured["operator_name"] == "OP003"
        assert "user" not in captured

    def test_passes_user_and_invoke_injects_user(self) -> None:
        user = AuthUser.objects.create_user(auth_username="OP004")
        captured: dict[str, Any] = {}

        class UserView(_StubView):
            batch_delete_passes_user = True

            def batch_delete_invoke(self, ids, **kw):  # type: ignore[override]
                captured["injected_user"] = kw["user"]
                return super().batch_delete_invoke(ids, **kw)

        view = UserView()
        view.batch_delete_service = lambda ids, **kw: {
            "total": len(ids),
            "success_count": len(ids),
            "fail_count": 0,
            "success_ids": list(ids),
            "fail_items": [],
        }
        view.batch_delete(self._request(["B"], user))
        assert isinstance(captured["injected_user"], AuthUser)
        assert captured["injected_user"] == user
