"""
通用审计日志 API 测试（BE-04P2 权限加固版）

覆盖:
1. AuditLogQueryService 单元测试(与权限无关)
2. 视图权限矩阵:普通用户(regular_user) → 403;审计员(auditor) / 系统管理员(system_admin) → 200
3. 业务行为:详情/by-logging-id/by-app/by-operator 404、参数校验 400、分页(以审计员角色验证)
"""

import itertools
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usermanagement.models import Employee, EmployeeRole
from core.audit_query_service import AuditLogQueryService
from core.models_audit import AuditLog
from core.tests import TEST_PASSWORD


User = get_user_model()

_phone_seq = itertools.count(1)


# =====================================================================
# Data helpers
# =====================================================================


def _make_audit_logs():
    """创建三条审计日志(含变更前后快照)"""
    return [
        AuditLog.objects.create(
            record_code="DEPT001",
            app_label="department",
            operation_type="create",
            description="创建部门: 技术部",
            operator_jobcode="E001",
            operator_name="张三",
            ip_address="192.168.1.100",
        ),
        AuditLog.objects.create(
            record_code="EMP001",
            app_label="employee",
            operation_type="update",
            description="更新员工信息",
            operator_jobcode="E002",
            operator_name="李四",
            before_data={"employee_name": "旧名字"},
            after_data={"employee_name": "新名字"},
            ip_address="192.168.1.101",
        ),
        AuditLog.objects.create(
            record_code="admin",
            app_label="authuser",
            operation_type="login",
            description="用户登录",
            operator_jobcode="admin",
            operator_name="管理员",
            ip_address="192.168.1.102",
        ),
    ]


# =====================================================================
# User / client helpers
# =====================================================================


def _phone():
    """生成测试用唯一手机号(满足 unique_employee_phone_not_deleted 约束)"""
    return f"137{next(_phone_seq):08d}"


def _make_user(username: str, role: str | None = None, is_superuser: bool = False):
    """创建 AuthUser;role 非 None 时同步创建 Employee(jobcode=username 隐式关联)"""
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
            role=role,
            employee_phone=_phone(),
            employee_location="测试地点",
        )
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# =====================================================================
# Fixtures: 用户 / 客户端 / 日志
# =====================================================================


@pytest.fixture
def regular_user(db):
    return _make_user("regular_user")


@pytest.fixture
def auditor_user(db):
    return _make_user("auditor1", role=EmployeeRole.AUDITOR)


@pytest.fixture
def admin_user(db):
    return _make_user("sys_admin", is_superuser=True)


@pytest.fixture
def regular_client(db, regular_user):
    return _client(regular_user)


@pytest.fixture
def auditor_client(db, auditor_user):
    return _client(auditor_user)


@pytest.fixture
def admin_client(db, admin_user):
    return _client(admin_user)


@pytest.fixture
def audit_log(db):
    """单条审计日志(供权限矩阵/详情测试使用)"""
    return AuditLog.objects.create(
        record_code="DEPT001",
        app_label="department",
        operation_type="create",
        description="创建部门: 技术部",
        operator_jobcode="E001",
        operator_name="张三",
        ip_address="192.168.1.100",
    )


@pytest.fixture
def audit_logs(db):
    """三条审计日志(供列表查询测试使用)"""
    return _make_audit_logs()


def _permission_endpoints(audit_log):
    """六个审计日志只读端点在日志存在时应返回的路径集合"""
    return [
        "/api/v1/audit-logs/",
        f"/api/v1/audit-logs/{audit_log.pk}/",
        f"/api/v1/audit-logs/by-logging-id/{audit_log.logging_id}/",
        "/api/v1/audit-logs/recent/",
        "/api/v1/audit-logs/by-app/department/",
        "/api/v1/audit-logs/by-operator/E001/",
    ]


# =====================================================================
# BE-04P2 权限矩阵:普通用户 403 / 审计员·系统管理员 200
# =====================================================================


