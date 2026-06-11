# d:\CodeDemo\Python\asset_management_backend\apps\authusermanagement\tests\conftest.py
"""
认证管理测试配置
"""

import pytest
from rest_framework.test import APIClient
from authusermanagement.models import AuthUser


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def auth_user(db):
    """认证测试用户"""
    return AuthUser.objects.create_user(
        username='testuser',
        password='testpass123',
        auth_jobcode='AU001',
        auth_name='测试用户'
    )
