# d:\CodeDemo\Python\asset_management_backend\apps\authusermanagement\tests\conftest.py
"""
认证管理测试配置
"""

import pytest
from rest_framework.test import APIClient

from apps.authusermanagement.models import AuthUser
from core.tests import TEST_PASSWORD


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def auth_user(db):
    """认证测试用户"""
    return AuthUser.objects.create_user(auth_username="testuser", password=TEST_PASSWORD, auth_phone="13800138000")
