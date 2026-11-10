"""
出库 Service 层单元测试(CT-1: out_asset_service 核心业务逻辑独立单测)

覆盖审查报告 #14 所列缺口:
- create_outasset 状态守卫、快照(original_*)构建落库
- 出库后资产状态流转 in_use、仓库清空、usage_type new→used (AC-27 / F-P2-9)
- 非法源状态 ILLEGAL_OUTASSET
- 取消出库(batch_delete_outasset)快照恢复契约
- 批量方法 fail_items 结构
- 行锁超时 409 ASSET_LOCKED(AC-30/65 / F-P2-8): 单条 create 与 cancel 批量路径
"""

from unittest import mock

import pytest
from django.db import OperationalError

from apps.assetmanagement.models import Asset, OutAsset
from apps.assetmanagement.selectors.out_asset_selector import OutAssetSelector
from apps.assetmanagement.services.out_asset_service import OutAssetService
from apps.usermanagement.models import Department, Employee
from core.exceptions import AppValidationError, ResourceConflictError


def _make_asset(
    storage,
    asset_type,
    status,
    code,
    applicant=None,
    manager=None,
    using_location=None,
):
    return Asset.objects.create(
        asset_code=code,
        asset_name="出库Service测试",
        asset_purchase_price=2000,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-01",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status=status,
        asset_applicant_recordcode=applicant,
        asset_manager_recordcode=manager,
        asset_using_location=using_location,
    )


def _outasset_payload(asset, applicant=None, manager=None, using_location="出库地点"):
    return {
        "asset_recordcode": asset,
        "outasset_date": "2024-03-01",
        "outasset_type": "receive",
        "outasset_applicant": applicant,
        "outasset_manager": manager,
        "outasset_using_location": using_location,
    }


@pytest.mark.django_db
class TestCreateOutAssetService:
    """create_outasset:状态守卫 + 快照构建落库"""

    @pytest.mark.parametrize(
        ("source_status", "expected_previous"),
        [("in_store", "in_store"), ("recycled_pending", "recycled_pending")],
    )
    def test_create_success_records_previous_status_and_snapshot(
        self, storage, asset_type, employee, source_status, expected_previous, full_scope_user
    ):
        asset = _make_asset(
            storage,
            asset_type,
            source_status,
            f"OUT_SVC_OK_{source_status[0].upper()}",
            applicant=employee,
            manager=employee,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )

        assert outasset.outasset_previous_status == expected_previous
        assert outasset.outasset_using_location == "出库地点"

        snapshot = outasset.outasset_snapshot
        assert snapshot["original_applicant"]["jobcode"] == employee.employee_jobcode
        assert snapshot["original_manager"]["jobcode"] == employee.employee_jobcode
        assert snapshot["original_using_location"] == "原地点"
        assert snapshot["asset_storage_recordcode"] == storage.recordcode

        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        assert asset.asset_storage_recordcode is None
        assert asset.asset_applicant_recordcode == employee
        assert asset.asset_using_location == "出库地点"

    def test_create_from_illegal_status_raises(self, storage, asset_type, employee, full_scope_user):
        asset = _make_asset(storage, asset_type, "in_use", "OUT_SVC_ILLEGAL")
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(_outasset_payload(asset, applicant=employee), user=full_scope_user)
        assert exc_info.value.error_code == "ILLEGAL_OUTASSET"

    def test_create_missing_asset_code_raises(self, storage, asset_type, full_scope_user):
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset({}, user=full_scope_user)
        assert exc_info.value.error_code == "MISSING_ASSET_CODE"


