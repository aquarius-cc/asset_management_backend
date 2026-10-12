"""C批 B3-二轮:out_asset_service 残留 mutant 补杀(CT-4 回归护栏)

一轮后 out_asset_service 存活 28 个。二轮分诊:
- A 可杀(15):_delete_one FSM 异常分支 7 个(#40-46)、batch_create 键归一 6 个
  (#3 deepcopy、#13/#16/#17 row_number pop、#19/#20 operator 透传)、
  _restore #14/#15 manager fallback 键、#63 update_fields=None、
  _apply #33 update_fields=None
- B 等价(13):审计快照 fallback getattr 死分支、snapshot or True 分支、
  batch max_batch_size=None/101、use_transaction=None/True(值不改变可观察行为)、
  _delete_one 守卫参数(None/True/False 无数据差异)

杀灭手法:
- FSM 分支:previous_status 非 in_store/recycled_pending → AssetFSM.cancel_outasset
  抛 InvalidTransitionError → 断言 detail=str(e) 逐字(f-string→None/str(None) 立红)
- 键归一:断言原 dict 未被污染 + row_number 已剔除(pop None/XX/大写 立红)
- update_fields:断言 updated_at 未被触碰(update_fields=None 会全量 save 刷 updated_at)
"""

from unittest.mock import patch

import pytest

from apps.assetmanagement.models import Asset, OutAsset
from apps.assetmanagement.services.out_asset_service import OutAssetService
from core.exceptions import AppValidationError


AUDIT = "apps.assetmanagement.services.out_asset_service.AuditLogger"
FALLBACK_EMPL = "apps.usermanagement.selectors.EmployeeSelector.get_employee_by_jobcode"


def _payload(asset, applicant=None, manager=None, using_location="地点"):
    return {
        "asset_recordcode": asset,
        "outasset_date": "2024-03-01",
        "outasset_type": "receive",
        "outasset_applicant": applicant,
        "outasset_manager": manager,
        "outasset_using_location": using_location,
    }


@pytest.mark.django_db
class TestDeleteOneFsmBranchMutants:
    """_delete_one FSM 异常分支(#40-46):previous_status 非法 → detail 逐字"""

    def test_fsm_invalid_previous_status_detail_verbatim(self, asset, user, employee):
        """previous_status 非 in_store/recycled_pending → FSM 抛错 → detail=str(e)"""
        asset.asset_applicant_recordcode = employee
        asset.asset_manager_recordcode = employee
        asset.asset_current_status = "in_use"
        asset.save(
            update_fields=[
                "asset_applicant_recordcode",
                "asset_manager_recordcode",
                "asset_current_status",
            ]
        )
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-09-01",
            outasset_previous_status="unknown_state",
        )
        with pytest.raises(AppValidationError) as exc:
            OutAssetService._delete_one(oa.recordcode)
        assert exc.value.error_code == "INVALID_STATE_TRANSITION"
        assert "unknown_state" in str(exc.value.detail)
        assert exc.value.detail != "None"
        assert exc.value.detail is not None


@pytest.mark.django_db
class TestBatchCreateKeyNormalizeMutants:
    """batch_create_outasset #3/#13/#16/#17/#19/#20:键归一 + 原 dict 未污染"""

    def test_row_number_stripped_and_input_not_mutated(self, asset, user, employee):
        """row_number pop(None/XX/大写 立红) + deepcopy 语义(原 dict 不动)"""
        payload = {
            "outasset_asset": asset,
            "row_number": 1,
            "outasset_date": "2024-06-03",
            "outasset_type": "borrow",
            "outasset_using_location": "键归一",
            "outasset_applicant": user,
            "outasset_manager": employee,
        }
        snapshot_before = dict(payload)
        result = OutAssetService.batch_create_outasset([payload])
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert payload == snapshot_before
        assert "row_number" in payload
        assert "outasset_asset" in payload
        assert "asset_recordcode" not in payload
        oa = OutAsset.objects.get(asset_recordcode=asset)
        assert oa.outasset_type == "borrow"
        assert oa.outasset_using_location == "键归一"
        assert oa.outasset_applicant_recordcode == user
        assert oa.outasset_manager_recordcode == employee

    def test_operator_fields_forwarded(self, asset, user, employee):
        """operator_jobcode/operator_name 透传(#19/#20 立红)"""
        payload = {
            "outasset_asset": asset,
            "outasset_date": "2024-06-04",
            "outasset_type": "borrow",
            "outasset_applicant": user,
        }
        with patch(AUDIT) as mock_audit:
            result = OutAssetService.batch_create_outasset(
                [payload], operator_jobcode="OP777", operator_name="批量操作员"
            )
        assert result["success_count"] == 1
        call_kwargs = mock_audit.log_asset_out.call_args.kwargs
        assert call_kwargs["operator_jobcode"] == "OP777"
        assert call_kwargs["operator_name"] == "批量操作员"


@pytest.mark.django_db
class TestRestoreManagerFallbackMutants:
    """_restore_asset_fields #14/#15:manager fallback 键路由"""

    def test_manager_fallback_key_routes(self, asset, user, employee):
        """original_manager 缺 → manager fallback 命中(#14 XX/#15 大写 立红)"""
        asset.asset_manager_recordcode = employee
        asset.save(update_fields=["asset_manager_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-09-02",
            outasset_snapshot={
                "manager": {"jobcode": user.employee_jobcode, "name": user.employee_name},
            },
        )
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        asset.refresh_from_db()
        assert asset.asset_manager_recordcode == user


@pytest.mark.django_db
class TestUpdateFieldsNoneMutants:
    """_restore #63 / _apply #33:save(update_fields=None) 全量落库触碰 updated_at"""

    def test_restore_preserves_updated_at(self, asset, user, employee):
        """update_fields=None 会全量 save 刷 updated_at(#63 立红)"""
        asset.asset_applicant_recordcode = employee
        asset.asset_storage_recordcode = None
        asset.save(update_fields=["asset_applicant_recordcode", "asset_storage_recordcode"])
        oa = OutAsset.objects.create(
            asset_recordcode=asset,
            outasset_date="2024-09-03",
            outasset_snapshot={
                "original_applicant": {"jobcode": user.employee_jobcode, "name": user.employee_name},
            },
        )
        before_ts = Asset.objects.get(pk=asset.pk).updated_at
        OutAssetService._restore_asset_fields(asset, oa, "in_store")
        after_ts = Asset.objects.get(pk=asset.pk).updated_at
        assert after_ts == before_ts

    def test_apply_preserves_updated_at(self, asset, user):
        """_apply update_fields=None(#33 立红):出库只应落 status/storage/people/usage"""
        before_ts = Asset.objects.get(pk=asset.pk).updated_at
        OutAssetService._apply_outasset_to_asset(asset, user, None, "新地点")
        after_ts = Asset.objects.get(pk=asset.pk).updated_at
        assert after_ts == before_ts
