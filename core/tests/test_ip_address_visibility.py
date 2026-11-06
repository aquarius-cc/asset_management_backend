"""[BF-182 / M-22-F14-A] ip_address 仅系统管理员可见——双暴露面角色契约（CT-4）。

拍板 A（2026-11-06）：ip_address 仅系统管理员可见。两个暴露面：
- 资产操作日志面（IsAuthenticated，全角色可达）：AssetOperationLogSerializer
  运行时按 context["request"] 角色剔除（列表 / 详情 / 资产 logs action）；
  服务端导出列清单本就不含 IP 列（首日实证，零改动，不属本契约）。
- 通用审计日志面（IsAuditorOrAdmin，auditor 为主要受影响角色）：
  AuditLogSerializer 运行时剔除（列表 / 详情），AuditLogExportView 动态剔 IP 导出列。

为何置于 core/tests：契约横跨 assetmanagement + core 两个 app
（DR-4 先例 test_export_columns_contract.py）。
角色判定单源 = core.permissions.is_system_admin（DR-1，与前端 usePermission().isAdmin 对称）。

CT-4 先红后绿：stash 四个源文件（序列化器 ×1 + 视图 ×3）→ 本文件非管理员断言全红 →
pop → 全绿（红/绿证据见账本 BF-182 验证记录）。
"""

import io
import itertools

import pytest
from django.contrib.auth import get_user_model
from openpyxl import load_workbook
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.assetmanagement.models import Asset, AssetOperationLog, AssetType, Storage
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.audit_log_views import AuditLogExportView
from core.models_audit import AuditLog
from core.tests import TEST_PASSWORD


User = get_user_model()

OP_LOG_LIST_URL = "/api/v1/assets/operation-logs/"
AUDIT_LOG_LIST_URL = "/api/v1/audit-logs/"
AUDIT_LOG_EXPORT_URL = "/api/v1/audit-logs/export/"
ASSET_LOGS_ACTION_TEMPLATE = "/api/v1/assets/assets/{asset_code}/logs/"

TEST_IP = "192.168.77.100"
ASSET_CODE = "AST-BF182"
RECORD_CODE = "DEPT-BF182"

_seq = itertools.count(1)

# 审计导出列（管理员口径）与类级 export_columns 声明逐一对应（DR-1）
AUDIT_EXPORT_HEADERS_ADMIN = [
    "记录编码",
    "应用标识",
    "操作类型",
    "操作时间",
    "操作人工号",
    "操作人姓名",
    "操作描述",
    "IP地址",
]


def _phone() -> str:
    return f"139{next(_seq):08d}"


def _make_user(username: str, role: str | None = None, is_superuser: bool = False, department=None):
    """创建 AuthUser；role 非 None 时同步创建 Employee（jobcode=username 隐式关联）。"""
    if is_superuser:
        return User.objects.create_superuser(
            auth_username=username,
            email=f"{username}@example.com",
            password=TEST_PASSWORD,
            auth_phone=_phone(),
        )
    user = User.objects.create_user(auth_username=username, password=TEST_PASSWORD, auth_phone=_phone())
    if role is not None:
        Employee.objects.create(
            employee_jobcode=username,
            employee_name=f"{username}员工",
            employee_department=department,
            role=role,
            employee_phone=_phone(),
            employee_location="测试地点",
        )
    return user


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _seed_op_log() -> AssetOperationLog:
    return AssetOperationLog.objects.create(
        asset_code=ASSET_CODE,
        asset_name="IP可见性测试资产",
        operation_type="update",
        description="BF-182 IP 可见性契约",
        ip_address=TEST_IP,
    )


def _seed_audit_log() -> AuditLog:
    return AuditLog.objects.create(
        record_code=RECORD_CODE,
        app_label="department",
        operation_type="create",
        description="BF-182 IP 可见性契约",
        operator_jobcode="E100",
        operator_name="IP测试操作人",
        ip_address=TEST_IP,
    )


def _make_asset(department: Department) -> Asset:
    keeper = Employee.objects.create(
        employee_jobcode=f"KP-{department.department_code}",
        employee_name="保管人",
        employee_department=department,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    manager = Employee.objects.create(
        employee_jobcode=f"WH-{department.department_code}",
        employee_name="仓管",
        employee_department=department,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=_phone(),
    )
    storage = Storage.objects.create(
        storage_code=f"ST-{department.department_code}",
        storage_name=f"{department.department_name}仓库",
        storage_address=f"{department.department_name}地址",
        storage_manager=manager,
    )
    asset_type = AssetType.objects.create(type_code=f"AT-{department.department_code}", type_name="测试类型")
    return Asset.objects.create(
        asset_code=ASSET_CODE,
        asset_name="IP可见性测试资产",
        asset_purchase_price=1000,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_type_recordcode=asset_type,
        asset_storage_recordcode=storage,
        asset_entry_person_recordcode=keeper,
        asset_current_status="in_store",
    )


def _audit_export_headers(user) -> list[str]:
    """调用审计导出端点并返回 xlsx 表头行（排除空值）。"""
    request = APIRequestFactory().get(AUDIT_LOG_EXPORT_URL)
    force_authenticate(request, user=user)
    response = AuditLogExportView.as_view()(request)
    assert response.status_code == 200, getattr(response, "data", response.status_code)
    try:
        payload = b"".join(response.streaming_content)
    finally:
        response.close()
    sheet = load_workbook(io.BytesIO(payload))["审计日志"]
    return [header for header in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True)) if header]


# 流式响应 close() 触发 close_old_connections，与 pytest-django 默认原子事务冲突
# （同型先例 test_operation_log_export_scope.py / test_audit_log_export.py）。
pytestmark = pytest.mark.django_db(transaction=True)


