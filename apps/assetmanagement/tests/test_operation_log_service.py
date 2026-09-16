"""资产操作日志服务测试"""

import itertools
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.assetmanagement.models import AssetOperationLog
from apps.assetmanagement.services.operation_log_service import (
    OperationLogQueryService,
    OperationLogService,
)
from core.tests import TEST_PASSWORD


@pytest.mark.django_db
class TestLogOperation:
    def test_log_operation_success(self, asset):
        log = OperationLogService.log_operation(
            asset_code=asset.asset_code,
            operation_type="create",
            description="创建资产",
        )
        assert log.pk is not None
        assert log.asset_code == asset.asset_code
        assert log.operation_type == "create"

    def test_log_operation_with_all_fields(self, asset):
        log = OperationLogService.log_operation(
            asset_code=asset.asset_code,
            operation_type="update",
            description="更新资产",
            asset_name="测试资产",
            asset_specification="规格",
            operator_jobcode="U001",
            operator_name="操作人",
            before_data={"name": "旧"},
            after_data={"name": "新"},
            related_record_code="RC001",
            related_record_type="update",
            ip_address="127.0.0.1",
        )
        assert log.operator_jobcode == "U001"
        assert log.before_data == {"name": "旧"}
        assert log.after_data == {"name": "新"}

    def test_log_operation_invalid_type_raises(self, asset):
        with pytest.raises(ValueError, match="无效的操作类型"):
            OperationLogService.log_operation(
                asset_code=asset.asset_code,
                operation_type="invalid_type",
                description="无效操作",
            )

    def test_log_operation_empty_asset_code_raises(self):
        with pytest.raises(ValueError, match="资产编码不能为空"):
            OperationLogService.log_operation(
                asset_code="",
                operation_type="create",
                description="空编码",
            )


@pytest.mark.django_db
class TestLogAssetCreate:
    def test_log_asset_create(self, asset):
        log = OperationLogService.log_asset_create(
            asset=asset,
            operator_jobcode="U001",
            operator_name="创建人",
        )
        assert log.operation_type == "create"
        assert log.after_data is not None
        assert log.after_data["asset_code"] == asset.asset_code


@pytest.mark.django_db
class TestLogAssetUpdate:
    def test_log_asset_update(self, asset):
        log = OperationLogService.log_asset_update(
            asset=asset,
            before_data={"asset_name": "旧名"},
            after_data={"asset_name": "新名"},
            operator_jobcode="U001",
        )
        assert log.operation_type == "update"
        assert "asset_name" in log.description

    def test_log_asset_update_no_changes(self, asset):
        log = OperationLogService.log_asset_update(
            asset=asset,
            before_data={"asset_name": "同名"},
            after_data={"asset_name": "同名"},
        )
        assert log.operation_type == "update"


@pytest.mark.django_db
class TestLogAssetDelete:
    def test_log_asset_delete_with_asset(self, asset):
        log = OperationLogService.log_asset_delete(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset=asset,
        )
        assert log.operation_type == "delete"
        assert log.before_data is not None

    def test_log_asset_delete_without_asset(self):
        log = OperationLogService.log_asset_delete(
            asset_code="DELETED_CODE",
            asset_name="已删除",
        )
        assert log.operation_type == "delete"
        assert log.before_data is None


@pytest.mark.django_db
class TestLogAssetOut:
    def test_log_asset_out(self, asset):
        log = OperationLogService.log_asset_out(
            asset=asset,
            recordcode="OUT001",
        )
        assert log.operation_type == "out"
        assert log.related_record_code == "OUT001"


@pytest.mark.django_db
class TestLogAssetRecycle:
    def test_log_asset_recycle(self, asset):
        log = OperationLogService.log_asset_recycle(
            asset=asset,
            recordcode="REC001",
        )
        assert log.operation_type == "recycle"
        assert log.after_data["asset_current_status"] == "recycled_pending"


@pytest.mark.django_db
class TestLogAssetDamaged:
    def test_log_asset_damaged(self, asset):
        log = OperationLogService.log_asset_damaged(
            asset=asset,
            damaged_record_code="DMG001",
        )
        assert log.operation_type == "damaged"
        assert log.after_data["asset_current_status"] == "damaged"


@pytest.mark.django_db
class TestLogAssetWaste:
    def test_log_asset_waste(self, asset):
        log = OperationLogService.log_asset_waste(
            asset=asset,
            waste_record_code="WST001",
        )
        assert log.operation_type == "waste"
        assert log.after_data["asset_current_status"] == "scrapped"


@pytest.mark.django_db
class TestLogAssetApprove:
    def test_log_approve(self, asset):
        log = OperationLogService.log_asset_approve(
            asset=asset,
            approval_result="approved",
        )
        assert log.operation_type == "approve"
        assert "通过" in log.description

    def test_log_reject(self, asset):
        log = OperationLogService.log_asset_approve(
            asset=asset,
            approval_result="rejected",
        )
        assert "拒绝" in log.description