@pytest.mark.django_db
class TestOutAssetLockAndUsageType:
    """F-P2-8/F-P2-9: 出库行锁409 + usage_type new→used (AC-27/30/65)"""

    def test_create_outasset_lock_timeout_raises_409(self, storage, asset_type, employee, full_scope_user):
        """AC-30/65: 出库行锁超时 → ResourceConflictError(409) ASSET_LOCKED"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_LK409")
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("database is locked"),
        ):
            with pytest.raises(ResourceConflictError) as exc:
                OutAssetService.create_outasset(
                    _outasset_payload(asset, applicant=employee),
                    operator_jobcode=employee.employee_jobcode,
                    user=full_scope_user,
                )
        assert exc.value.status_code == 409
        assert exc.value.error_code == "ASSET_LOCKED"

    def test_create_outasset_flips_usage_type_to_used(self, storage, asset_type, employee, full_scope_user):
        """AC-27: 出库成功后 usage_type new→used (F-P2-9); fresh query 避开 FK 缓存"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_USED")
        assert asset.usage_type == "new"
        OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        fresh = Asset.objects.get(asset_code=asset.asset_code)
        assert fresh.usage_type == "used"

    def test_cancel_outasset_lock_timeout_lands_in_fail_items(
        self, storage, asset_type, user, employee, full_scope_user
    ):
        """AC-65: cancel 行锁超时 → fail_items ASSET_LOCKED,不落 INTERNAL_ERROR/500"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_CLK")
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("database is locked"),
        ):
            result = OutAssetService.batch_delete_outasset(
                [outasset.recordcode], operator_jobcode=user.employee_jobcode, user=full_scope_user
            )
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_LOCKED"

    def test_update_outasset_lock_timeout_raises_409(self, storage, asset_type, user, employee, full_scope_user):
        """F-P2-8 续:update 单条路径 OutAsset 行锁超时 → 真 409 ASSET_LOCKED(select_for_update().get 经 guard)"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_UP_409")
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        qs_type = type(OutAsset.objects.select_for_update())
        orig_get = qs_type.get
        error = OperationalError("database is locked")

        def fake_get(self, *args, **kwargs):
            if getattr(self.query, "select_for_update", False):
                raise error
            return orig_get(self, *args, **kwargs)

        with mock.patch.object(qs_type, "get", autospec=True, side_effect=fake_get):
            with pytest.raises(ResourceConflictError) as exc:
                OutAssetService.update_outasset(outasset.recordcode, {"outasset_using_location": "更新地点"}, user=user)
        assert exc.value.status_code == 409
        assert exc.value.error_code == "ASSET_LOCKED"

    def test_batch_delete_guard_lock_timeout_raises_409(self, storage, asset_type, user, employee, full_scope_user):
        """F-P2-8 续:批量删除守卫(get_outasset_for_update)锁超时 → Selector 抛 409 ASSET_LOCKED"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_GUARD409")
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        with mock.patch.object(
            type(OutAsset.objects.select_for_update()),
            "first",
            side_effect=OperationalError("database is locked"),
        ):
            with pytest.raises(ResourceConflictError) as exc:
                OutAssetSelector.get_outasset_for_update(outasset.recordcode)
        assert exc.value.status_code == 409
        assert exc.value.error_code == "ASSET_LOCKED"

    def test_batch_delete_mixed_guard_conflict_routes_to_fail_items(
        self, storage, asset_type, user, employee, full_scope_user
    ):
        """F-P2-8 续:批量删除混合批——一条关联资产锁超时→fail_items ASSET_LOCKED,其余正常取消"""
        ok_asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_MIX_OK")
        boom_asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_MIX_BM")
        ok_out = OutAssetService.create_outasset(
            _outasset_payload(ok_asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        boom_out = OutAssetService.create_outasset(
            _outasset_payload(boom_asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=full_scope_user,
        )
        qs_type = type(Asset.objects.select_for_update())
        orig_get = qs_type.get
        error = OperationalError("database is locked")

        def fake_get(self, *args, **kwargs):
            if getattr(self.query, "select_for_update", False) and kwargs.get("pk") == boom_asset.pk:
                raise error
            return orig_get(self, *args, **kwargs)

        with mock.patch.object(qs_type, "get", autospec=True, side_effect=fake_get):
            result = OutAssetService.batch_delete_outasset(
                [ok_out.recordcode, boom_out.recordcode],
                operator_jobcode=user.employee_jobcode,
                user=full_scope_user,
            )
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_LOCKED"

        ok_asset.refresh_from_db()
        boom_asset.refresh_from_db()
        assert ok_asset.asset_current_status == "in_store"
        assert boom_asset.asset_current_status == "in_use"

    def test_guard_reraises_non_lock_operational_error(self, storage, asset_type, employee, full_scope_user):
        """F-P2-8 续:非锁类 OperationalError(不含 lock)不被吞,原样 re-raise"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_SVC_RELK")
        with mock.patch.object(
            type(Asset.objects.select_for_update()),
            "get",
            side_effect=OperationalError("connection reset by peer"),
        ):
            with pytest.raises(OperationalError):
                OutAssetService.create_outasset(
                    _outasset_payload(asset, applicant=employee),
                    operator_jobcode=employee.employee_jobcode,
                    user=full_scope_user,
                )


