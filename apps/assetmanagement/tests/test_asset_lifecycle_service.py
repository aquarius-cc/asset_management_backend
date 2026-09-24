"""资产生命周期批量删除 Service 层测试(#17 §1.2 分层收敛)

覆盖:
- batch_delete_lifecycle_asset: broken/lost/found 三入口, 合成成功+NOT_FOUND 分类
- batch_delete_repair_asset: 成功 / REPAIR_IN_PROGRESS 透传 / NOT_FOUND
- 批大小上限 BATCH_SIZE_EXCEEDED(与 test_recycle_asset_service.py 同语义: 抛异常而非 fail_items)
- 批次①(2026-09-22) 删除写路径部门作用域(B12 模式, A-29 先例): 单删/批删越权 ASSET_NOT_VISIBLE + 同部门回归
"""

import pytest

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    BrokenAsset,
    FoundAsset,
    LostAsset,
    RepairAsset,
)
from apps.assetmanagement.services.asset_lifecycle_mixin import AssetLifecycleMixin
from core.exceptions import AppValidationError


NOT_FOUND_ID = "NO_SUCH_RECORDCODE"


@pytest.mark.django_db
class TestBatchDeleteLifecycleAsset:
    """批量删除损坏/遗失/找回记录"""

    def test_broken_mixed_success_and_not_found(self, broken_asset):
        """合成场景: 1 条成功(软删+审计) + 1 条不存在(NOT_FOUND), 互不影响"""
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            [broken_asset.recordcode, NOT_FOUND_ID],
            "delete_broken_asset",
            operator_jobcode="OP999",
            operator_name="测试操作员",
        )

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["success_ids"] == [broken_asset.recordcode]
        assert result["fail_items"] == [
            {"id": NOT_FOUND_ID, "error_code": "NOT_FOUND", "error_message": f"记录 {NOT_FOUND_ID} 不存在"}
        ]

        assert not BrokenAsset.objects.filter(recordcode=broken_asset.recordcode, is_deleted=False).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=broken_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description__startswith="损坏资产记录删除",
        ).exists()

    @pytest.mark.parametrize(
        ("delete_method", "fixture_name"),
        [("delete_lost_asset", "lost_asset"), ("delete_found_asset", "found_asset")],
    )
    def test_parameterized_success(self, request, delete_method, fixture_name):
        """lost/found 与 broken 同构: 成功软删 + NOT_FOUND 分类"""
        record = request.getfixturevalue(fixture_name)
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            [record.recordcode, NOT_FOUND_ID],
            delete_method,
            operator_jobcode="OP999",
            operator_name="测试操作员",
        )

        assert result["success_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"
        model = LostAsset if fixture_name == "lost_asset" else FoundAsset
        assert not model.objects.filter(recordcode=record.recordcode, is_deleted=False).exists()

    def test_exceeds_limit_raises(self):
        """101 条 → 抛 BATCH_SIZE_EXCEEDED(前置校验, 不落 fail_items, 与全仓 batch_delete 一致)"""
        ids = [f"R{i}" for i in range(101)]
        with pytest.raises(AppValidationError) as exc_info:
            AssetLifecycleMixin.batch_delete_lifecycle_asset(ids, "delete_broken_asset")
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"


@pytest.mark.django_db
class TestBatchDeleteRepairAsset:
    """批量删除维修记录"""

    def test_success_soft_deletes_with_audit(self, repair_asset):
        repair_asset.repair_status = RepairAsset.RepairStatus.COMPLETED
        repair_asset.save(update_fields=["repair_status", "updated_at"])
        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [repair_asset.recordcode], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["success_count"] == 1
        assert not RepairAsset.objects.filter(recordcode=repair_asset.recordcode, is_deleted=False).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=repair_asset.asset_recordcode.asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description__startswith="维修记录删除",
        ).exists()

    def test_in_progress_error_code_preserved(self, repair_asset):
        """进行中的维修记录: REPAIR_IN_PROGRESS 原样进 fail_items(不被 NOT_FOUND/兜底遮蔽)"""
        repair_asset.repair_status = RepairAsset.RepairStatus.IN_PROGRESS
        repair_asset.save(update_fields=["repair_status", "updated_at"])

        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [repair_asset.recordcode], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "REPAIR_IN_PROGRESS"
        assert result["fail_items"][0]["error_message"] == (f"维修记录 {repair_asset.recordcode} 正在进行中,不可删除")

    def test_not_found_classified(self):
        """不存在的维修记录: NOT_FOUND(收敛前落入 INTERNAL_ERROR, 行为变更已登记 #17)"""
        result = AssetLifecycleMixin.batch_delete_repair_asset(
            [NOT_FOUND_ID], operator_jobcode="OP999", operator_name="测试操作员"
        )
        assert result["fail_count"] == 1
        assert result["fail_items"][0] == {
            "id": NOT_FOUND_ID,
            "error_code": "NOT_FOUND",
            "error_message": f"记录 {NOT_FOUND_ID} 不存在",
        }