@pytest.mark.django_db
class TestLogAssetTransfer:
    def test_log_transfer(self, asset):
        log = OperationLogService.log_asset_transfer(
            asset=asset,
            from_storage="仓库A",
            to_storage="仓库B",
        )
        assert log.operation_type == "transfer"
        assert log.before_data["asset_storage"] == "仓库A"
        assert log.after_data["asset_storage"] == "仓库B"


@pytest.mark.django_db
class TestOperationLogQueryService:
    def _create_log(self, asset_code, op_type="create", jobcode="U001"):
        return AssetOperationLog.objects.create(
            asset_code=asset_code,
            operation_type=op_type,
            description=f"测试{op_type}",
            operator_jobcode=jobcode,
        )

    @pytest.fixture
    def query_admin(self, db):
        """无 Employee 记录的 AuthUser:部门范围 None(不过滤),保持既有查询行为断言"""
        from apps.authusermanagement.models import AuthUser

        return AuthUser.objects.create_user(auth_username="ops_q", password=TEST_PASSWORD)

    def test_get_asset_history(self, asset, query_admin):
        self._create_log(asset.asset_code, "create")
        self._create_log(asset.asset_code, "update")
        logs = OperationLogQueryService.get_asset_history(query_admin, asset.asset_code)
        assert len(logs) == 2

    def test_get_asset_history_empty(self, query_admin):
        logs = OperationLogQueryService.get_asset_history(query_admin, "NONEXIST")
        assert len(logs) == 0

    def test_get_recent_operations(self, asset, query_admin):
        self._create_log(asset.asset_code)
        logs = OperationLogQueryService.get_recent_operations(query_admin, days=7)
        assert len(logs) >= 1

    def test_get_operations_by_type(self, asset, query_admin):
        self._create_log(asset.asset_code, "create")
        self._create_log(asset.asset_code, "update")
        logs = OperationLogQueryService.get_operations_by_type("create")
        assert all(log.operation_type == "create" for log in logs)

    def test_get_user_operations(self, asset, query_admin):
        self._create_log(asset.asset_code, jobcode="U001")
        self._create_log(asset.asset_code, jobcode="U002")
        logs = OperationLogQueryService.get_user_operations(query_admin, "U001")
        assert all(log.operator_jobcode == "U001" for log in logs)

    def test_get_asset_status_timeline(self, asset, query_admin):
        self._create_log(asset.asset_code, "create")
        self._create_log(asset.asset_code, "out")
        timeline = OperationLogQueryService.get_asset_status_timeline(query_admin, asset.asset_code)
        assert len(timeline) == 2
        assert "time" in timeline[0]

    def test_get_operation_log_by_logging_id(self, asset, query_admin):
        log = self._create_log(asset.asset_code)
        result = OperationLogQueryService.get_operation_log_by_logging_id(query_admin, log.logging_id)
        assert result is not None
        assert result.pk == log.pk

    def test_get_operation_log_by_logging_id_not_found(self, query_admin):
        result = OperationLogQueryService.get_operation_log_by_logging_id(query_admin, "NONEXIST")
        assert result is None

    def test_get_operation_log_by_pk(self, asset, query_admin):
        log = self._create_log(asset.asset_code)
        result = OperationLogQueryService.get_operation_log_by_pk(query_admin, log.pk)
        assert result is not None
        assert result.pk == log.pk

    def test_get_operation_log_by_pk_not_found(self, query_admin):
        result = OperationLogQueryService.get_operation_log_by_pk(query_admin, 999999)
        assert result is None

    def test_query_operation_logs(self, asset, query_admin):
        self._create_log(asset.asset_code, "create", "U001")
        self._create_log(asset.asset_code, "update", "U002")
        logs = OperationLogQueryService.query_operation_logs(
            query_admin,
            asset_code=asset.asset_code,
            operation_type="create",
        )
        assert len(logs) == 1

    def test_query_operation_logs_by_jobcode(self, asset, query_admin):
        self._create_log(asset.asset_code, "create", "U10")
        self._create_log(asset.asset_code, "update", "U20")
        logs = OperationLogQueryService.query_operation_logs(query_admin, operator_jobcode="U10")
        assert len(logs) == 1

    def test_query_operation_logs_by_time_range(self, asset, query_admin):
        self._create_log(asset.asset_code)
        now = timezone.now()
        logs = OperationLogQueryService.query_operation_logs(
            query_admin,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        assert len(logs) >= 1

    def test_query_operation_logs_empty_filters(self, asset, query_admin):
        self._create_log(asset.asset_code)
        logs = OperationLogQueryService.query_operation_logs(query_admin)
        assert len(logs) >= 1


@pytest.mark.django_db
class TestOperationLogRowIsolation:
    """操作日志行级隔离回归(BE-03):部门级用户不可见他部门资产日志"""

    _phone_seq = itertools.count(1)

    def _make_employee(self, username, role, department):
        from apps.usermanagement.models import Employee

        return Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
            employee_phone=f"138{next(self._phone_seq):08d}",
        )

    def _make_user(self, username, role, department):
        from apps.authusermanagement.models import AuthUser

        self._make_employee(username, role, department)
        return AuthUser.objects.create_user(auth_username=username, password=TEST_PASSWORD)

    def _make_asset(self, code, manager):
        from apps.assetmanagement.models import Asset, AssetType

        asset_type = AssetType.objects.create(type_code=code, type_name=f"类型{code}")
        return Asset.objects.create(
            asset_code=code,
            asset_name=f"资产{code}",
            asset_purchase_price=1000,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_type_recordcode=asset_type,
            asset_manager_recordcode=manager,
            asset_current_status="in_store",
        )

    def _depts(self):
        from apps.usermanagement.models import Department

        return (
            Department.objects.create(department_code="DEPT-A", department_name="A部门"),
            Department.objects.create(department_code="DEPT-B", department_name="B部门"),
        )

    def test_regular_user_cannot_query_other_dept_log(self):
        from apps.usermanagement.models import EmployeeRole

        dept_a, dept_b = self._depts()
        manager_b = self._make_employee("mgr_b", EmployeeRole.ASSET_ADMIN, dept_b)
        asset_b = self._make_asset("AST-B001", manager_b)
        AssetOperationLog.objects.create(
            asset_code=asset_b.asset_code, operation_type="create", description="B资产创建"
        )
        user_a = self._make_user("reg_a1", EmployeeRole.REGULAR_USER, dept_a)

        assert OperationLogQueryService.query_operation_logs(user_a, asset_code="AST-B001") == []

    def test_sysadmin_sees_all_logs(self):
        from apps.usermanagement.models import EmployeeRole

        dept_a, dept_b = self._depts()
        manager_b = self._make_employee("mgr_b", EmployeeRole.ASSET_ADMIN, dept_b)
        asset_b = self._make_asset("AST-B002", manager_b)
        AssetOperationLog.objects.create(
            asset_code=asset_b.asset_code, operation_type="create", description="B资产创建"
        )
        admin = self._make_user("ops_adm", EmployeeRole.SYSTEM_ADMIN, dept_a)

        assert len(OperationLogQueryService.query_operation_logs(admin, asset_code="AST-B002")) == 1

    def test_dept_user_sees_own_dept_log(self):
        from apps.usermanagement.models import EmployeeRole

        dept_a, _ = self._depts()
        manager_a = self._make_employee("mgr_a", EmployeeRole.ASSET_ADMIN, dept_a)
        asset_a = self._make_asset("AST-A001", manager_a)
        AssetOperationLog.objects.create(
            asset_code=asset_a.asset_code, operation_type="create", description="A资产创建"
        )
        user_a = self._make_user("reg_a2", EmployeeRole.REGULAR_USER, dept_a)

        assert len(OperationLogQueryService.query_operation_logs(user_a, asset_code="AST-A001")) == 1

    def test_api_regular_user_list_returns_empty(self):
        from rest_framework.test import APIClient

        from apps.usermanagement.models import EmployeeRole

        dept_a, dept_b = self._depts()
        manager_b = self._make_employee("mgr_b", EmployeeRole.ASSET_ADMIN, dept_b)
        asset_b = self._make_asset("AST-B003", manager_b)
        AssetOperationLog.objects.create(
            asset_code=asset_b.asset_code, operation_type="create", description="B资产创建"
        )
        user_a = self._make_user("reg_a3", EmployeeRole.REGULAR_USER, dept_a)

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/v1/assets/operation-logs/", {"asset_code": "AST-B003"})

        assert resp.status_code == 200
        assert resp.data["data"]["count"] == 0
        assert resp.data["data"]["results"] == []

    def test_api_regular_user_detail_returns_404(self):
        from rest_framework.test import APIClient

        from apps.usermanagement.models import EmployeeRole

        dept_a, dept_b = self._depts()
        manager_b = self._make_employee("mgr_b", EmployeeRole.ASSET_ADMIN, dept_b)
        asset_b = self._make_asset("AST-B004", manager_b)
        log = AssetOperationLog.objects.create(
            asset_code=asset_b.asset_code, operation_type="create", description="B资产创建"
        )
        user_a = self._make_user("reg_a4", EmployeeRole.REGULAR_USER, dept_a)

        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get(f"/api/v1/assets/operation-logs/{log.pk}/")

        assert resp.status_code == 404
        assert resp.data["code"] == 404
