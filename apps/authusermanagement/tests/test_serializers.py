"""
用户个人信息更新序列化器测试(BE-02)

覆盖:
- old_password 必填与原密码校验(CT-1 / T3)
- 空密码/空白/None 在字段校验层被拒(终结 P1 误报, 断言 allow_blank=False 行为)
- update() 改密设置新哈希并吊销 refresh token; 仅改联系字段不触发吊销(CT-4 回归护栏)
"""

from unittest import mock

import pytest

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.serializers import UserProfileUpdateSerializer
from apps.authusermanagement.services import AuthService
from core.tests import TEST_PASSWORD


NEW_PASSWORD = "NewPass123!"


@pytest.mark.django_db
class TestUserProfileUpdateSerializer:
    """个人信息更新序列化器(old_password 校验与改密吊销)"""

    def test_password_without_old_password_rejected(self, auth_user):
        """修改密码但未提供原密码时应被拒绝"""
        serializer = UserProfileUpdateSerializer(auth_user, data={"password": NEW_PASSWORD}, partial=True)
        assert not serializer.is_valid()
        assert "old_password" in serializer.errors
        assert "修改密码时必须提供原密码" in str(serializer.errors["old_password"])

    def test_wrong_old_password_rejected(self, auth_user):
        """原密码错误时应被拒绝"""
        serializer = UserProfileUpdateSerializer(
            auth_user, data={"password": NEW_PASSWORD, "old_password": "wrong-old-pass"}, partial=True
        )
        assert not serializer.is_valid()
        assert "old_password" in serializer.errors
        assert "原密码错误" in str(serializer.errors["old_password"])

    def test_correct_old_password_passes_and_drops_old_password(self, auth_user):
        """原密码正确时通过, 且 old_password 不进入 validated_data"""
        serializer = UserProfileUpdateSerializer(
            auth_user, data={"password": NEW_PASSWORD, "old_password": TEST_PASSWORD}, partial=True
        )
        assert serializer.is_valid()
        assert "old_password" not in serializer.validated_data
        assert serializer.validated_data["password"] == NEW_PASSWORD

    @pytest.mark.parametrize("blank", ["", "  ", None])
    def test_blank_password_rejected_at_field(self, auth_user, blank):
        """空串/纯空白/None 应在字段校验层被拒, 不会进入 validate()"""
        serializer = UserProfileUpdateSerializer(auth_user, data={"password": blank}, partial=True)
        assert not serializer.is_valid()
        assert "password" in serializer.errors

    def test_update_password_sets_hash_and_invalidates_tokens(self, auth_user):
        """改密成功后应写入新哈希并吊销该用户全部 refresh token"""
        with mock.patch.object(AuthService, "invalidate_user_refresh_tokens") as mock_invalidate:
            serializer = UserProfileUpdateSerializer(
                auth_user, data={"password": NEW_PASSWORD, "old_password": TEST_PASSWORD}, partial=True
            )
            assert serializer.is_valid()
            serializer.save()
        mock_invalidate.assert_called_once_with(auth_user)
        updated = AuthUser.objects.get(auth_id=auth_user.auth_id)
        assert updated.check_password(NEW_PASSWORD)

    def test_update_contact_only_skips_token_invalidation(self, auth_user):
        """仅更新联系字段时不应触发 refresh token 吊销(防止修复引入新副作用)"""
        with mock.patch.object(AuthService, "invalidate_user_refresh_tokens") as mock_invalidate:
            serializer = UserProfileUpdateSerializer(auth_user, data={"email": "new@example.com"}, partial=True)
            assert serializer.is_valid()
            serializer.save()
        mock_invalidate.assert_not_called()
