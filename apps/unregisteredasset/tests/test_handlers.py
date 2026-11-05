"""
未登记资产审批处理函数(handlers)直接行为测试

BR-4 B2 拆分前补充的 CT-3 回归锚:直接调用 handlers 模块函数,锁定
S1 创建即回收、S3 修正即回收的状态机路径与三表(asset/outasset/recycle)
关联一致性,使拆分 helper(_create_unregistered_asset/_create_receive_outasset/
_force_finalize_recycle)时行为可回归比对。
"""

from datetime import date

import pytest

from apps.assetmanagement.models import Asset, AssetOperationLog, OutAsset, RecycleAsset, Storage
from apps.unregisteredasset.handlers import (
    _create_unregistered_asset,
    _handle_s1_create_and_damaged,
    _handle_s1_create_and_recycle,
    _handle_s2_supplement_and_recycle,
    _handle_s3_correct_and_recycle,
)
from apps.unregisteredasset.models import UnregisteredAsset
from core.exceptions import AppValidationError


@pytest.mark.django_db
class TestUnregisteredAssetHandlers:
    def test_handle_s1_create_and_recycle(self, unregistered_asset_s1, admin_employee, asset_type):
        result = _handle_s1_create_and_recycle(unregistered_asset_s1, admin_employee)

        assert set(result) >= {"action", "asset_code", "recycle_id", "recordcode"}
        assert result["action"] == "create_and_recycle"

        asset = Asset.objects.get(asset_code=result["asset_code"])
        assert asset.asset_name == unregistered_asset_s1.asset_name
        assert asset.asset_brand == unregistered_asset_s1.asset_brand
        assert asset.asset_specification == unregistered_asset_s1.asset_specification
        assert asset.asset_type_recordcode == unregistered_asset_s1.unregistered_asset_type
        assert asset.asset_storage_recordcode == unregistered_asset_s1.unregistered_asset_storage
        assert asset.asset_purchase_price == unregistered_asset_s1.estimated_value
        assert asset.asset_purchase_date == unregistered_asset_s1.discovery_date
        # CT-3: unregistered_create_and_recycle 路径
        assert asset.asset_current_status == "recycled_pending"

        outasset = OutAsset.objects.get(asset_recordcode=asset)
        assert outasset.outasset_type == "receive"
        assert unregistered_asset_s1.unregistered_code in outasset.outasset_description

        recycle = RecycleAsset.objects.get(id=result["recycle_id"])
        assert recycle.asset_recordcode == asset
        assert recycle.outasset_recordcode == outasset
        assert recycle.operator_employee == admin_employee
        assert recycle.recordcode == result["recordcode"]

        assert unregistered_asset_s1.result_asset == asset
        assert unregistered_asset_s1.result_recycle_asset == recycle

        unregistered_asset_s1.save()
        unregistered_asset_s1.refresh_from_db()
        assert unregistered_asset_s1.result_asset == asset
        assert unregistered_asset_s1.result_recycle_asset == recycle

    def test_create_injects_in_store_explicitly(self, unregistered_asset_s1):
        """[OP-18/例外 E-1] S1 裸 create 显式注入 IN_STORE 枚举(与约束 7 同口径, 不依赖模型隐式默认)"""
        asset = _create_unregistered_asset(unregistered_asset_s1)
        assert asset.asset_current_status == Asset.AssetStatus.IN_STORE.value

    def test_handle_s3_correct_and_recycle(self, unregistered_asset_s3, admin_employee, existing_asset):
        new_storage = Storage.objects.create(
            storage_code="STOR-S3", storage_name="S3修正仓库", storage_address="测试地址"
        )
        unregistered_asset_s3.unregistered_asset_storage = new_storage
        unregistered_asset_s3.save(update_fields=["unregistered_asset_storage"])

        old_status = existing_asset.asset_current_status
        result = _handle_s3_correct_and_recycle(unregistered_asset_s3, admin_employee)

        assert result["action"] == "correct_and_recycle"
        assert result["old_status"] == old_status
        assert "recycle_id" in result
        assert "recordcode" in result

        existing_asset.refresh_from_db()
        assert existing_asset.asset_current_status == "recycled_pending"
        assert existing_asset.asset_storage_recordcode == new_storage

        outasset = OutAsset.objects.get(asset_recordcode=existing_asset)
        assert outasset.outasset_type == "receive"
        assert unregistered_asset_s3.unregistered_code in outasset.outasset_description

        recycle = RecycleAsset.objects.get(id=result["recycle_id"])
        assert recycle.asset_recordcode == existing_asset
        assert recycle.outasset_recordcode == outasset
        assert f"状态修正 {old_status}→recycled_pending" in recycle.recycle_asset_description
        assert recycle.recordcode == result["recordcode"]

        assert unregistered_asset_s3.result_asset == existing_asset
        assert unregistered_asset_s3.result_recycle_asset == recycle

        unregistered_asset_s3.save()
        unregistered_asset_s3.refresh_from_db()
        assert unregistered_asset_s3.result_asset == existing_asset
        assert unregistered_asset_s3.result_recycle_asset == recycle

    def test_handle_s3_missing_related_asset(self, employee, storage):
        unreg = UnregisteredAsset.objects.create(
            scenario_type="s3_status_mismatch",
            discovery_date=date(2024, 6, 1),
            discovery_location="仓库C",
            discovery_person=employee,
            asset_name="无关联资产",
            unregistered_asset_storage=storage,
            approval_status="pending",
        )

        with pytest.raises(AppValidationError) as exc_info:
            _handle_s3_correct_and_recycle(unreg, "EMP001")
        assert "必须有关联资产" in str(exc_info.value.detail)


