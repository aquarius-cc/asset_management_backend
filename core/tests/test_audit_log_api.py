"""
通用审计日志 API 测试

测试 AuditLog 查询 API 的各种场景:
1. 列表查询(多条件组合)
2. 详情查询(按 pk)
3. 详情查询(按 logging_id)
4. 最近审计日志查询
5. 按应用标识查询
6. 按操作人查询
7. 参数校验(无效操作类型、日期格式错误等)
"""

from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.audit_query_service import AuditLogQueryService
from core.models_audit import AuditLog


class AuditLogQueryServiceTest(TestCase):
    """AuditLogQueryService 单元测试"""

    def setUp(self):
        """创建测试用审计日志数据"""
        self.logs = []
        log_data = [
            {
                "record_code": "DEPT001",
                "app_label": "department",
                "operation_type": "create",
                "description": "创建部门: 技术部",
                "operator_jobcode": "E001",
                "operator_name": "张三",
                "ip_address": "192.168.1.100",
            },
            {
                "record_code": "EMP001",
                "app_label": "employee",
                "operation_type": "update",
                "description": "更新员工信息",
                "operator_jobcode": "E002",
                "operator_name": "李四",
                "before_data": {"employee_name": "旧名字"},
                "after_data": {"employee_name": "新名字"},
                "ip_address": "192.168.1.101",
            },
            {
                "record_code": "admin",
                "app_label": "authuser",
                "operation_type": "login",
                "description": "用户登录",
                "operator_jobcode": "admin",
                "operator_name": "管理员",
                "ip_address": "192.168.1.102",
            },
        ]
        for data in log_data:
            self.logs.append(AuditLog.objects.create(**data))

    def test_get_by_pk_should_return_log_when_exists(self):
        """按 pk 查询应返回存在的记录"""
        log = AuditLogQueryService.get_by_pk(self.logs[0].pk)
        self.assertIsNotNone(log)
        self.assertEqual(log.record_code, "DEPT001")

    def test_get_by_pk_should_return_none_when_not_exists(self):
        """按 pk 查询不存在的记录应返回 None"""
        log = AuditLogQueryService.get_by_pk(99999)
        self.assertIsNone(log)

    def test_get_by_logging_id_should_return_log_when_exists(self):
        """按 logging_id 查询应返回存在的记录"""
        logging_id = self.logs[0].logging_id
        log = AuditLogQueryService.get_by_logging_id(logging_id)
        self.assertIsNotNone(log)
        self.assertEqual(log.logging_id, logging_id)

    def test_get_by_logging_id_should_return_none_when_not_exists(self):
        """按 logging_id 查询不存在的记录应返回 None"""
        log = AuditLogQueryService.get_by_logging_id("NOTEXIST-Log-20260101-XXXXXXXX")
        self.assertIsNone(log)

    def test_query_logs_should_filter_by_app_label(self):
        """按 app_label 过滤应返回正确结果"""
        logs = AuditLogQueryService.query_logs(app_label="department")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].app_label, "department")

    def test_query_logs_should_filter_by_operation_type(self):
        """按 operation_type 过滤应返回正确结果"""
        logs = AuditLogQueryService.query_logs(operation_type="login")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].operation_type, "login")

    def test_query_logs_should_filter_by_operator_jobcode(self):
        """按 operator_jobcode 过滤应返回正确结果"""
        logs = AuditLogQueryService.query_logs(operator_jobcode="E001")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].operator_jobcode, "E001")

    def test_query_logs_should_filter_by_record_code(self):
        """按 record_code 过滤应返回正确结果"""
        logs = AuditLogQueryService.query_logs(record_code="EMP001")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].record_code, "EMP001")

    def test_query_logs_should_filter_by_time_range(self):
        """按时间范围过滤应返回正确结果"""
        now = timezone.now()
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)
        logs = AuditLogQueryService.query_logs(start_time=start_time, end_time=end_time)
        self.assertEqual(len(logs), 3)

    def test_query_logs_should_return_empty_when_no_match(self):
        """无匹配时应返回空列表"""
        logs = AuditLogQueryService.query_logs(app_label="nonexistent")
        self.assertEqual(len(logs), 0)

    def test_get_recent_logs_should_return_recent_records(self):
        """最近 N 天查询应返回最近的记录"""
        logs = AuditLogQueryService.get_recent_logs(days=1)
        self.assertEqual(len(logs), 3)

    def test_get_logs_by_app_label_should_filter_correctly(self):
        """按应用标识查询应返回正确结果"""
        logs = AuditLogQueryService.get_logs_by_app_label("employee")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].app_label, "employee")

    def test_get_logs_by_operator_should_filter_correctly(self):
        """按操作人查询应返回正确结果"""
        logs = AuditLogQueryService.get_logs_by_operator("E002")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].operator_jobcode, "E002")