@pytest.fixture
def lifecycle_cross_dept_data(db, storage, asset_type):
    """跨部门生命周期夹具(A-29 部门 A/B 模式): B部门资产 + broken/repair 记录 + A/B 部门经理
    user↔部门映射依赖 AuthUser.username == Employee.employee_jobcode 配对
    (与 test_damaged_asset_service.py:579 cross_dept_data 同口径)
    """
    from apps.authusermanagement.models import AuthUser
    from apps.usermanagement.models import Department, Employee, EmployeeRole
    from core.tests import TEST_PASSWORD

    dept_a = Department.objects.create(department_code="X-LA", department_name="A部门")
    dept_b = Department.objects.create(department_code="X-LB", department_name="B部门")
    Employee.objects.create(
        employee_jobcode="lmgr_a",
        employee_name="A经理",
        employee_department=dept_a,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone="13800000021",
    )
    Employee.objects.create(
        employee_jobcode="lmgr_b",
        employee_name="B经理",
        employee_department=dept_b,
        role=EmployeeRole.DEPT_MANAGER,
        employee_phone="13800000022",
    )
    holder_b = Employee.objects.create(
        employee_jobcode="lholder_b",
        employee_name="B保管",
        employee_department=dept_b,
        employee_phone="13800000023",
    )
    user_a = AuthUser.objects.create_user(auth_username="lmgr_a", password=TEST_PASSWORD, auth_phone="13800000031")
    user_b = AuthUser.objects.create_user(auth_username="lmgr_b", password=TEST_PASSWORD, auth_phone="13800000032")
    asset_b = Asset.objects.create(
        asset_code="A-LB-01",
        asset_name="B部门资产",
        asset_purchase_price=2000.00,
        asset_purchase_date="2024-02-01",
        asset_entry_date="2024-02-10",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_manager_recordcode=holder_b,
        asset_current_status=Asset.AssetStatus.BROKEN,
    )
    broken_b = BrokenAsset.objects.create(
        asset_recordcode=asset_b,
        broken_reason="跨部门损坏",
        broken_date="2024-09-01",
        operator_employee=holder_b,
    )
    repair_b = RepairAsset.objects.create(
        asset_recordcode=asset_b,
        repair_reason="跨部门维修",
        repair_date="2024-12-01",
        operator_employee=holder_b,
        repair_status=RepairAsset.RepairStatus.COMPLETED,
    )
    return {
        "asset_b": asset_b,
        "broken_b": broken_b,
        "repair_b": repair_b,
        "user_a": user_a,
        "user_b": user_b,
    }


@pytest.mark.django_db
class TestDeleteServiceUserScope:
    """批次①(2026-09-22): 生命周期删除写路径部门作用域收口(B12 模式, A-29 先例)

    A29 方案选择传递 user 的 get_queryset_for_user 校验(不预筛 ids),
    越权 → AppValidationError(ASSET_NOT_VISIBLE) 入 fail_items / 单删抛异常
    """

    def test_batch_delete_cross_dept_blocked(self, lifecycle_cross_dept_data):
        """A部门经理批量删除 B部门损坏记录 → fail_item ASSET_NOT_VISIBLE, 记录不动"""
        data = lifecycle_cross_dept_data
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            ids=[data["broken_b"].recordcode],
            delete_service_method="delete_broken_asset",
            operator_jobcode="lmgr_a",
            operator_name="A经理",
            user=data["user_a"],
        )
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert BrokenAsset.objects.filter(recordcode=data["broken_b"].recordcode, is_deleted=False).exists()

    def test_batch_delete_same_dept_success(self, lifecycle_cross_dept_data):
        """B部门经理批量删除本部门损坏记录 → 成功软删 + 审计落库"""
        data = lifecycle_cross_dept_data
        result = AssetLifecycleMixin.batch_delete_lifecycle_asset(
            ids=[data["broken_b"].recordcode],
            delete_service_method="delete_broken_asset",
            operator_jobcode="lmgr_b",
            operator_name="B经理",
            user=data["user_b"],
        )
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert BrokenAsset.objects.filter(recordcode=data["broken_b"].recordcode, is_deleted=False).exists() is False

    def test_batch_delete_repair_cross_dept_blocked(self, lifecycle_cross_dept_data):
        """A部门经理批量删除 B部门维修记录 → ASSET_NOT_VISIBLE(权限缺失不得误删)"""
        data = lifecycle_cross_dept_data
        result = AssetLifecycleMixin.batch_delete_repair_asset(
            ids=[data["repair_b"].recordcode],
            operator_jobcode="lmgr_a",
            operator_name="A经理",
            user=data["user_a"],
        )
        assert result["success_count"] == 0
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "ASSET_NOT_VISIBLE"
        assert RepairAsset.objects.filter(recordcode=data["repair_b"].recordcode, is_deleted=False).exists()

    def test_single_delete_cross_dept_raises(self, lifecycle_cross_dept_data):
        """A部门经理单删 B部门损坏记录 → AppValidationError(ASSET_NOT_VISIBLE), 记录不动"""
        data = lifecycle_cross_dept_data
        with pytest.raises(AppValidationError) as exc_info:
            AssetLifecycleMixin.delete_broken_asset(
                recordcode=data["broken_b"].recordcode,
                operator_jobcode="lmgr_a",
                operator_name="A经理",
                user=data["user_a"],
            )
        assert exc_info.value.error_code == "ASSET_NOT_VISIBLE"
        assert BrokenAsset.objects.filter(recordcode=data["broken_b"].recordcode, is_deleted=False).exists()

    def test_single_delete_same_dept_success(self, lifecycle_cross_dept_data):
        """B部门经理单删本部门损坏记录 → 软删 + 审计落库"""
        data = lifecycle_cross_dept_data
        result = AssetLifecycleMixin.delete_broken_asset(
            recordcode=data["broken_b"].recordcode,
            operator_jobcode="lmgr_b",
            operator_name="B经理",
            user=data["user_b"],
        )
        assert result["status"] == "deleted"
        assert BrokenAsset.all_objects.filter(recordcode=data["broken_b"].recordcode, is_deleted=True).exists()
        assert AssetOperationLog.objects.filter(
            asset_code=data["asset_b"].asset_code,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description__startswith="损坏资产记录删除",
        ).exists()
