"""
认证后端

提供自定义用户认证逻辑，支持使用用户名、邮箱或手机号登录
"""

from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpRequest

from apps.authusermanagement.models import AuthUser


class AuthUserBackend(ModelBackend):
    """
    自定义认证后端

    支持使用用户名、邮箱或手机号进行登录认证
    """

    def authenticate(
        self, request: HttpRequest | None, username: str | None = None, password: str | None = None, **kwargs: Any
    ) -> AuthUser | None:
        """
        用户认证

        Args:
            request: HTTP请求对象
            username: 用户名、邮箱或手机号
            password: 用户密码

        Returns:
            认证成功返回用户对象，失败返回None
        """
        if not username or not password:
            return None

        try:
            # 【软删除兼容】认证时只查询激活用户，避免 MultipleObjectsReturned
            # 原因：auth_username 改为条件唯一后，可能存在同名禁用用户
            query_condition = (
                Q(auth_username=username, auth_is_active=True)
                | Q(email=username, auth_is_active=True)
                | Q(auth_phone=username, auth_is_active=True)
            )
            user = AuthUser.objects.get(query_condition)
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except ObjectDoesNotExist:
            return None
        except MultipleObjectsReturned:
            return None

        return None
