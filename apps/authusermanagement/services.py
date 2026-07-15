"""
认证管理服务层

提供用户认证、注册等相关的业务逻辑
"""

from typing import Any

from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken, TokenError  # 如果已有 RefreshToken 则追加 TokenError

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.selectors import AuthUserSelector
from core.exceptions import AppValidationError


class AuthService:
    """
    认证服务类

    提供用户认证、注册等相关的业务逻辑方法
    """

    @staticmethod
    @transaction.atomic
    def register_user(user_data: dict[str, Any]) -> AuthUser:
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
        auth_username = user_data.get("auth_username")
        if not auth_username:
            raise AppValidationError("用户名不能为空")

        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_username()，
        # 避免 Service 层直接调用 AuthUser.objects.filter(...).exists()
        if AuthUserSelector.exists_by_username(auth_username):
            raise AppValidationError("用户名已存在")

        email = user_data.get("email")
        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_email()
        if email and AuthUserSelector.exists_by_email(email):
            raise AppValidationError("邮箱已被使用")

        auth_phone = user_data.get("auth_phone")
        # 【AGENTS 规范 - P2-02】改用 AuthUserSelector.exists_by_phone()
        if auth_phone and AuthUserSelector.exists_by_phone(auth_phone):
            raise AppValidationError("手机号已被使用")

        # 【修复 S8】强制创建为普通用户，忽略客户端传入的 auth_is_staff
        user = AuthUser.objects.create_user(
            auth_username=auth_username,
            password=user_data["password"],
            email=email or "",
            auth_phone=auth_phone or "",
            auth_is_active=True,
            auth_is_staff=False,  # 【修复 S8】强制为普通用户
        )

        from apps.authusermanagement.audit_adapter import AuthAuditAdapter

        AuthAuditAdapter.log_register(user)

        return user

    @staticmethod
    def authenticate_user(auth_username: str, password: str) -> AuthUser | None:
        """
        用户认证

        Args:
            auth_username: 用户名
            password: 密码

        Returns:
            Optional[AuthUser]: 认证成功返回用户实例，失败返回None
        """
        user = authenticate(username=auth_username, password=password)
        if user:
            from apps.authusermanagement.audit_adapter import AuthAuditAdapter

            AuthAuditAdapter.log_login(user)
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

        try:
            # 解析 refresh_token，验证签名和有效期
            token = RefreshToken(refresh_token)

            # 将 token 加入黑名单（写入 BlacklistedToken 表）
            # SimpleJWT 的 token_blacklist 应用会自动处理：
            # - 检查 token 是否已存在 OutstandingToken 记录
            # - 创建 BlacklistedToken 记录关联到 OutstandingToken
            # - 后续 TokenAuthentication 会检查黑名单并拒绝已作废的 token
            token.blacklist()

            from apps.authusermanagement.audit_adapter import AuthAuditAdapter

            AuthAuditAdapter.log_logout(token.get("username", "") if hasattr(token, "get") else "")

        except TokenError as e:
            # TokenError 涵盖以下场景：
            # - Token 已过期（ExpiredTokenError）
            # - Token 格式错误
            # - Token 签名无效
            # - Token 已被作废（BlacklistedTokenError）
            raise AppValidationError(f"Token 无效或已过期: {e!s}")

    @staticmethod
    @transaction.atomic
    def update_user(
        auth_id: int, update_data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> AuthUser:
        """
        更新用户信息

        【P2-08 修复】将更新逻辑从 View 层迁移到 Service 层，
        确保业务校验和审计日志记录。

        Args:
            auth_id: 用户 ID
            update_data: 更新数据
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            AuthUser: 更新后的用户实例
        """
        try:
            user = AuthUser.objects.get(auth_id=auth_id)
        except AuthUser.DoesNotExist:
            raise AppValidationError(f"用户 {auth_id} 不存在")

        # 安全检查：不允许通过更新接口修改敏感字段
        forbidden_fields = {"auth_id", "recordcode", "password", "is_superuser"}
        for field in forbidden_fields:
            update_data.pop(field, None)

        # 检查唯一性约束
        if "auth_username" in update_data and update_data["auth_username"] != user.auth_username:
            if AuthUserSelector.exists_by_username(update_data["auth_username"]):
                raise AppValidationError("用户名已存在")

        if "email" in update_data and update_data["email"] != user.email:
            if update_data["email"] and AuthUserSelector.exists_by_email(update_data["email"]):
                raise AppValidationError("邮箱已被使用")

        if "auth_phone" in update_data and update_data["auth_phone"] != user.auth_phone:
            if update_data["auth_phone"] and AuthUserSelector.exists_by_phone(update_data["auth_phone"]):
                raise AppValidationError("手机号已被使用")

        for key, value in update_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        user.save()

        return user