@pytest.mark.django_db
class TestCancelOutAssetService:
    """取消出库(batch_delete_outasset):快照 original_* 恢复核心契约"""

    def test_cancel_restores_original_fields(self, storage, asset_type, user, employee, full_scope_user):
        asset = _make_asset(
            storage,
            asset_type,
            "in_store",
            "OUT_SVC_CNL_1",
            applicant=user,
            manager=user,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee, using_location="出库地点"),
            user=full_scope_user,
        )

        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode == employee
        assert asset.asset_using_location == "出库地点"
        assert asset.asset_current_status == "in_use"
        assert asset.asset_storage_recordcode is None

        result = OutAssetService.batch_delete_outasset(
            [outasset.recordcode], operator_jobcode=user.employee_jobcode, user=full_scope_user
        )
        assert result["success_count"] == 1

        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"
        assert asset.asset_storage_recordcode == storage
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_manager_recordcode == user
        assert asset.asset_using_location == "原地点"
        assert asset.usage_type == "used"  # F-P2-9 回归锚:取消出库不还原 usage_type

    def test_cancel_from_recycled_pending_not_restore_storage(
        self, storage, asset_type, user, employee, full_scope_user
    ):
        asset = _make_asset(
            storage,
            asset_type,
            "recycled_pending",
            "OUT_SVC_CNL_2",
            applicant=user,
            manager=user,
            using_location="原地点",
        )
        outasset = OutAssetService.create_outasset(_outasset_payload(asset, applicant=employee), user=full_scope_user)

        asset.refresh_from_db()
        assert asset.asset_storage_recordcode is None

        result = OutAssetService.batch_delete_outasset(
            [outasset.recordcode], operator_jobcode=user.employee_jobcode, user=full_scope_user
        )
        assert result["success_count"] == 1

        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"
        assert asset.asset_storage_recordcode is None
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_using_location == "原地点"


@pytest.mark.django_db
class TestBatchOutAssetService:
    """批量方法 fail_items 结构(CT-4 回归护栏)"""

    def test_batch_create_fail_items_structure(self, storage, asset_type, employee, full_scope_user):
        valid = _make_asset(storage, asset_type, "in_store", "OUT_SVC_BC_OK")
        illegal = _make_asset(storage, asset_type, "in_use", "OUT_SVC_BC_ILL")
        result = OutAssetService.batch_create_outasset(
            [_outasset_payload(valid, applicant=employee), _outasset_payload(illegal, applicant=employee)],
            user=full_scope_user,
        )
        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ILLEGAL_OUTASSET"
        valid.refresh_from_db()
        illegal.refresh_from_db()
        assert valid.asset_current_status == "in_use"  # 首条成功:批量独立性
        assert illegal.asset_current_status == "in_use"  # 失败条保持原状

    def test_batch_delete_fail_items_structure(self, storage, asset_type, employee, full_scope_user):
        result = OutAssetService.batch_delete_outasset(
            ["OUT-NOT-EXIST-123"], operator_jobcode=employee.employee_jobcode, user=full_scope_user
        )
        assert result["total"] == 1
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["id"] == "OUT-NOT-EXIST-123"
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_create_lock_timeout_lands_in_fail_items(self, storage, asset_type, employee, full_scope_user):
        """F-P2-8 续:批量创建混合批——一条资产锁超时→fail_items ASSET_LOCKED,其余成功"""
        ok = _make_asset(storage, asset_type, "in_store", "OUT_SVC_BCLK_OK")
        boom = _make_asset(storage, asset_type, "in_store", "OUT_SVC_BCLK_BM")
        qs_type = type(Asset.objects.select_for_update())
        orig_get = qs_type.get
        error = OperationalError("database is locked")

        def fake_get(self, *args, **kwargs):
            if getattr(self.query, "select_for_update", False) and kwargs.get("pk") == boom.pk:
                raise error
            return orig_get(self, *args, **kwargs)

        with mock.patch.object(qs_type, "get", autospec=True, side_effect=fake_get):
            result = OutAssetService.batch_create_outasset(
                [
                    _outasset_payload(ok, applicant=employee),
                    _outasset_payload(boom, applicant=employee),
                ],
                user=full_scope_user,
            )
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_LOCKED"
        ok.refresh_from_db()
        boom.refresh_from_db()
        assert ok.asset_current_status == "in_use"
        assert boom.asset_current_status == "in_store"