class AuditLogListViewTest(TestCase):
    """AuditLogListView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.logs = []
        log_data = [
            {
                "record_code": "DEPT001",
                "app_label": "department",
                "operation_type": "create",
                "description": "创建部门: 技术部",
                "operator_jobcode": "E001",
                "operator_name": "张三",
                "ip_address": "192.168.1.100",
            },
            {
                "record_code": "EMP001",
                "app_label": "employee",
                "operation_type": "update",
                "description": "更新员工信息",
                "operator_jobcode": "E002",
                "operator_name": "李四",
                "before_data": {"employee_name": "旧名字"},
                "after_data": {"employee_name": "新名字"},
                "ip_address": "192.168.1.101",
            },
            {
                "record_code": "admin",
                "app_label": "authuser",
                "operation_type": "login",
                "description": "用户登录",
                "operator_jobcode": "admin",
                "operator_name": "管理员",
                "ip_address": "192.168.1.102",
            },
        ]
        for data in log_data:
            self.logs.append(AuditLog.objects.create(**data))

    def test_list_should_return_all_logs(self):
        """列表查询应返回所有审计日志"""
        response = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 0)
        self.assertEqual(response.data["data"]["count"], 3)

    def test_list_should_filter_by_app_label(self):
        """按 app_label 过滤应返回正确结果"""
        response = self.client.get("/api/v1/audit-logs/", {"app_label": "department"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["app_label"], "department")

    def test_list_should_filter_by_operation_type(self):
        """按 operation_type 过滤应返回正确结果"""
        response = self.client.get("/api/v1/audit-logs/", {"operation_type": "login"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)
        self.assertEqual(response.data["data"]["results"][0]["operation_type"], "login")

    def test_list_should_return_error_when_invalid_operation_type(self):
        """无效操作类型应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/", {"operation_type": "invalid"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("无效的操作类型", response.data["message"])

    def test_list_should_filter_by_days(self):
        """按 days 过滤应返回正确结果"""
        response = self.client.get("/api/v1/audit-logs/", {"days": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 3)

    def test_list_should_return_error_when_invalid_days(self):
        """无效 days 参数应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/", {"days": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("days 参数必须是整数", response.data["message"])

    def test_list_should_filter_by_date_range(self):
        """按日期范围过滤应返回正确结果"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = self.client.get(
            "/api/v1/audit-logs/",
            {
                "start_date": today,
                "end_date": today,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 3)

    def test_list_should_return_error_when_invalid_start_date(self):
        """无效 start_date 格式应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/", {"start_date": "invalid-date"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date 格式错误", response.data["message"])

    def test_list_should_return_error_when_invalid_end_date(self):
        """无效 end_date 格式应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/", {"end_date": "invalid-date"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("end_date 格式错误", response.data["message"])

    def test_list_should_paginate_results(self):
        """列表查询应支持分页"""
        response = self.client.get("/api/v1/audit-logs/", {"page": "1", "page_size": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]["results"]), 2)
        self.assertEqual(response.data["data"]["count"], 3)


