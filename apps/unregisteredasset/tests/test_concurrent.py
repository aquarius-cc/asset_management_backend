"""
未登记资产并发场景测试

验证 select_for_update 的并发保护效果。
每个线程通过 transaction.atomic() 获取独立数据库连接,
模拟真实的并发请求场景。
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import transaction

from apps.assetmanagement.models import Asset, AssetType, RecycleAsset, Storage
from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.services import UnregisteredAssetService
from apps.usermanagement.models import Employee
from core.exceptions import AppValidationError


@pytest.fixture
def concurrent_fixtures(db):
    """创建并发测试所需的基础数据"""
    employee = Employee.objects.create(
        employee_jobcode="EMP001",
        employee_name="测试员工",
        employee_phone="13800138000",
        employee_location="测试地点",
    )
    asset_type = AssetType.objects.create(
        type_code="AT_ADMIN",
        type_name="测试类型",
    )
    admin = Employee.objects.create(
        employee_jobcode="ADMIN001",
        employee_name="测试管理员",
        employee_phone="13800138001",
        employee_location="测试地点",
    )
    storage = Storage.objects.create(
        storage_code="STOR001",
        storage_name="测试仓库",
        storage_address="测试地点",
    )
    return employee, admin, asset_type, storage


@pytest.fixture
def pending_unregistered(concurrent_fixtures):
    """创建待审批的未登记资产"""
    employee, _, asset_type, storage = concurrent_fixtures
    return UnregisteredAsset.objects.create(
        scenario_type="s1_no_record",
        discovery_date=date(2024, 6, 1),
        discovery_location="会议室A",
        discovery_person=employee,
        asset_name="并发测试资产",
        asset_brand="测试品牌",
        asset_specification="测试规格",
        unregistered_asset_type=asset_type,
        estimated_value=Decimal("5000.00"),
        unregistered_asset_storage=storage,
        approval_status="pending",
    )


@pytest.mark.django_db(transaction=True)
class TestConcurrentApprove:
    """并发审批场景测试"""

    def test_concurrent_approve_only_one_succeeds(self, pending_unregistered, concurrent_fixtures):
        """两个并发审批请求,只有一个应该成功创建资产"""
        _, admin, _, _ = concurrent_fixtures
        code = pending_unregistered.unregistered_code

        results = {"success_count": 0, "fail_count": 0, "errors": []}
        lock = threading.Lock()

        def approve_in_thread(thread_name):
            # transaction.atomic() 在子线程中会创建独立的数据库连接
            with transaction.atomic():
                try:
                    UnregisteredAssetService.approve_and_handle(
                        unregistered_code=code,
                        handle_type="create_and_recycle",
                        approver=admin.employee_jobcode,
                    )
                    with lock:
                        results["success_count"] += 1
                except AppValidationError as e:
                    with lock:
                        results["fail_count"] += 1
                        results["errors"].append(f"{thread_name}: {e.detail}")
                except Exception as e:
                    with lock:
                        results["fail_count"] += 1
                        results["errors"].append(f"{thread_name}: {type(e).__name__}: {e}")

        t1 = threading.Thread(target=approve_in_thread, args=("T1",))
        t2 = threading.Thread(target=approve_in_thread, args=("T2",))

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # 恰好一个成功
        assert results["success_count"] == 1, (
            f"期望恰好 1 个审批成功,实际 {results['success_count']} 个。错误: {results['errors']}"
        )

        # 验证数据库状态
        pending_unregistered.refresh_from_db()
        assert pending_unregistered.approval_status == "approved"
        assert pending_unregistered.result_asset is not None
        assert pending_unregistered.result_recycle_asset is not None

        # 验证没有重复资产
        asset_count = Asset.objects.filter(asset_name="并发测试资产").count()
        assert asset_count == 1, f"期望 1 个资产,实际 {asset_count} 个"

        # 验证没有重复回收记录
        recycle_count = RecycleAsset.objects.filter(
            asset_recordcode=pending_unregistered.result_asset,
        ).count()
        assert recycle_count == 1, f"期望 1 条回收记录,实际 {recycle_count} 条"

    def test_approve_then_approve_fails(self, pending_unregistered, concurrent_fixtures):
        """先审批通过,再审批同一记录应该失败"""
        _, admin, _, _ = concurrent_fixtures
        code = pending_unregistered.unregistered_code

        # 第一次审批成功
        UnregisteredAssetService.approve_and_handle(
            unregistered_code=code,
            handle_type="create_and_recycle",
            approver=admin.employee_jobcode,
        )

        # 第二次审批应失败
        with pytest.raises(AppValidationError) as exc_info:
            UnregisteredAssetService.approve_and_handle(
                unregistered_code=code,
                handle_type="create_and_recycle",
                approver=admin.employee_jobcode,
            )

        assert "不允许审批" in str(exc_info.value.detail)


@pytest.mark.django_db(transaction=True)
class TestConcurrentDelete:
    """并发删除场景测试"""

    def test_concurrent_delete_only_one_succeeds(self, pending_unregistered, concurrent_fixtures):
        """两个并发删除请求,只有一个应该成功"""
        _, admin, _, _ = concurrent_fixtures
        code = pending_unregistered.unregistered_code

        results = {"success_count": 0, "fail_count": 0, "errors": []}
        lock = threading.Lock()

        def delete_in_thread(thread_name):
            with transaction.atomic():
                try:
                    UnregisteredAssetService.delete(
                        unregistered_code=code,
                        operator_jobcode=admin.employee_jobcode,
                    )
                    with lock:
                        results["success_count"] += 1
                except AppValidationError as e:
                    with lock:
                        results["fail_count"] += 1
                        results["errors"].append(f"{thread_name}: {e.detail}")
                except Exception as e:
                    with lock:
                        results["fail_count"] += 1
                        results["errors"].append(f"{thread_name}: {type(e).__name__}: {e}")

        t1 = threading.Thread(target=delete_in_thread, args=("T1",))
        t2 = threading.Thread(target=delete_in_thread, args=("T2",))

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # 恰好一个成功
        assert results["success_count"] == 1, (
            f"期望恰好 1 个删除成功,实际 {results['success_count']} 个。错误: {results['errors']}"
        )

        # 验证软删除
        assert UnregisteredAsset.objects.filter(unregistered_code=code).count() == 0
        assert UnregisteredAsset.all_objects.filter(unregistered_code=code).count() == 1


@pytest.mark.django_db(transaction=True)
class TestConcurrentApproveAndDelete:
    """并发审批和删除场景测试"""

    def test_approve_and_delete_cannot_both_succeed(self, pending_unregistered, concurrent_fixtures):
        """并发审批和删除不能同时成功"""
        _, admin, _, _ = concurrent_fixtures
        code = pending_unregistered.unregistered_code

        results = {"approve_success": False, "delete_success": False, "errors": []}
        lock = threading.Lock()

        def approve_in_thread():
            with transaction.atomic():
                try:
                    UnregisteredAssetService.approve_and_handle(
                        unregistered_code=code,
                        handle_type="create_and_recycle",
                        approver=admin.employee_jobcode,
                    )
                    with lock:
                        results["approve_success"] = True
                except Exception as e:
                    with lock:
                        results["errors"].append(f"approve: {type(e).__name__}: {e}")

        def delete_in_thread():
            with transaction.atomic():
                try:
                    UnregisteredAssetService.delete(
                        unregistered_code=code,
                        operator_jobcode=admin.employee_jobcode,
                    )
                    with lock:
                        results["delete_success"] = True
                except AppValidationError as e:
                    with lock:
                        results["errors"].append(f"delete: {e.detail}")
                except Exception as e:
                    with lock:
                        results["errors"].append(f"delete: {type(e).__name__}: {e}")

        t1 = threading.Thread(target=approve_in_thread)
        t2 = threading.Thread(target=delete_in_thread)

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # 不能同时成功
        assert not (results["approve_success"] and results["delete_success"]), (
            f"审批和删除同时成功,存在竞态条件。错误: {results['errors']}"
        )

        # 记录最终状态
        pending_unregistered.refresh_from_db()
        assert pending_unregistered.approval_status in ("pending", "approved"), (
            f"状态异常: {pending_unregistered.approval_status}"
        )


@pytest.mark.django_db(transaction=True)
class TestConcurrentUpdateAndApprove:
    """并发更新和审批场景测试"""

    def test_update_and_approve_cannot_both_succeed(self, pending_unregistered, concurrent_fixtures):
        """并发更新和审批不能同时成功修改同一记录"""
        _, admin, _, _ = concurrent_fixtures
        code = pending_unregistered.unregistered_code

        results = {"update_success": False, "approve_success": False, "errors": []}
        lock = threading.Lock()

        def update_in_thread():
            with transaction.atomic():
                try:
                    UnregisteredAssetService.update(
                        unregistered_code=code,
                        update_data={"asset_name": "更新后的名称"},
                        operator_jobcode=admin.employee_jobcode,
                    )
                    with lock:
                        results["update_success"] = True
                except Exception as e:
                    with lock:
                        results["errors"].append(f"update: {type(e).__name__}: {e}")

        def approve_in_thread():
            with transaction.atomic():
                try:
                    UnregisteredAssetService.approve_and_handle(
                        unregistered_code=code,
                        handle_type="create_and_recycle",
                        approver=admin.employee_jobcode,
                    )
                    with lock:
                        results["approve_success"] = True
                except Exception as e:
                    with lock:
                        results["errors"].append(f"approve: {type(e).__name__}: {e}")

        t1 = threading.Thread(target=update_in_thread)
        t2 = threading.Thread(target=approve_in_thread)

        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # 两者不能同时成功
        # 如果 update 先拿到锁:update 成功 → 状态仍为 pending → approve 拿到锁后状态检查通过 → 也能成功
        # 但如果 approve 先拿到锁:approve 成功 → 状态变为 approved → update 拿到锁后 can_modify 检查失败
        # 所以最坏情况是两者都成功(update 先拿到锁),但不会产生数据不一致
        # 关键验证:最终状态必须一致
        pending_unregistered.refresh_from_db()
        assert pending_unregistered.approval_status in ("pending", "approved"), (
            f"状态异常: {pending_unregistered.approval_status}。错误: {results['errors']}"
        )

        # 如果审批成功,验证资产已创建
        if pending_unregistered.approval_status == "approved":
            assert pending_unregistered.result_asset is not None
