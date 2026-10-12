"""C批 B3:out_asset_service 存活 mutant 定向补杀(CT-4 回归护栏)

B3-A:_delete_one(31)/_build_update_audit_snapshot(29)/_restore_asset_fields(15)/
     batch_create_outasset(14)/_resolve_snapshot_employee(11)
B3-B:_build_outasset_snapshot(11)/_apply_outasset_to_asset(8)/batch_delete(2)/
     _validate_outasset_source(2)

杀灭手法(对应分诊):
- detail 逐字断言:`exc.value.detail`(f-string→None/删参 立刻红)
- 错误码逐字:`exc.value.error_code`(None/XX改写/大小写 立刻红)
- 审计快照全字段:patch AuditLogger 捕获 before/after 逐键断言
- snapshot 键名:`snapshot["name"]`/`snapshot["original_*"]`(XX改写 立刻红)
- 键路由来源:original 命中 vs fallback 命中各一条(仅断言值相等杀不掉键变异)
- 键归一 + 原 dict 未污染:deepcopy 语义(pop 后原 dict 残留 立刻红)
- FSM:非法态出库 / 非 in_use 取消出库
"""

from unittest.mock import patch

import pytest

from apps.assetmanagement.models import Asset, OutAsset, RecycleAsset
from apps.assetmanagement.services.out_asset_service import OutAssetService
from core.exceptions import AppValidationError


AUDIT = "apps.assetmanagement.services.out_asset_service.AuditLogger"
FALLBACK_EMPL = "apps.usermanagement.selectors.EmployeeSelector.get_employee_by_jobcode"


def _state_log_desc(asset, trigger):
    """审计 description 唯一真源形态(见 apps/assetmanagement/audit.py log_state_change)"""
    return f"状态从 {asset.asset_current_status} 变为 in_use (触发: {trigger})"


@pytest.mark.django_db
class TestValidateOutassetSourceMutants:
    """_validate_outasset_source(2):非法态 detail 逐字"""

    def test_illegal_status_detail_verbatim(self, storage, asset_type, employee):
        asset = Asset.objects.create(
            asset_code="VAL_M1",
            asset_name="校验",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="scrapped",
        )
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._validate_outasset_source(asset)
        assert exc.value.detail == f"资产当前状态为 {asset.asset_current_status},不能出库"
        assert exc.value.error_code == "ILLEGAL_OUTASSET"


@pytest.mark.django_db
class TestBuildSnapshotMutants:
    """_build_outasset_snapshot(11):键名 + None 分支"""

    def test_snapshot_applicant_none(self, storage, asset_type):
        asset = Asset.objects.create(
            asset_code="SNAP_M1",
            asset_name="快照None",
            asset_purchase_price=100,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
        )
        snap = OutAssetService._build_outasset_snapshot(asset, None, None, "库房A")
        assert snap["applicant"] is None
        assert snap["manager"] is None
        assert snap["using_location"] == "库房A"
        assert snap["asset_storage_recordcode"] == storage.recordcode
        assert snap["original_applicant"] is None
        assert snap["original_manager"] is None
        assert snap["original_using_location"] is None

    def test_snapshot_full_key_names(self, asset, storage, user, employee):
        """asset 原字段非空:original_* 全键 + employee jobcode/name 取值"""
        asset.asset_applicant_recordcode = user
        asset.asset_manager_recordcode = employee
        asset.asset_using_location = "原地点"
        asset.save(
            update_fields=[
                "asset_applicant_recordcode",
                "asset_manager_recordcode",
                "asset_using_location",
            ]
        )
        snap = OutAssetService._build_outasset_snapshot(asset, user, employee, "新地点")
        assert snap["applicant"] == {"jobcode": user.employee_jobcode, "name": user.employee_name}
        assert snap["manager"] == {"jobcode": employee.employee_jobcode, "name": employee.employee_name}
        assert snap["original_applicant"] == {"jobcode": user.employee_jobcode, "name": user.employee_name}
        assert snap["original_manager"] == {"jobcode": employee.employee_jobcode, "name": employee.employee_name}
        assert snap["original_using_location"] == "原地点"
        assert snap["using_location"] == "新地点"


