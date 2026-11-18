# d:\CodeDemo\Python\asset_management_backend\apps\authusermanagement\tests\conftest.py
"""
认证管理测试配置

MA-23 包 1c：造数改走 factory_boy 工厂（`tests/factories.py`），
**fixture 签名与返回值不变**。
"""

import pytest
from rest_framework.test import APIClient

from apps.authusermanagement.tests.factories import AuthUserFactory
from core.tests import TEST_PASSWORD


@pytest.fixture
def api_client():
    """API 测试客户端"""
    return APIClient()


@pytest.fixture
def auth_user(db):
    """认证测试用户"""
    return AuthUserFactory.create(
        auth_username="testuser", password=TEST_PASSWORD, auth_phone="13800138000"
    )
