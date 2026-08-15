"""
AssetOperationLog logging_id 功能测试

测试范围:
1. logging_id 自动生成
2. logging_id 格式正确性
3. logging_id 唯一性约束
4. 服务层根据 logging_id 查询
5. API 接口根据 logging_id 查询
"""

import re

import pytest
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.assetmanagement.models import AssetOperationLog
from apps.assetmanagement.services.operation_log_service import OperationLogQueryService


@pytest.mark.django_db
class TestLoggingIdGeneration:
    """logging_id 自动生成测试"""

    def test_logging_id_auto_generated_on_create(self):
        """创建记录时应自动生成 logging_id"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试日志")
        assert log.logging_id is not None
        assert len(log.logging_id) > 0

    def test_logging_id_starts_with_operation_type(self):
        """logging_id 应以 operation_type 开头"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="out", description="测试出库")
        assert log.logging_id.startswith("out-Log-")

    def test_logging_id_contains_date(self):
        """logging_id 应包含操作日期(YYYYMMDD 格式)"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试日期")
        date_str = log.operation_time.strftime("%Y%m%d")
        assert date_str in log.logging_id

    def test_logging_id_has_random_suffix(self):
        """logging_id 应包含8位随机字符后缀"""
        log = AssetOperationLog.objects.create(
            asset_code="TEST001", operation_type="create", description="测试随机字符"
        )
        # 格式: {operation_type}-Log-{YYYYMMDD}-{8位随机字符}
        suffix = log.logging_id.split("-")[-1]
        assert len(suffix) == 8
        assert re.match(r"^[A-Z0-9]+$", suffix)


@pytest.mark.django_db
class TestLoggingIdFormat:
    """logging_id 格式正确性测试"""

    def test_create_format(self):
        """create 操作的 logging_id 格式"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试格式")
        pattern = r"^create-Log-\d{8}-[A-Z0-9]{8}$"
        assert re.match(pattern, log.logging_id)

    def test_out_format(self):
        """out 操作的 logging_id 格式"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="out", description="测试格式")
        pattern = r"^out-Log-\d{8}-[A-Z0-9]{8}$"
        assert re.match(pattern, log.logging_id)

    def test_recycle_format(self):
        """recycle 操作的 logging_id 格式"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="recycle", description="测试格式")
        pattern = r"^recycle-Log-\d{8}-[A-Z0-9]{8}$"
        assert re.match(pattern, log.logging_id)

    def test_total_length(self):
        """logging_id 总长度应在合理范围内"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试长度")
        # create(6) + -Log-(5) + YYYYMMDD(8) + -(1) + random(8) = 28
        assert len(log.logging_id) == 28


@pytest.mark.django_db
class TestLoggingIdUniqueness:
    """logging_id 唯一性测试"""

    def test_duplicate_logging_id_raises_error(self):
        """重复的 logging_id 应抛出 IntegrityError"""
        log1 = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试1")

        with pytest.raises(IntegrityError):
            AssetOperationLog.objects.create(
                asset_code="TEST002",
                operation_type="create",
                description="测试2",
                logging_id=log1.logging_id,  # 手动设置重复值
            )

    def test_two_records_have_different_logging_ids(self):
        """两条记录应生成不同的 logging_id"""
        log1 = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试1")
        log2 = AssetOperationLog.objects.create(asset_code="TEST002", operation_type="create", description="测试2")
        assert log1.logging_id != log2.logging_id


@pytest.mark.django_db
class TestGetByLoggingIdService:
    """服务层根据 logging_id 查询测试"""

    def test_existing_logging_id(self):
        """查询存在的 logging_id 应返回记录"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试")
        result = OperationLogQueryService.get_operation_log_by_logging_id(log.logging_id)
        assert result is not None
        assert result.id == log.id

    def test_nonexistent_logging_id(self):
        """查询不存在的 logging_id 应返回 None"""
        result = OperationLogQueryService.get_operation_log_by_logging_id("nonexistent-Log-20250123-A1B2C3D4")
        assert result is None


@pytest.mark.django_db
class TestGetByLoggingIdAPI:
    """API 接口根据 logging_id 查询测试"""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        """创建测试用户并强制认证"""
        from apps.authusermanagement.models import AuthUser

        self.user = AuthUser.objects.create_user(auth_username="testuser", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_api_returns_record(self):
        """API 应返回匹配的记录"""
        log = AssetOperationLog.objects.create(asset_code="TEST001", operation_type="create", description="测试")
        url = f"/api/assets/operation-logs/by-logging-id/{log.logging_id}/"
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["code"] == 0
        assert response.data["data"]["logging_id"] == log.logging_id

    def test_api_returns_404_for_nonexistent(self):
        """API 对不存在的 logging_id 应返回 404"""
        url = "/api/assets/operation-logs/by-logging-id/nonexistent-Log-20250123-A1B2C3D4/"
        response = self.client.get(url)

        assert response.status_code == 404
        assert response.data["code"] == 404
