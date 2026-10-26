"""
批次 C 修复验证测试 (M-06/07/08/09/10)

覆盖:
- M-06: out_asset TOCTOU 前态锁内重读
- M-07: move_department 旧祖先链缓存失效
- M-08: refresh_tokens 并发竞态 IntegrityError 门
- M-09: resolve_viewset_permissions fail-closed 未登记 action
- M-10: JWT_AUTH_COOKIE_SECURE 缺省 True
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework import permissions
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.services import AuthService
from apps.usermanagement.models import Department
from apps.usermanagement.services import DepartmentService
from core.permissions import IsAssetAdminOrAbove, IsSystemAdmin, resolve_viewset_permissions
from core.tests import TEST_PASSWORD


# ── M-10: JWT_AUTH_COOKIE_SECURE 缺省 True ──────────────────────────────────


class TestM10CookieSecureDefault:
    """M-10: base.py 缺省 JWT_AUTH_COOKIE_SECURE=True, development/test 显式 opt-out"""

    def test_base_default_is_true_in_source(self):
        """base.py 源码中 JWT_AUTH_COOKIE_SECURE 缺省 default=True"""
        import inspect

        from config.settings import base

        source = inspect.getsource(base)
        assert 'JWT_AUTH_COOKIE_SECURE = config("JWT_AUTH_COOKIE_SECURE", default=True, cast=bool)' in source

    def test_development_opts_out(self):
        """development.py 显式 opt-out 为 False"""
        import inspect

        from config.settings import development

        source = inspect.getsource(development)
        assert "JWT_AUTH_COOKIE_SECURE = False" in source

    def test_test_opts_out(self):
        """test.py 显式 opt-out 为 False"""
        import inspect

        from config.settings import test

        source = inspect.getsource(test)
        assert "JWT_AUTH_COOKIE_SECURE = False" in source


# ── M-09: resolve_viewset_permissions fail-closed ────────────────────────────


class TestM09PermissionFailClosed:
    """M-09: admin_actions 非空时, 未登记 action 遇写方法(或方法未知)缺省返回 admin_permission"""

    def test_unregistered_write_action_returns_admin_permission(self):
        """未登记 action + 写方法(POST) → admin_permission (非 IsAuthenticated)"""
        result = resolve_viewset_permissions(
            "some_new_action",
            admin_actions=["create", "destroy"],
            admin_permission=IsSystemAdmin,
            method="POST",
        )
        assert isinstance(result[0], IsSystemAdmin)

    def test_unregistered_write_action_lowercased_method(self):
        """方法小写(post)同样命中 fail-closed (方法比较大小写不敏感)"""
        result = resolve_viewset_permissions(
            "some_new_action",
            admin_actions=["create"],
            admin_permission=IsSystemAdmin,
            method="post",
        )
        assert isinstance(result[0], IsSystemAdmin)

    def test_unregistered_action_method_unknown_fails_closed(self):
        """方法未知(method=None, 如 schema 生成期) → fail-closed 用 admin_permission"""
        result = resolve_viewset_permissions(
            "some_new_action",
            admin_actions=["create"],
            admin_permission=IsSystemAdmin,
            method=None,
        )
        assert isinstance(result[0], IsSystemAdmin)

    def test_unregistered_get_action_still_authenticated(self):
        """未登记 action + 读方法(GET) → 读面语义不变, 缺省 IsAuthenticated"""
        result = resolve_viewset_permissions(
            "by_asset",
            admin_actions=["create", "destroy"],
            admin_permission=IsSystemAdmin,
            method="GET",
        )
        assert isinstance(result[0], permissions.IsAuthenticated)

    def test_list_still_authenticated(self):
        """list action + GET 缺省保持 IsAuthenticated"""
        result = resolve_viewset_permissions(
            "list",
            admin_actions=["create", "destroy"],
            admin_permission=IsSystemAdmin,
            method="GET",
        )
        assert isinstance(result[0], permissions.IsAuthenticated)

    def test_retrieve_still_authenticated(self):
        """retrieve action + GET 缺省保持 IsAuthenticated"""
        result = resolve_viewset_permissions(
            "retrieve",
            admin_actions=["create", "destroy"],
            admin_permission=IsSystemAdmin,
            method="GET",
        )
        assert isinstance(result[0], permissions.IsAuthenticated)

    def test_registered_action_returns_admin_permission(self):
        """已登记 action → admin_permission, 与方法无关 (原行为不变)"""
        result = resolve_viewset_permissions(
            "create",
            admin_actions=["create", "destroy"],
            admin_permission=IsSystemAdmin,
            method="POST",
        )
        assert isinstance(result[0], IsSystemAdmin)

    def test_empty_admin_actions_write_fails_closed(self):
        """【M-49 方案B】admin_actions 为空 + 写方法 → admin_permission, 与是否为空无关
        (空清单原缺省 IsAuthenticated 的越权窗口已封堵)"""
        result = resolve_viewset_permissions(
            "some_action",
            admin_actions=[],
            admin_permission=IsSystemAdmin,
            method="POST",
        )
        assert isinstance(result[0], IsSystemAdmin)

    def test_empty_admin_actions_read_stays_authenticated(self):
        """【M-49 读路径屏障】admin_actions 为空 + 读方法 → 仍缺省 IsAuthenticated, 读面语义不变"""
        result = resolve_viewset_permissions(
            "some_action",
            admin_actions=[],
            admin_permission=IsSystemAdmin,
            method="GET",
        )
        assert isinstance(result[0], permissions.IsAuthenticated)

    def test_action_overrides_still_wins(self):
        """action_overrides 优先级最高, 不受 fail-closed 影响(写方法下仍按显式映射)"""
        result = resolve_viewset_permissions(
            "change_status",
            admin_actions=["create"],
            admin_permission=IsSystemAdmin,
            action_overrides={"change_status": IsAssetAdminOrAbove},
            method="POST",
        )
        assert isinstance(result[0], IsAssetAdminOrAbove)

    def test_export_excel_still_wins(self):
        """export_excel 优先级最高"""
        from core.permissions import CanExportExcel

        result = resolve_viewset_permissions(
            "export_excel",
            admin_actions=["create"],
            admin_permission=IsSystemAdmin,
            method="GET",
        )
        assert isinstance(result[0], CanExportExcel)

    def test_request_method_reads_view_request(self):
        """request_method: dispatch 期取真实方法, request 缺省(schema 生成期)返回 None"""
        from types import SimpleNamespace

        from core.permissions import request_method

        view = SimpleNamespace(request=SimpleNamespace(method="DELETE"))
        assert request_method(view) == "DELETE"
        assert request_method(SimpleNamespace(request=None)) is None
        assert request_method(SimpleNamespace()) is None


# ── M-08: refresh_tokens 并发竞态 ───────────────────────────────────────────


@pytest.mark.django_db
class TestM08RefreshRace:
    """M-08: refresh_tokens 轮换+黑名单原子执行, IntegrityError → TokenError"""

    def _make_user_and_refresh(self):
        user = AuthUser.objects.create_user(
            auth_username="raceuser",
            password=TEST_PASSWORD,
            email="",
            auth_phone="",
            auth_is_active=True,
            auth_is_staff=False,
        )
        return AuthService.issue_tokens(user)["refresh"]

    def test_refresh_integrity_error_raises_token_error(self, db):
        """blacklist() 抛 IntegrityError 时转换为 TokenError"""
        refresh = self._make_user_and_refresh()

        with (
            patch.object(RefreshToken, "blacklist", side_effect=IntegrityError("duplicate key")),
            patch(
                "apps.authusermanagement.services.settings.SIMPLE_JWT",
                {"ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True},
            ),
        ):
            with pytest.raises(TokenError, match="并发刷新冲突"):
                AuthService.refresh_tokens(refresh)

    def test_refresh_success_path_non_rotation(self, db):
        """正常刷新路径(非轮换)不抛异常"""
        refresh = self._make_user_and_refresh()

        # test.py 默认 ROTATE_REFRESH_TOKENS=False, 走 else 分支
        data = AuthService.refresh_tokens(refresh)
        assert "access" in data
        assert "refresh" in data


# ── M-07: move_department 旧祖先链缓存失效 ──────────────────────────────────


@pytest.mark.django_db
class TestM07DepartmentCacheInvalidation:
    """M-07: move_department 后旧祖先链的 descendants 缓存必须失效"""

    def test_move_invalidates_old_ancestor_cache(self, db):
        """移动部门后, 旧祖先的 descendants 缓存被清除"""
        # 构建: root_a -> child_b -> grandchild_c
        root_a = Department.objects.create(
            department_code="M7ROOT", department_name="根A", department_information="", level=0, path="/M7ROOT"
        )
        Department.objects.create(
            department_code="M7CHILD",
            department_name="子B",
            department_information="",
            parent=root_a,
            level=1,
            path="/M7ROOT/M7CHILD",
        )
        grandchild_c = Department.objects.create(
            department_code="M7GC",
            department_name="孙C",
            department_information="",
            parent=Department.objects.get(department_code="M7CHILD"),
            level=2,
            path="/M7ROOT/M7CHILD/M7GC",
        )

        # 预热 root_a 的 descendants 缓存
        _ = root_a.get_all_descendants()
        cache_key = f"dept:{root_a.recordcode}:descendants"
        assert cache.get(cache_key) is not None

        # 移动 child_b 到另一个根部门
        Department.objects.create(
            department_code="M7NEWROOT", department_name="新根", department_information="", level=0, path="/M7NEWROOT"
        )
        DepartmentService.move_department("M7CHILD", "M7NEWROOT")

        # 旧祖先 root_a 的缓存必须已失效
        assert cache.get(cache_key) is None

        # grandchild_c 的 path 应已更新
        grandchild_c.refresh_from_db()
        assert grandchild_c.path == "/M7NEWROOT/M7CHILD/M7GC"

    def test_move_to_root_invalidates_old_ancestor_cache(self, db):
        """移动为根部门时, 旧祖先缓存也失效"""
        root_a = Department.objects.create(
            department_code="M7R2", department_name="根", department_information="", level=0, path="/M7R2"
        )
        Department.objects.create(
            department_code="M7C2",
            department_name="子",
            department_information="",
            parent=root_a,
            level=1,
            path="/M7R2/M7C2",
        )

        _ = root_a.get_all_descendants()
        cache_key = f"dept:{root_a.recordcode}:descendants"
        assert cache.get(cache_key) is not None

        DepartmentService.move_department("M7C2", None)

        assert cache.get(cache_key) is None


# ── M-06: out_asset TOCTOU 前态锁内重读 ──────────────────────────────────────


@pytest.mark.django_db
class TestM06OutAssetTOCTOU:
    """M-06: _apply_outasset_to_asset 锁内重读前态并更新 outasset"""

    def _make_asset(self, db):
        from apps.assetmanagement.models import Asset, AssetType, Storage
        from apps.usermanagement.models import Employee

        storage = Storage.objects.create(storage_name="M6仓库")
        asset_type = AssetType.objects.create(type_code="M6TYPE", type_name="M6类型")
        department = Department.objects.create(department_code="M6DEPT", department_name="M6部门")
        user = Employee.objects.create(
            employee_jobcode="M6U001", employee_name="M6用户", employee_department=department
        )
        return Asset.objects.create(
            asset_name="M6测试资产",
            asset_code="M6-001",
            asset_purchase_price=1000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_entry_person_recordcode=user,
            asset_current_status=Asset.AssetStatus.IN_STORE,
        )

    def test_apply_updates_previous_status_inside_lock(self, db):
        """锁内前态重读: outasset.outasset_previous_status 以锁内读到的为准"""
        from apps.assetmanagement.models import Asset, OutAsset
        from apps.assetmanagement.services.out_asset_service import OutAssetService

        asset = self._make_asset(db)
        outasset = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_type="领用",
            outasset_previous_status=Asset.AssetStatus.IN_STORE,  # 锁前捕获
        )

        # 模拟并发: 在 _apply_outasset_to_asset 执行前, 资产状态已被改为 recycled_pending
        # 但 outasset.outasset_previous_status 仍是 in_store (锁前捕获的旧值)
        asset.asset_current_status = Asset.AssetStatus.RECYCLED_PENDING
        asset.save(update_fields=["asset_current_status"])

        # 调用 _apply_outasset_to_asset, 锁内应重读并更新 outasset.previous_status
        updated_asset = OutAssetService._apply_outasset_to_asset(asset, None, None, None, outasset)

        # outasset.previous_status 应已被锁内重读的值覆盖
        outasset.refresh_from_db()
        assert outasset.outasset_previous_status == Asset.AssetStatus.RECYCLED_PENDING
        # 资产状态已转为 in_use (出库后)
        assert updated_asset.asset_current_status == Asset.AssetStatus.IN_USE

    def test_apply_without_outasset_param_backward_compat(self, db):
        """不传 outasset 参数时保持原行为(向后兼容)"""
        from apps.assetmanagement.models import Asset
        from apps.assetmanagement.services.out_asset_service import OutAssetService

        asset = self._make_asset(db)

        updated = OutAssetService._apply_outasset_to_asset(asset, None, None, None)
        assert updated.asset_current_status == Asset.AssetStatus.IN_USE