@pytest.mark.django_db
class TestOutAssetPersonScope:
    """D-5: 出库使用人/保管人写侧归属校验(口径 2026-11-02: 禁止跨部门借用)

    范围主体 auth_user(Employee 绑定 D001, regular_user → 仅本部门);
    跨部门员工 X002 属 D002,不在其可见范围内。
    """

    @pytest.fixture
    def cross_dept_employee(self):
        dept2 = Department.objects.create(department_code="D002", department_name="跨部门")
        return Employee.objects.create(
            employee_jobcode="X002",
            employee_name="跨部门员工",
            employee_department=dept2,
            employee_phone="13800131099",
        )

    @staticmethod
    def _make_outasset(storage, asset_type, employee, code, user):
        """合法出库(同部门人员);user kw-only 必填(M-07),由调用方按语义注入"""
        asset = _make_asset(storage, asset_type, "in_store", code, applicant=employee, manager=employee)
        return OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=user,
        )

    def test_create_cross_dept_applicant_raises(self, storage, asset_type, employee, auth_user, cross_dept_employee):
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_APP", applicant=employee, manager=employee)
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(
                _outasset_payload(asset, applicant=cross_dept_employee, manager=employee),
                operator_jobcode=employee.employee_jobcode,
                user=auth_user,
            )
        assert exc_info.value.error_code == "OUTASSET_PERSON_OUT_OF_SCOPE"

    def test_create_cross_dept_manager_raises(self, storage, asset_type, employee, auth_user, cross_dept_employee):
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_MGR", applicant=employee, manager=employee)
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(
                _outasset_payload(asset, applicant=employee, manager=cross_dept_employee),
                operator_jobcode=employee.employee_jobcode,
                user=auth_user,
            )
        assert exc_info.value.error_code == "OUTASSET_PERSON_OUT_OF_SCOPE"

    def test_create_same_dept_person_allowed(self, storage, asset_type, employee, auth_user):
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_OK", applicant=employee, manager=employee)
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee),
            operator_jobcode=employee.employee_jobcode,
            user=auth_user,
        )
        asset.refresh_from_db()
        assert outasset.outasset_applicant_recordcode == employee
        assert asset.asset_current_status == "in_use"

    def test_create_missing_user_raises_type_error(self, storage, asset_type, cross_dept_employee):
        """M-07: user 为 kw-only 必填——忘传即 TypeError,不再有「不传即放行」退化"""
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_NU")
        with pytest.raises(TypeError):
            OutAssetService.create_outasset(
                _outasset_payload(asset, applicant=cross_dept_employee, manager=cross_dept_employee)
            )

    def test_create_superuser_cross_dept_allowed(
        self, storage, asset_type, employee, admin_auth_user, cross_dept_employee
    ):
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_SA", applicant=employee, manager=employee)
        outasset = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=cross_dept_employee),
            operator_jobcode=employee.employee_jobcode,
            user=admin_auth_user,
        )
        assert outasset.outasset_applicant_recordcode == cross_dept_employee

    def test_create_no_department_employee_raises(self, storage, asset_type, employee, auth_user):
        """无部门员工: 部门级角色恒不可见(is_department_visible 同源, 不设单独分支)"""
        emp_no_dept = Employee.objects.create(
            employee_jobcode="X003", employee_name="无部门员工", employee_phone="13800131098"
        )
        asset = _make_asset(storage, asset_type, "in_store", "OUT_PSN_ND", applicant=employee, manager=employee)
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(
                _outasset_payload(asset, applicant=emp_no_dept, manager=employee),
                operator_jobcode=employee.employee_jobcode,
                user=auth_user,
            )
        assert exc_info.value.error_code == "OUTASSET_PERSON_OUT_OF_SCOPE"

    def test_batch_create_cross_dept_row_routed_to_fail_items(
        self, storage, asset_type, employee, auth_user, cross_dept_employee
    ):
        """批量端点 user 透传: 跨部门行逐行报错进 fail_items, 其余行不受影响"""
        ok = _make_asset(storage, asset_type, "in_store", "OUT_PSN_BA", applicant=employee, manager=employee)
        bad = _make_asset(storage, asset_type, "in_store", "OUT_PSN_BB", applicant=employee, manager=employee)
        result = OutAssetService.batch_create_outasset(
            [
                _outasset_payload(ok, applicant=employee, manager=employee),
                _outasset_payload(bad, applicant=cross_dept_employee, manager=employee),
            ],
            operator_jobcode=employee.employee_jobcode,
            user=auth_user,
        )
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "OUTASSET_PERSON_OUT_OF_SCOPE"

    def test_update_cross_dept_applicant_raises(self, storage, asset_type, employee, auth_user, cross_dept_employee):
        outasset = self._make_outasset(storage, asset_type, employee, "OUT_PSN_UP1", user=auth_user)
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.update_outasset(
                outasset.recordcode, {"outasset_applicant": cross_dept_employee}, user=auth_user
            )
        assert exc_info.value.error_code == "OUTASSET_PERSON_OUT_OF_SCOPE"

    def test_update_only_using_location_skips_person_check(self, storage, asset_type, employee, auth_user):
        """partial_update 未提交人员字段为 None 自动跳过: 只改使用地点不误拦"""
        outasset = self._make_outasset(storage, asset_type, employee, "OUT_PSN_UP2", user=auth_user)
        updated = OutAssetService.update_outasset(
            outasset.recordcode, {"outasset_using_location": "新地点"}, user=auth_user
        )
        updated.refresh_from_db()
        assert updated.outasset_using_location == "新地点"
        assert updated.outasset_applicant_recordcode == employee

    def test_update_superuser_cross_dept_allowed(
        self, storage, asset_type, employee, admin_auth_user, cross_dept_employee
    ):
        outasset = self._make_outasset(storage, asset_type, employee, "OUT_PSN_UP3", user=admin_auth_user)
        updated = OutAssetService.update_outasset(
            outasset.recordcode, {"outasset_applicant": cross_dept_employee}, user=admin_auth_user
        )
        assert updated.outasset_applicant_recordcode == cross_dept_employee

    def test_illegal_status_error_precedes_person_check(
        self, storage, asset_type, employee, auth_user, cross_dept_employee
    ):
        """校验插入在 _validate_outasset_source 之后: 非法状态先报 ILLEGAL_OUTASSET(错误码优先级不变)"""
        asset = _make_asset(storage, asset_type, "in_use", "OUT_PSN_PRI", applicant=employee, manager=employee)
        with pytest.raises(AppValidationError) as exc_info:
            OutAssetService.create_outasset(
                _outasset_payload(asset, applicant=cross_dept_employee, manager=employee),
                operator_jobcode=employee.employee_jobcode,
                user=auth_user,
            )
        assert exc_info.value.error_code == "ILLEGAL_OUTASSET"
