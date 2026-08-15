"""
认证服务测试
"""

import pytest

from apps.authusermanagement.services import AuthService
from core.exceptions import AppValidationError


ValidationError = AppValidationError  # 测试中统一使用 AppValidationError


@pytest.mark.django_db
class TestAuthService:
    """认证服务测试"""

    def test_register_user(self):
        """测试注册用户"""
        user_data = {
            "auth_username": "newuser",
            "password": "newpass123",
            "auth_jobcode": "AU002",
            "auth_name": "新用户",
        }

        user = AuthService.register_user(user_data)

        assert user.auth_username == "newuser"
        assert user.check_password("newpass123")

    def test_register_duplicate_username(self, auth_user):
        """测试重复用户名"""

        user_data = {"auth_username": "testuser", "password": "anotherpass", "auth_jobcode": "AU003"}

        with pytest.raises(ValidationError):
            AuthService.register_user(user_data)

    def test_authenticate_user(self, auth_user):
        """测试用户认证"""
        user = AuthService.authenticate_user("testuser", "testpass123")

        assert user is not None
        assert user.auth_username == "testuser"

    def test_authenticate_invalid_password(self, auth_user):
        """测试错误密码认证"""
        user = AuthService.authenticate_user("testuser", "wrongpass")

        assert user is None