class AuditLogDetailViewTest(TestCase):
    """AuditLogDetailView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.log = AuditLog.objects.create(
            record_code="DEPT001",
            app_label="department",
            operation_type="create",
            description="创建部门: 技术部",
            operator_jobcode="E001",
            operator_name="张三",
            ip_address="192.168.1.100",
        )

    def test_detail_should_return_log_when_exists(self):
        """详情查询应返回存在的记录"""
        response = self.client.get(f"/api/v1/audit-logs/{self.log.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["record_code"], "DEPT001")

    def test_detail_should_return_404_when_not_exists(self):
        """详情查询不存在的记录应返回 404"""
        response = self.client.get("/api/v1/audit-logs/99999/")
        self.assertEqual(response.status_code, 404)


class AuditLogByLoggingIdViewTest(TestCase):
    """AuditLogByLoggingIdView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.log = AuditLog.objects.create(
            record_code="DEPT001",
            app_label="department",
            operation_type="create",
            description="创建部门: 技术部",
            operator_jobcode="E001",
            operator_name="张三",
            ip_address="192.168.1.100",
        )

    def test_by_logging_id_should_return_log_when_exists(self):
        """按 logging_id 查询应返回存在的记录"""
        response = self.client.get(f"/api/v1/audit-logs/by-logging-id/{self.log.logging_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["logging_id"], self.log.logging_id)

    def test_by_logging_id_should_return_404_when_not_exists(self):
        """按 logging_id 查询不存在的记录应返回 404"""
        response = self.client.get("/api/v1/audit-logs/by-logging-id/NOTEXIST-Log-20260101-XXXXXXXX/")
        self.assertEqual(response.status_code, 404)


class RecentAuditLogsViewTest(TestCase):
    """RecentAuditLogsView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.logs = []
        log_data = [
            {
                "record_code": "DEPT001",
                "app_label": "department",
                "operation_type": "create",
                "description": "创建部门: 技术部",
                "operator_jobcode": "E001",
                "operator_name": "张三",
                "ip_address": "192.168.1.100",
            },
        ]
        for data in log_data:
            self.logs.append(AuditLog.objects.create(**data))

    def test_recent_should_return_logs(self):
        """最近审计日志查询应返回结果"""
        response = self.client.get("/api/v1/audit-logs/recent/", {"days": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_recent_should_return_error_when_invalid_days(self):
        """无效 days 参数应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/recent/", {"days": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("days 参数必须是整数", response.data["message"])

    def test_recent_should_return_error_when_days_out_of_range(self):
        """days 超出范围应返回 400 错误"""
        response = self.client.get("/api/v1/audit-logs/recent/", {"days": "400"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("days 参数必须在 1-365 之间", response.data["message"])


class AuditLogsByAppLabelViewTest(TestCase):
    """AuditLogsByAppLabelView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.log = AuditLog.objects.create(
            record_code="DEPT001",
            app_label="department",
            operation_type="create",
            description="创建部门: 技术部",
            operator_jobcode="E001",
            operator_name="张三",
            ip_address="192.168.1.100",
        )

    def test_by_app_label_should_return_logs(self):
        """按应用标识查询应返回结果"""
        response = self.client.get("/api/v1/audit-logs/by-app/department/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_by_app_label_should_return_404_when_no_logs(self):
        """按应用标识查询无记录时应返回 404"""
        response = self.client.get("/api/v1/audit-logs/by-app/nonexistent/")
        self.assertEqual(response.status_code, 404)


class AuditLogsByOperatorViewTest(TestCase):
    """AuditLogsByOperatorView API 测试"""

    def setUp(self):
        """创建测试用审计日志数据并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.log = AuditLog.objects.create(
            record_code="DEPT001",
            app_label="department",
            operation_type="create",
            description="创建部门: 技术部",
            operator_jobcode="E001",
            operator_name="张三",
            ip_address="192.168.1.100",
        )

    def test_by_operator_should_return_logs(self):
        """按操作人查询应返回结果"""
        response = self.client.get("/api/v1/audit-logs/by-operator/E001/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["count"], 1)

    def test_by_operator_should_return_404_when_no_logs(self):
        """按操作人查询无记录时应返回 404"""
        response = self.client.get("/api/v1/audit-logs/by-operator/NONEXIST/")
        self.assertEqual(response.status_code, 404)