@pytest.mark.django_db
class TestAuditSnapshotMutants:
    """_build_update_audit_snapshot(29):before/after 全字段 + 键路由"""

    def test_audit_before_after_full_fields(self, asset, user, employee, storage):
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-01",
            outasset_type="borrow",
            outasset_using_location="旧地点",
            outasset_applicant_recordcode=user,
            outasset_manager_recordcode=employee,
            outasset_snapshot={},
        )
        upd = {"outasset_using_location": "新地点", "outasset_type": "receive"}
        before, after = OutAssetService._build_update_audit_snapshot(
            oa, upd, applicant=employee, manager=employee
        )
        assert before["outasset_using_location"] == "旧地点"
        assert before["outasset_type"] == "borrow"
        assert before["outasset_applicant"] == user.employee_jobcode
        assert before["outasset_manager"] == employee.employee_jobcode
        assert after["outasset_using_location"] == "新地点"
        assert after["outasset_type"] == "receive"
        assert after["outasset_applicant_recordcode"] == employee.employee_jobcode
        assert after["outasset_manager_recordcode"] == employee.employee_jobcode

    def test_audit_none_applicant_manager_keeps_scalar(self, asset, storage):
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-02",
            outasset_type="borrow",
            outasset_using_location="A",
            outasset_snapshot={},
        )
        upd = {"outasset_using_location": "B"}
        before, after = OutAssetService._build_update_audit_snapshot(oa, upd, None, None)
        assert "outasset_applicant" not in before
        assert "outasset_manager" not in before
        assert "outasset_applicant_recordcode" not in after
        assert "outasset_manager_recordcode" not in after
        assert before["outasset_using_location"] == "A"
        assert after["outasset_using_location"] == "B"