@pytest.mark.django_db
class TestForceRecycleStateChangeAudit:
    """[M-16] S2/S3 强制回收前态留痕：force_recycle_from_any 为 M-60 声明例外的
    FSM 旁路，必须在 helper 内补 state_change 审计（before_data 含原状态）。"""

    def test_s2_writes_state_change_log(self, unregistered_asset_s2, admin_employee):
        result = _handle_s2_supplement_and_recycle(unregistered_asset_s2, admin_employee)
        asset = Asset.objects.get(asset_code=result["asset_code"])
        log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="state_change").latest(
            "operation_time"
        )
        assert log.before_data["asset_current_status"] == "in_store"
        assert log.after_data["asset_current_status"] == "recycled_pending"

    def test_s3_writes_state_change_log(self, unregistered_asset_s3, admin_employee):
        result = _handle_s3_correct_and_recycle(unregistered_asset_s3, admin_employee)
        asset = Asset.objects.get(asset_code=result["asset_code"])
        log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="state_change").latest(
            "operation_time"
        )
        assert log.before_data["asset_current_status"] == "in_store"
        assert log.after_data["asset_current_status"] == "recycled_pending"


@pytest.mark.django_db
class TestS1CreateAuditTrail:
    """[OP-10] S1 场景裸 Asset.objects.create + FSM 旁路补痕: 与 M-16 范式对齐,
    创建(create) + 状态变更(state_change) 两条审计事件构成完整链路。"""

    def test_s1_recycle_writes_create_and_state_change_log(self, unregistered_asset_s1, admin_employee):
        result = _handle_s1_create_and_recycle(unregistered_asset_s1, admin_employee)
        asset = Asset.objects.get(asset_code=result["asset_code"])

        # 创建痕迹: after_data 如实为 in_store(FSM 前), 与 state_change 构成完整前态
        create_log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="create").latest("id")
        assert create_log.after_data["asset_current_status"] == "in_store"

        # 状态变更痕迹: in_store → recycled_pending, trigger 可追溯
        state_log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="state_change").latest(
            "id"
        )
        assert state_log.before_data["asset_current_status"] == "in_store"
        assert state_log.after_data["asset_current_status"] == "recycled_pending"
        assert "unregistered_create_and_recycle" in state_log.description

    def test_s1_damaged_writes_create_and_state_change_log(self, unregistered_asset_s1, admin_employee):
        result = _handle_s1_create_and_damaged(unregistered_asset_s1, admin_employee)
        asset = Asset.objects.get(asset_code=result["asset_code"])

        create_log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="create").latest("id")
        assert create_log.after_data["asset_current_status"] == "in_store"

        state_log = AssetOperationLog.objects.filter(asset_code=asset.asset_code, operation_type="state_change").latest(
            "id"
        )
        assert state_log.before_data["asset_current_status"] == "in_store"
        assert state_log.after_data["asset_current_status"] == "damaged"
        assert "unregistered_create_and_damaged" in state_log.description
