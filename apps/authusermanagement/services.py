"""
认证管理服务层

提供用户认证、注册等相关的业务逻辑
"""
from django.contrib.auth import authenticate
from django.db import transaction
from core.exceptions import AppValidationError
from typing import Optional, Dict, Any
from .models import AuthUser
from .selectors import AuthUserSelector
from rest_framework_simplejwt.tokens import RefreshToken, TokenError  # 如果已有 RefreshToken 则追加 TokenError


class AuthService:
    """
    认证服务类

    提供用户认证、注册等相关的业务逻辑方法
    """

    @staticmethod
    @transaction.atomic
    def register_user(user_data: Dict[str, Any]) -> AuthUser:
        """
        注册新用户

        【修复 S8】强制设置 auth_is_staff=False，忽略客户端传入的值

        Args:
            user_data: 用户数据字典，包含 auth_username, password, email, auth_phone 等字段

        Returns:
            AuthUser: 创建的用户实例

        Raises:
            AppValidationError: 数据验证失败时抛出
        """
        auth_username = user_data.get('auth_username')
        if not auth_username:
            raise AppValidationError("用户名不能为空")

        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_username()，
        # 避免 Service 层直接调用 AuthUser.objects.filter(...).exists()
        if AuthUserSelector.exists_by_username(auth_username):
            raise AppValidationError("用户名已存在")

        email = user_data.get('email')
        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_email()
        if email and AuthUserSelector.exists_by_email(email):
            raise AppValidationError("邮箱已被使用")

        auth_phone = user_data.get('auth_phone')
        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_phone()
        if auth_phone and AuthUserSelector.exists_by_phone(auth_phone):
            raise AppValidationError("手机号已被使用")

        # 【修复 S8】强制创建为普通用户，忽略客户端传入的 auth_is_staff
        user = AuthUser.objects.create_user(
            auth_username=auth_username,
            password=user_data['password'],
            email=email or '',
            auth_phone=auth_phone or '',
            auth_is_active=True,
            auth_is_staff=False,  # 【修复 S8】强制为普通用户
        )

        return user

    @staticmethod
    def authenticate_user(
        auth_username: str,
        password: str
    ) -> Optional[AuthUser]:
        """
        用户认证

        Args:
            auth_username: 用户名
            password: 密码

        Returns:
            Optional[AuthUser]: 认证成功返回用户实例，失败返回None
        """
        user = authenticate(username=auth_username, password=password)
        return user

    @staticmethod
    def logout_user(refresh_token: str) -> None:
        """
        用户退出登录 - 将 refresh_token 加入黑名单

        核心流程：
        1. 解析 refresh_token，获取 Token 对象
        2. 将 Token 的 jti（JWT ID）写入黑名单
        3. 后续该 Token 的所有验证请求都会被拒绝

        【安全机制】
        - 使用 SimpleJWT 的 BlacklistMixin 机制，通过 OutstandingToken + BlacklistedToken 模型实现
        - Token 被加入黑名单后，即使未过期也无法再用于刷新获取新的 access_token
        - 配合 ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION，形成双重保护：
          · 主动退出：refresh_token 立即作废
          · 被动轮换：每次 refresh 时旧 token 自动作废

        Args:
            refresh_token: 客户端提交的 refresh_token 字符串

        Raises:
            AppValidationError: 当 token 无效、已过期或已被作废时
        """
        from rest_framework_simplejwt.tokens import RefreshToken, TokenError

        try:
            # 解析 refresh_token，验证签名和有效期
            token = RefreshToken(refresh_token)

            # 将 token 加入黑名单（写入 BlacklistedToken 表）
            # SimpleJWT 的 token_blacklist 应用会自动处理：
            # - 检查 token 是否已存在 OutstandingToken 记录
            # - 创建 BlacklistedToken 记录关联到 OutstandingToken
            # - 后续 TokenAuthentication 会检查黑名单并拒绝已作废的 token
            token.blacklist()

        except TokenError as e:
            # TokenError 涵盖以下场景：
            # - Token 已过期（ExpiredTokenError）
            # - Token 格式错误
            # - Token 签名无效
            # - Token 已被作废（BlacklistedTokenError）
            raise AppValidationError(f"Token 无效或已过期: {str(e)}")
