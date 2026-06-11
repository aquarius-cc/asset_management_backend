"""
认证与用户管理数据库模型

该模块定义用户认证与管理相关的数据模型，
继承Django的AbstractBaseUser和PermissionsMixin以支持完整的认证功能。

包含以下核心模型：
- AuthUser: 自定义用户模型
- AuthUserManager: 自定义用户管理器
"""

from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from typing import TYPE_CHECKING, Optional, Any

from core.models import generate_recordcode

if TYPE_CHECKING:
    from django.db.models import Manager


class AuthUserManager(BaseUserManager):
    """
    自定义用户管理器

    负责用户的创建和管理，包括普通用户和超级用户的创建。
    支持通过用户名不区分大小写进行查询。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    def get_by_natural_key(self, username: str) -> "AuthUser":
        """
        通过自然键（用户名）获取用户，不区分大小写

        Args:
            username: 用户名

        Returns:
            AuthUser: 用户实例
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})

    def create_user(
        self,
        auth_username: str,
        password: Optional[str] = None,
        **extra_fields: Any
    ) -> "AuthUser":
        """
        创建并保存一个普通用户

        Args:
            auth_username: 用户名
            password: 密码
            **extra_fields: 额外的用户字段

        Returns:
            AuthUser: 创建的用户实例

        Raises:
            ValueError: 当用户名为空时
        """
        if not auth_username:
            raise ValueError("用户名不能为空")

        user = self.model(auth_username=auth_username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        auth_username: str,
        password: Optional[str] = None,
        **extra_fields: Any
    ) -> "AuthUser":
        """
        创建并保存一个超级用户

        Args:
            auth_username: 用户名
            password: 密码
            **extra_fields: 额外的用户字段

        Returns:
            AuthUser: 创建的超级用户实例

        Raises:
            ValueError: 当auth_is_staff不为True时
        """
        extra_fields.setdefault("auth_is_staff", True)
        extra_fields.setdefault("auth_is_active", True)
        extra_fields.setdefault("is_superuser", True)   # ← 添加这一行, 确保超级用户有所有权限

        if extra_fields.get("auth_is_staff") is not True:
            raise ValueError("超级用户必须设置 auth_is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("超级用户必须设置 is_superuser=True")

        return self.create_user(auth_username, password, **extra_fields)


class AuthUser(AbstractBaseUser, PermissionsMixin):
    """
    认证与用户管理模型

    自定义用户模型，继承AbstractBaseUser和PermissionsMixin，
    支持完整的Django认证系统功能。
    """

    if TYPE_CHECKING:
        objects: "Manager[AuthUser]"

    auth_id = models.AutoField(
        primary_key=True,
        verbose_name="用户ID",
        help_text="用户唯一标识"
    )
    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 auth_is_active=True 时唯一（AuthUser 使用 auth_is_active 作为有效状态标记）
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    auth_username = models.CharField(
        max_length=150,
        verbose_name="用户名",
        help_text="用户登录名，唯一标识"
    )
    email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
        verbose_name="电子邮件",
        help_text="用户邮箱地址"
    )
    auth_is_active = models.BooleanField(
        default=True,
        verbose_name="是否激活",
        help_text="用户账户是否激活"
    )
    auth_is_staff = models.BooleanField(
        default=False,
        verbose_name="是否为员工",
        help_text="是否为后台管理员"
    )
    auth_date_create = models.DateTimeField(
        auto_now_add=True,
        verbose_name="创建日期",
        help_text="用户创建时间"
    )
    auth_date_update = models.DateTimeField(
        auto_now=True,
        verbose_name="更新日期",
        help_text="用户信息更新时间"
    )
    auth_phone = models.CharField(
        max_length=15,
        verbose_name="联系电话",
        help_text="用户联系电话"
    )
    last_login = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="上次登录时间",
        help_text="用户最后一次登录时间"
    )
    # 【AGENTS规范】添加排序字段，支持前端自定义显示顺序
    # sort_order = models.IntegerField(
    #     default=0,
    #     verbose_name="排序顺序",
    #     help_text="数字越小排序越靠前，用于控制前端显示顺序"
    # )

    REQUIRED_FIELDS = ["email"]
    USERNAME_FIELD = "auth_username"

    objects = AuthUserManager()

    class Meta:
        verbose_name = "认证与用户管理"
        verbose_name_plural = "认证与用户管理"
        db_table = "auth_user_management_table"
        app_label = "authusermanagement"
        # 【软删除兼容-条件唯一约束】仅激活状态记录的业务字段唯一（AuthUser 使用 auth_is_active 作为有效状态标记）
        constraints = [
            models.UniqueConstraint(
                fields=["auth_username"],
                condition=models.Q(auth_is_active=True),
                name="unique_auth_username_active",
            ),
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(auth_is_active=True),
                name="unique_auth_email_active",
            ),
            models.UniqueConstraint(
                fields=["auth_phone"],
                condition=models.Q(auth_is_active=True),
                name="unique_auth_phone_active",
            ),
        ]
        indexes = [
            models.Index(fields=["auth_username"]),
            models.Index(fields=["email"]),
            models.Index(fields=["auth_phone"]),
            # models.Index(fields=["sort_order"]),  # 【AGENTS规范】排序字段索引
        ]
        ordering = [ 'auth_username']  # 按排序字段优先排序

    def __str__(self) -> str:
        """返回用户名字符串表示"""
        return str(self.auth_username)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        保存用户实例

        Args:
            *args: 位置参数
            **kwargs: 关键字参数
        """
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        # 【软删除兼容】将空字符串 email 转为 null，避免 UniqueConstraint 冲突
        # 原因：多个激活用户的 email="" 会触发唯一约束冲突，null 值不受唯一约束限制
        if self.email == "":
            self.email = None
        if self.password and not str(self.password).startswith("pbkdf2_sha256$"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    @property
    def is_authenticated(self) -> bool:
        """Django认证系统需要的is_authenticated属性"""
        return True

    def get_username(self) -> str:
        """获取用户名"""
        return self.auth_username

    @property
    def is_staff(self) -> bool:
        """Django认证系统需要的is_staff属性"""
        return self.auth_is_staff

    @property
    def is_active(self) -> bool:
        """Django认证系统需要的is_active属性"""
        return self.auth_is_active

    def hard_delete(self, using=None, keep_parents=False):
        """硬删除：真正从数据库删除记录"""
        super().delete(using=using, keep_parents=keep_parents)

    def set_password(self, raw_password: Optional[str]) -> None:
        """
        设置密码（哈希后存储）

        Args:
            raw_password: 原始密码
        """
        if raw_password:
            self.password = make_password(raw_password)

    def check_password(self, raw_password: Optional[str]) -> bool:
        """
        检查密码是否正确

        Args:
            raw_password: 原始密码

        Returns:
            bool: 密码是否正确
        """
        if not raw_password or not self.password:
            return False
        return check_password(raw_password, self.password)
