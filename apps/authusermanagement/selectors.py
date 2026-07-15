"""
认证管理查询层

提供用户数据的查询方法
"""

from django.db.models import QuerySet

from apps.authusermanagement.models import AuthUser


class AuthUserSelector:
    """
    认证用户查询选择器

    提供用户数据的查询方法
    """

    @staticmethod
    def get_user_by_username(auth_username: str) -> AuthUser | None:
        """
        通过用户名获取激活用户

        【软删除兼容】只查询 auth_is_active=True 的用户
        原因：auth_username 改为条件唯一后，可能存在同名禁用用户

        Args:
            auth_username: 用户名

        Returns:
            Optional[AuthUser]: 用户实例或None
        """
        try:
            return AuthUser.objects.get(auth_username=auth_username, auth_is_active=True)
        except AuthUser.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_id(auth_id: int) -> AuthUser | None:
        """
        通过用户ID获取用户

        Args:
            auth_id: 用户ID

        Returns:
            Optional[AuthUser]: 用户实例或None
        """
        try:
            return AuthUser.objects.get(auth_id=auth_id)
        except AuthUser.DoesNotExist:
            return None

    @staticmethod
    def list_active_users() -> QuerySet[AuthUser]:
        """
        获取所有激活用户

        Returns:
            QuerySet[AuthUser]: 激活用户查询集
        """
        return AuthUser.objects.filter(auth_is_active=True)

    @staticmethod
    def list_all_users() -> QuerySet[AuthUser]:
        """
        获取所有用户

        Returns:
            QuerySet[AuthUser]: 所有用户查询集
        """
        return AuthUser.objects.all()

    @staticmethod
    def get_user_by_email(email: str) -> AuthUser | None:
        """
        通过邮箱获取激活用户

        【软删除兼容】只查询 auth_is_active=True 的用户
        原因：email 改为条件唯一后，可能存在相同邮箱的禁用用户

        Args:
            email: 邮箱地址

        Returns:
            Optional[AuthUser]: 用户实例或None
        """
        try:
            return AuthUser.objects.get(email=email, auth_is_active=True)
        except AuthUser.DoesNotExist:
            return None

    # 【AGENTS 规范 - P2-02】以下 exists 方法供 AuthService.register_user 使用，
    # 避免 Service 层直接调用 AuthUser.objects.filter(...).exists()

    @staticmethod
    def exists_by_username(auth_username: str) -> bool:
        """
        检查用户名是否已被激活用户使用

        【AGENTS 规范 - P2-02】供 AuthService.register_user 使用
        【软删除兼容】只检查 auth_is_active=True 的用户
        原因：禁用的用户名可以重新注册

        Args:
            auth_username: 用户名

        Returns:
            bool: 用户名是否已被激活用户使用
        """
        return AuthUser.objects.filter(auth_username=auth_username, auth_is_active=True).exists()

    @staticmethod
    def exists_by_email(email: str) -> bool:
        """
        检查邮箱是否已被激活用户使用

        【AGENTS 规范 - P2-02】供 AuthService.register_user 使用
        【软删除兼容】只检查 auth_is_active=True 的用户
        原因：禁用的邮箱可以重新注册

        Args:
            email: 邮箱地址

        Returns:
            bool: 邮箱是否已被激活用户使用
        """
        return AuthUser.objects.filter(email=email, auth_is_active=True).exists()

    @staticmethod
    def exists_by_phone(auth_phone: str) -> bool:
        """
        检查手机号是否已被激活用户使用

        【AGENTS 规范 - P2-02】供 AuthService.register_user 使用
        【软删除兼容】只检查 auth_is_active=True 的用户
        原因：禁用的手机号可以重新注册

        Args:
            auth_phone: 手机号

        Returns:
            bool: 手机号是否已被激活用户使用
        """
        return AuthUser.objects.filter(auth_phone=auth_phone, auth_is_active=True).exists()