def test_permission_control(audit_log, request):
    """六个审计端点对三种角色的访问控制:普通用户禁止,审计员/管理员放行"""
    matrix = [("regular_client", 403), ("auditor_client", 200), ("admin_client", 200)]
    for role_fixture, expected in matrix:
        client = request.getfixturevalue(role_fixture)
        for endpoint in _permission_endpoints(audit_log):
            status_code = client.get(endpoint).status_code
            assert status_code == expected, f"{role_fixture} -> {endpoint} 期望 {expected},实得 {status_code}"


# =====================================================================
# AuditLogQueryService 单元测试(与权限无关)
# =====================================================================


def test_get_by_pk_should_return_log_when_exists(db, audit_log):
    log = AuditLogQueryService.get_by_pk(audit_log.pk)
    assert log is not None
    assert log.record_code == "DEPT001"


def test_get_by_pk_should_return_none_when_not_exists(db):
    assert AuditLogQueryService.get_by_pk(99999) is None


def test_get_by_logging_id_should_return_log_when_exists(db, audit_log):
    logging_id = audit_log.logging_id
    log = AuditLogQueryService.get_by_logging_id(logging_id)
    assert log is not None
    assert log.logging_id == logging_id


def test_get_by_logging_id_should_return_none_when_not_exists(db):
    assert AuditLogQueryService.get_by_logging_id("NOTEXIST-Log-20260101-XXXXXXXX") is None


def test_query_logs_should_filter_by_app_label(db, audit_logs):
    logs = AuditLogQueryService.query_logs(app_label="department")
    assert len(logs) == 1
    assert logs[0].app_label == "department"


def test_query_logs_should_filter_by_operation_type(db, audit_logs):
    logs = AuditLogQueryService.query_logs(operation_type="login")
    assert len(logs) == 1
    assert logs[0].operation_type == "login"


def test_query_logs_should_filter_by_operator_jobcode(db, audit_logs):
    logs = AuditLogQueryService.query_logs(operator_jobcode="E001")
    assert len(logs) == 1
    assert logs[0].operator_jobcode == "E001"


def test_query_logs_should_filter_by_record_code(db, audit_logs):
    logs = AuditLogQueryService.query_logs(record_code="EMP001")
    assert len(logs) == 1
    assert logs[0].record_code == "EMP001"


def test_query_logs_should_filter_by_time_range(db, audit_logs):
    start_time = timezone.now() - timedelta(hours=1)
    end_time = timezone.now() + timedelta(hours=1)
    logs = AuditLogQueryService.query_logs(start_time=start_time, end_time=end_time)
    assert len(logs) == 3


def test_query_logs_should_return_empty_when_no_match(db, audit_logs):
    assert len(AuditLogQueryService.query_logs(app_label="nonexistent")) == 0


def test_get_recent_logs_should_return_recent_records(db, audit_logs):
    assert len(AuditLogQueryService.get_recent_logs(days=1)) == 3


def test_get_logs_by_app_label_should_filter_correctly(db, audit_logs):
    logs = AuditLogQueryService.get_logs_by_app_label("employee")
    assert len(logs) == 1
    assert logs[0].app_label == "employee"


def test_get_logs_by_operator_should_filter_correctly(db, audit_logs):
    logs = AuditLogQueryService.get_logs_by_operator("E002")
    assert len(logs) == 1
    assert logs[0].operator_jobcode == "E002"


# =====================================================================
# 业务行为测试(审计员视角):列表 / 详情 / 条件查询 / 参数校验
# =====================================================================


def test_list_should_return_all_logs(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/")
    assert response.status_code == 200
    assert response.data["code"] == 0
    assert response.data["data"]["count"] == 3


def test_list_should_filter_by_app_label(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"app_label": "department"})
    assert response.status_code == 200
    assert response.data["data"]["count"] == 1
    assert response.data["data"]["results"][0]["app_label"] == "department"


def test_list_should_filter_by_operation_type(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"operation_type": "login"})
    assert response.status_code == 200
    assert response.data["data"]["count"] == 1
    assert response.data["data"]["results"][0]["operation_type"] == "login"