# =====================================================================
# 资产操作日志面（IsAuthenticated：系统管理员可见 / 审计员不可见）
# =====================================================================


class TestOperationLogIpVisibility:
    def test_list_system_admin_sees_ip(self):
        _seed_op_log()
        admin = _make_user("bf182-op-admin", is_superuser=True)
        resp = _client(admin).get(OP_LOG_LIST_URL)
        assert resp.status_code == 200, resp.data
        row = next(r for r in resp.data["data"]["results"] if r["asset_code"] == ASSET_CODE)
        assert row["ip_address"] == TEST_IP

    def test_list_auditor_ip_key_absent(self):
        _seed_op_log()
        auditor = _make_user("bf182-op-auditor", role=EmployeeRole.AUDITOR)
        resp = _client(auditor).get(OP_LOG_LIST_URL)
        assert resp.status_code == 200, resp.data
        row = next(r for r in resp.data["data"]["results"] if r["asset_code"] == ASSET_CODE)
        assert "ip_address" not in row

    def test_detail_system_admin_sees_ip(self):
        log = _seed_op_log()
        admin = _make_user("bf182-opd-admin", is_superuser=True)
        resp = _client(admin).get(f"{OP_LOG_LIST_URL}{log.pk}/")
        assert resp.status_code == 200, resp.data
        assert resp.data["data"]["ip_address"] == TEST_IP

    def test_detail_auditor_ip_key_absent(self):
        log = _seed_op_log()
        auditor = _make_user("bf182-opd-auditor", role=EmployeeRole.AUDITOR)
        resp = _client(auditor).get(f"{OP_LOG_LIST_URL}{log.pk}/")
        assert resp.status_code == 200, resp.data
        assert "ip_address" not in resp.data["data"]

    def test_asset_logs_action_system_admin_sees_ip(self):
        dept = Department.objects.create(department_code="BF182-A", department_name="BF-182资产部门")
        asset = _make_asset(dept)
        _seed_op_log()
        admin = _make_user("bf182-act-admin", is_superuser=True)
        # AssetViewSet lookup_field="recordcode"（非 asset_code），URL 段用 recordcode
        resp = _client(admin).get(ASSET_LOGS_ACTION_TEMPLATE.format(asset_code=asset.recordcode))
        assert resp.status_code == 200, resp.data
        logs = resp.data["data"]
        assert logs, "资产 logs action 应返回该资产的操作记录"
        assert logs[0]["ip_address"] == TEST_IP

    def test_asset_logs_action_dept_manager_ip_absent(self):
        """部门经理（非系统管理员）可见本部门资产的日志，但 IP 键必须缺失。"""
        dept = Department.objects.create(department_code="BF182-D", department_name="BF-182经理部门")
        manager = _make_user("bf182-act-mgr", role=EmployeeRole.DEPT_MANAGER, department=dept)
        asset = _make_asset(dept)
        _seed_op_log()
        resp = _client(manager).get(ASSET_LOGS_ACTION_TEMPLATE.format(asset_code=asset.recordcode))
        assert resp.status_code == 200, resp.data
        logs = resp.data["data"]
        assert logs, "部门经理应看到本部门资产的操作记录"
        assert "ip_address" not in logs[0]


# =====================================================================
# 通用审计日志面（IsAuditorOrAdmin：系统管理员可见 / 审计员不可见）
# =====================================================================


class TestAuditLogIpVisibility:
    def test_list_system_admin_sees_ip(self):
        _seed_audit_log()
        admin = _make_user("bf182-ad-admin", is_superuser=True)
        resp = _client(admin).get(AUDIT_LOG_LIST_URL)
        assert resp.status_code == 200, resp.data
        row = next(r for r in resp.data["data"]["results"] if r["record_code"] == RECORD_CODE)
        assert row["ip_address"] == TEST_IP

    def test_list_auditor_ip_key_absent(self):
        _seed_audit_log()
        auditor = _make_user("bf182-ad-auditor", role=EmployeeRole.AUDITOR)
        resp = _client(auditor).get(AUDIT_LOG_LIST_URL)
        assert resp.status_code == 200, resp.data
        row = next(r for r in resp.data["data"]["results"] if r["record_code"] == RECORD_CODE)
        assert "ip_address" not in row

    def test_detail_by_logging_id_system_admin_sees_ip(self):
        log = _seed_audit_log()
        admin = _make_user("bf182-add-admin", is_superuser=True)
        resp = _client(admin).get(f"/api/v1/audit-logs/by-logging-id/{log.logging_id}/")
        assert resp.status_code == 200, resp.data
        assert resp.data["data"]["ip_address"] == TEST_IP

    def test_detail_by_logging_id_auditor_ip_key_absent(self):
        log = _seed_audit_log()
        auditor = _make_user("bf182-add-auditor", role=EmployeeRole.AUDITOR)
        resp = _client(auditor).get(f"/api/v1/audit-logs/by-logging-id/{log.logging_id}/")
        assert resp.status_code == 200, resp.data
        assert "ip_address" not in resp.data["data"]

    def test_export_system_admin_has_ip_column(self):
        _seed_audit_log()
        admin = _make_user("bf182-ae-admin", is_superuser=True)
        assert _audit_export_headers(admin) == AUDIT_EXPORT_HEADERS_ADMIN

    def test_export_auditor_ip_column_absent(self):
        """审计员导出：IP 列剔除，其余 7 列与顺序不变（与前端客户端导出双保险）。"""
        _seed_audit_log()
        auditor = _make_user("bf182-ae-auditor", role=EmployeeRole.AUDITOR)
        assert _audit_export_headers(auditor) == AUDIT_EXPORT_HEADERS_ADMIN[:-1]