@pytest.mark.django_db
class TestRestoreFieldsMutants:
    """_restore_asset_fields(15) + _resolve_snapshot_employee(11):键路由来源"""

    def test_restore_uses_original_key(self, asset, user, employee, storage):
        """original 键命中→取 original 值(不看 fallback)"""
        asset.asset_applicant_recordcode = employee
        asset.save(update_fields=["asset_applicant_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-03",
            outasset_type="borrow",
            outasset_snapshot={
                "original_applicant": {"jobcode": user.employee_jobcode, "name": user.employee_name},
                "applicant": {"jobcode": employee.employee_jobcode, "name": employee.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode == user

    def test_restore_falls_back_when_original_missing(self, asset, user, employee, storage):
        """original 键缺→fallback 键命中"""
        asset.asset_applicant_recordcode = employee
        asset.save(update_fields=["asset_applicant_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-04",
            outasset_type="borrow",
            outasset_snapshot={
                "applicant": {"jobcode": user.employee_jobcode, "name": user.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode == user

    def test_restore_null_original_stays_none(self, asset, employee, storage):
        """original 键命中但值 None → 恢复为 None(不走 fallback)"""
        asset.asset_applicant_recordcode = employee
        asset.save(update_fields=["asset_applicant_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-05",
            outasset_type="borrow",
            outasset_snapshot={
                "original_applicant": None,
                "applicant": {"jobcode": employee.employee_jobcode, "name": employee.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode is None

    def test_restore_manager_key_routes(self, asset, user, employee, storage):
        """manager 侧键路由:original 命中"""
        asset.asset_manager_recordcode = employee
        asset.save(update_fields=["asset_manager_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-06",
            outasset_type="borrow",
            outasset_snapshot={
                "original_manager": {"jobcode": user.employee_jobcode, "name": user.employee_name},
                "manager": {"jobcode": employee.employee_jobcode, "name": employee.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_manager_recordcode == user

    def test_restore_using_location_fallback(self, asset, storage):
        """无 original_using_location → 走 fallback using_location"""
        asset.asset_using_location = "库房"
        asset.save(update_fields=["asset_using_location"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-07",
            outasset_type="borrow",
            outasset_snapshot={"using_location": "旧地"},
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_using_location == "旧地"

    def test_restore_storage_when_in_store(self, asset, storage, employee):
        """previous_status=in_store → 从 snapshot 恢复 storage"""
        asset.asset_applicant_recordcode = employee
        asset.save(update_fields=["asset_applicant_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-08",
            outasset_type="borrow",
            outasset_snapshot={
                "asset_storage_recordcode": storage.recordcode,
                "original_applicant": {"jobcode": employee.employee_jobcode, "name": employee.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_storage_recordcode == storage

    def test_restore_no_storage_when_not_in_store(self, asset, storage, employee):
        """previous_status 非 in_store → 不恢复 storage(elif 分支)"""
        asset.asset_applicant_recordcode = employee
        asset.asset_storage_recordcode = None
        asset.save(update_fields=["asset_applicant_recordcode", "asset_storage_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-05-09",
            outasset_type="borrow",
            outasset_snapshot={
                "asset_storage_recordcode": storage.recordcode,
                "original_applicant": {"jobcode": employee.employee_jobcode, "name": employee.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "recycled_pending")
        asset.refresh_from_db()
        assert asset.asset_storage_recordcode is None


class TestResolveSnapshotEmployeeMutants:
    """_resolve_snapshot_employee(11):三分支 + jobcode 键名"""

    def test_original_hit_returns_employee(self, user):
        with patch(FALLBACK_EMPL, return_value=user) as m:
            ok, val = OutAssetService._resolve_snapshot_employee(
                {"original_applicant": {"jobcode": "U001", "name": "x"}}, "original_applicant", "applicant"
            )
        assert ok is True and val == user
        m.assert_called_once_with("U001")

    def test_fallback_hit_returns_employee(self, user):
        with patch(FALLBACK_EMPL, return_value=user) as m:
            ok, val = OutAssetService._resolve_snapshot_employee(
                {"applicant": {"jobcode": "U001", "name": "x"}}, "original_applicant", "applicant"
            )
        assert ok is True and val == user
        m.assert_called_once_with("U001")

    def test_none_hit_returns_true_none(self):
        with patch(FALLBACK_EMPL) as m:
            ok, val = OutAssetService._resolve_snapshot_employee({}, "original_applicant", "applicant")
        assert ok is False and val is None
        m.assert_not_called()


@pytest.mark.django_db
class TestBatchCreateOutassetMutants:
    """batch_create_outasset(14):键归一 + 原 dict 未污染"""

    def test_key_normalization_and_input_not_mutated(self, asset, storage, user, employee):
        payload = {
            "outasset_asset": asset,
            "row_number": 1,
            "outasset_date": "2024-06-01",
            "outasset_type": "borrow",
            "outasset_using_location": "批量",
            "outasset_applicant": user,
            "outasset_manager": employee,
        }
        original_len = len(payload)
        result = OutAssetService.batch_create_outasset([payload])
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert len(payload) == original_len
        assert "asset_recordcode" not in payload
        assert "outasset_asset" in payload
        assert "row_number" in payload
        oa = OutAsset.objects.get(asset_recordcode=asset)
        assert oa.outasset_type == "borrow"
        assert oa.outasset_using_location == "批量"
        assert oa.outasset_applicant_recordcode == user
        assert oa.outasset_manager_recordcode == employee

    def test_operator_jobcode_forwarded(self, asset, storage, user, employee):
        payload = {
            "outasset_asset": asset,
            "outasset_date": "2024-06-02",
            "outasset_type": "borrow",
            "outasset_applicant": user,
        }
        with patch(AUDIT) as mock_audit:
            result = OutAssetService.batch_create_outasset(
                [payload], operator_jobcode="OP999", operator_name="批量员"
            )
        assert result["success_count"] == 1
        mock_audit.log_asset_out.assert_called_once()
        call_kwargs = mock_audit.log_asset_out.call_args
        assert call_kwargs.kwargs["operator_jobcode"] == "OP999"
        assert call_kwargs.kwargs["operator_name"] == "批量员"


@pytest.mark.django_db
class TestDeleteOneMutants:
    """_delete_one(31):detail/error_code 逐字 + 审计 trigger + 守卫"""

    def test_not_found_detail_verbatim(self):
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._delete_one("NON-EXIST-CODE")
        assert exc.value.detail == "出库记录 NON-EXIST-CODE 不存在"
        assert exc.value.error_code == "NOT_FOUND"

    def test_status_not_allowed_detail_verbatim(self, asset, storage, user):
        asset.asset_applicant_recordcode = user
        asset.save(update_fields=["asset_applicant_recordcode"])
        oa = OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-07-01")
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._delete_one(oa.recordcode)
        assert exc.value.detail == f"关联资产当前状态为 {asset.asset_current_status},不允许删除出库记录"
        assert exc.value.error_code == "STATUS_NOT_ALLOWED"

    def test_has_recycle_records_detail_verbatim(self, asset, outasset, employee):
        RecycleAsset.objects.create(
            outasset_recordcode=outasset,
            asset_recordcode=asset,
            recycle_asset_date="2024-07-02",
            recycle_asset_number=1,
            operator_employee=employee,
        )
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._delete_one(outasset.recordcode)
        assert exc.value.detail == "出库记录存在关联回收记录,不允许删除"
        assert exc.value.error_code == "HAS_RECYCLE_RECORDS"

    def test_cancel_audit_trigger_verbatim(self, asset, user, employee):
        asset.asset_applicant_recordcode = employee
        asset.asset_manager_recordcode = employee
        asset.asset_using_location = "旧地"
        asset.save(
            update_fields=[
                "asset_applicant_recordcode",
                "asset_manager_recordcode",
                "asset_using_location",
            ]
        )
        oa = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=user, manager=user, using_location="新地")
        )
        with patch(AUDIT) as mock_audit:
            OutAssetService._delete_one(oa.recordcode, operator_jobcode="OP1", operator_name="张三")
        assert mock_audit.log_state_change.call_count == 1
        kwargs = mock_audit.log_state_change.call_args.kwargs
        assert kwargs["trigger"] == "cancel_outasset"
        assert kwargs["operator_name"] == "张三"
        assert kwargs["operator_jobcode"] == "OP1"


def _outasset_payload(asset, applicant=None, manager=None, using_location="地点"):
    return {
        "asset_recordcode": asset,
        "outasset_date": "2024-03-01",
        "outasset_type": "receive",
        "outasset_applicant": applicant,
        "outasset_manager": manager,
        "outasset_using_location": using_location,
    }


@pytest.mark.django_db
class TestApplyOutassetToAssetMutants:
    """_apply_outasset_to_asset(8):FSM 非法态 + update_fields None"""

    def test_fsm_reject_illegal_transition(self, asset, storage):
        asset.asset_current_status = "scrapped"
        asset.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._apply_outasset_to_asset(asset, None, None, "X")
        assert exc.value.error_code == "INVALID_STATE_TRANSITION"
        assert "scrapped" in str(exc.value.detail)

    def test_usage_type_set_to_used(self, asset, user, employee, storage):
        asset.asset_applicant_recordcode = user
        asset.save(update_fields=["asset_applicant_recordcode"])
        result = OutAssetService._apply_outasset_to_asset(asset, user, employee, "新地点")
        assert result.usage_type == Asset.UsageType.USED
        assert result.asset_current_status == Asset.AssetStatus.IN_USE
        assert result.asset_storage_recordcode is None
        assert result.asset_using_location == "新地点"


@pytest.mark.django_db
class TestBatchDeleteOutassetMutants:
    """batch_delete_outasset(2):lambda 转发 operator_name"""

    def test_operator_name_forwarded_to_delete(self, asset, user, employee):
        """先出库到 in_use，再删除转发 operator_name"""
        oa = OutAssetService.create_outasset(
            _outasset_payload(asset, applicant=employee, manager=employee)
        )
        with patch(AUDIT) as mock_audit:
            result = OutAssetService.batch_delete_outasset(
                [oa.recordcode], operator_jobcode="OP1", operator_name="李四"
            )
        assert result["success_count"] == 1
        kwargs = mock_audit.log_state_change.call_args.kwargs
        assert kwargs["operator_name"] == "李四"
        assert kwargs["operator_jobcode"] == "OP1"
