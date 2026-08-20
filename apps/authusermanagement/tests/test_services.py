"""
认证服务测试
"""

import pytest
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.services import AuthService
from core.exceptions import AppValidationError
from core.tests import TEST_PASSWORD


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

    def test_register_empty_username(self):
        """测试空用户名"""
        with pytest.raises(ValidationError) as exc_info:
            AuthService.register_user({"password": "pass123", "auth_phone": "13710010001"})
        assert "用户名不能为空" in str(exc_info.value.detail)

    def test_register_duplicate_email(self, auth_user):
        """测试注册重复邮箱"""
        AuthUser.objects.create_user(
            auth_username="emailuser", password=TEST_PASSWORD, email="dup@example.com", auth_phone="13710010002"
        )

        with pytest.raises(ValidationError):
            AuthService.register_user(
                {
                    "auth_username": "uniqueuser",
                    "password": "pass123",
                    "email": "dup@example.com",
                    "auth_phone": "13710010003",
                }
            )

    def test_register_duplicate_phone(self, auth_user):
        """测试注册重复手机号"""
        AuthUser.objects.create_user(
            auth_username="phoneuser", password=TEST_PASSWORD, auth_phone="13710010004"
        )

        with pytest.raises(ValidationError):
            AuthService.register_user(
                {"auth_username": "uniquephone", "password": "pass123", "auth_phone": "13710010004"}
            )

    def test_authenticate_user(self, auth_user):
        """测试用户认证"""
        user = AuthService.authenticate_user("testuser", TEST_PASSWORD)

        assert user is not None
        assert user.auth_username == "testuser"

    def test_authenticate_invalid_password(self, auth_user):
        """测试错误密码认证"""
        user = AuthService.authenticate_user("testuser", "wrongpass")

        assert user is None

    def test_refresh_tokens_missing_user_id(self):
        """测试 refresh_token 缺失 user_id"""
        token = RefreshToken()

        with pytest.raises(TokenError):
            AuthService.refresh_tokens(str(token))

    def test_update_user_not_found(self):
        """测试更新不存在的用户"""
        with pytest.raises(ValidationError):
            AuthService.update_user(999999, {"auth_username": "nobody"})

    def test_update_user_duplicate_username(self, auth_user):
        """测试更新时用户名重复"""
        AuthUser.objects.create_user(auth_username="takenname", password=TEST_PASSWORD, auth_phone="13710010005")

        with pytest.raises(ValidationError) as exc_info:
            AuthService.update_user(
                auth_user.auth_id, {"auth_username": "takenname"}, operator_jobcode="U001", operator_name="操作员"
            )
        assert "用户名已存在" in str(exc_info.value.detail)

    def test_update_user_duplicate_email(self, auth_user):
        """测试更新时邮箱重复"""
        AuthUser.objects.create_user(
            auth_username="emailowner", password=TEST_PASSWORD, email="taken@example.com", auth_phone="13710010006"
        )

        with pytest.raises(ValidationError) as exc_info:
            AuthService.update_user(
                auth_user.auth_id, {"email": "taken@example.com"}, operator_jobcode="U001", operator_name="操作员"
            )
        assert "邮箱已被使用" in str(exc_info.value.detail)

    def test_update_user_duplicate_phone(self, auth_user):
        """测试更新时手机号重复"""
        AuthUser.objects.create_user(auth_username="phoneowner", password=TEST_PASSWORD, auth_phone="13710010007")

        with pytest.raises(ValidationError) as exc_info:
            AuthService.update_user(
                auth_user.auth_id, {"auth_phone": "13710010007"}, operator_jobcode="U001", operator_name="操作员"
            )
        assert "手机号已被使用" in str(exc_info.value.detail)

    def test_update_user_success(self, auth_user):
        """测试更新用户成功"""
        user = AuthService.update_user(
            auth_user.auth_id,
            {"auth_username": "renamed", "email": "new@example.com"},
            operator_jobcode="U001",
            operator_name="操作员",
        )

        assert user.auth_username == "renamed"
        assert user.email == "new@example.com"