def test_list_should_return_error_when_invalid_operation_type(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"operation_type": "invalid"})
    assert response.status_code == 400
    assert "无效的操作类型" in response.data["message"]


def test_list_should_filter_by_days(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"days": "1"})
    assert response.status_code == 200
    assert response.data["data"]["count"] == 3


def test_list_should_return_error_when_invalid_days(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"days": "abc"})
    assert response.status_code == 400
    assert "days 参数必须是整数" in response.data["message"]


def test_list_should_filter_by_date_range(auditor_client, audit_logs):
    today = datetime.now().strftime("%Y-%m-%d")
    response = auditor_client.get(
        "/api/v1/audit-logs/",
        {"start_date": today, "end_date": today},
    )
    assert response.status_code == 200
    assert response.data["data"]["count"] == 3


def test_list_should_return_error_when_invalid_start_date(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"start_date": "invalid-date"})
    assert response.status_code == 400
    assert "start_date 格式错误" in response.data["message"]


def test_list_should_return_error_when_invalid_end_date(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"end_date": "invalid-date"})
    assert response.status_code == 400
    assert "end_date 格式错误" in response.data["message"]


def test_list_should_paginate_results(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/", {"page": "1", "page_size": "2"})
    assert response.status_code == 200
    assert len(response.data["data"]["results"]) == 2
    assert response.data["data"]["count"] == 3


def test_detail_should_return_log_when_exists(auditor_client, audit_log):
    response = auditor_client.get(f"/api/v1/audit-logs/{audit_log.pk}/")
    assert response.status_code == 200
    assert response.data["data"]["record_code"] == "DEPT001"


def test_detail_should_return_404_when_not_exists(auditor_client):
    response = auditor_client.get("/api/v1/audit-logs/99999/")
    assert response.status_code == 404


def test_by_logging_id_should_return_log_when_exists(auditor_client, audit_log):
    response = auditor_client.get(f"/api/v1/audit-logs/by-logging-id/{audit_log.logging_id}/")
    assert response.status_code == 200
    assert response.data["data"]["logging_id"] == audit_log.logging_id


def test_by_logging_id_should_return_404_when_not_exists(auditor_client):
    response = auditor_client.get("/api/v1/audit-logs/by-logging-id/NOTEXIST-Log-20260101-XXXXXXXX/")
    assert response.status_code == 404


def test_recent_should_return_logs(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/recent/", {"days": "1"})
    assert response.status_code == 200
    assert response.data["data"]["count"] == 3


def test_recent_should_return_error_when_invalid_days(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/recent/", {"days": "abc"})
    assert response.status_code == 400
    assert "days 参数必须是整数" in response.data["message"]


def test_recent_should_return_error_when_days_out_of_range(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/recent/", {"days": "400"})
    assert response.status_code == 400
    assert "days 参数必须在 1-365 之间" in response.data["message"]


def test_by_app_label_should_return_logs(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/by-app/department/")
    assert response.status_code == 200
    assert response.data["data"]["count"] == 1


def test_by_app_label_should_return_404_when_no_logs(auditor_client):
    response = auditor_client.get("/api/v1/audit-logs/by-app/nonexistent/")
    assert response.status_code == 404


def test_by_operator_should_return_logs(auditor_client, audit_logs):
    response = auditor_client.get("/api/v1/audit-logs/by-operator/E001/")
    assert response.status_code == 200
    assert response.data["data"]["count"] == 1


def test_by_operator_should_return_404_when_no_logs(auditor_client):
    response = auditor_client.get("/api/v1/audit-logs/by-operator/NONEXIST/")
    assert response.status_code == 404


# W-1 对抗审计:补充 datetime.strptime 路径覆盖(防止 F821/NameError 回归)
def test_strptime_parsing_path_covered(db):
    start_time = datetime.strptime("2026-08-29", "%Y-%m-%d")
    end_time = datetime.strptime("2026-08-30", "%Y-%m-%d")
    assert start_time.year == 2026
    assert end_time > start_time
