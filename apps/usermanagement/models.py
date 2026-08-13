"""
用户管理数据库模型
"""

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models

from core.models import BaseModel


if TYPE_CHECKING:
    from django.db.models import Manager


# 部门层级最大限制(level 0-5,共 6 层)
MAX_DEPARTMENT_LEVEL = 5


class Department(BaseModel):
    """
    部门管理表

    支持树形层级结构,最大层级限制为 6 层。

    树形关联设计(方案 D):
    - parent: ForeignKey(self) — 指向父级 recordcode,保证引用完整性
    - path: CharField — 物化路径,如 /DEPT-001/IT-001/DEV-001,加速子孙查询

    继承 BaseModel 获得:recordcode、is_active、is_deleted、
    created_at、updated_at、SoftDeleteManager、delete/restore/hard_delete。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "DEPARTMENT"

    department_code = models.CharField(max_length=20, verbose_name="部门编码", help_text="部门唯一标识编码")
    department_name = models.CharField(max_length=100, verbose_name="部门名称", help_text="部门显示名称")
    department_information = models.CharField(max_length=20, verbose_name="部门信息员", help_text="部门信息负责人")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        to_field="recordcode",
        verbose_name="上级部门",
        help_text="上级部门(FK 指向 recordcode),null 表示根部门",
    )
    path = models.CharField(
        max_length=500,
        default="",
        blank=True,
        verbose_name="物化路径",
        help_text="从根到当前节点的完整路径,如 /DEPT-001/IT-001/DEV-001",
    )
    level = models.IntegerField(default=0, verbose_name="部门层级", help_text="部门层级:0=根部门,1=一级部门,最大 6 层")
    sort_order = models.IntegerField(
        default=0, verbose_name="排序顺序", help_text="数字越小排序越靠前,用于控制前端显示顺序"
    )

    class Meta:
        verbose_name = "部门管理"
        verbose_name_plural = "部门管理"
        db_table = "am_department"
        ordering = ["sort_order", "department_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["department_code"],
                condition=models.Q(is_deleted=False),
                name="unique_department_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["department_name"],
                condition=models.Q(is_deleted=False),
                name="unique_department_name_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["parent"], name="idx_department_parent_fk"),
            models.Index(fields=["path"], name="idx_department_path"),
            models.Index(fields=["level"], name="idx_department_level"),
        ]

    def __str__(self) -> str:
        return str(self.department_name)

    def save(self, *args, **kwargs):
        """保存时清除自身及所有祖先的后代缓存"""
        from django.core.cache import cache

        # 清除自身缓存
        cache.delete(f"dept:{self.recordcode}:descendants")
        # 清除所有祖先的缓存(因为后代列表可能变化)
        if self.path:
            parts = self.path.strip("/").split("/")
            for i in range(1, len(parts)):
                ancestor_path = "/".join(parts[:i])
                try:
                    ancestor = Department.objects.get(path=ancestor_path)
                    cache.delete(f"dept:{ancestor.recordcode}:descendants")
                except Department.DoesNotExist:
                    pass
        super().save(*args, **kwargs)

    def clean(self) -> None:
        """
        模型验证:检查层级约束和循环引用
        """
        super().clean()

        if self.level > MAX_DEPARTMENT_LEVEL:
            raise DjangoValidationError({"level": f"部门层级不能超过 {MAX_DEPARTMENT_LEVEL} 层"})

        if self.level < 0:
            raise DjangoValidationError({"level": "部门层级不能为负数"})

        if self.parent:
            if self.parent_id == self.pk:
                raise DjangoValidationError({"parent": "不能将自己设为上级部门"})
            if not Department.objects.filter(pk=self.parent_id).exists():
                raise DjangoValidationError({"parent": "上级部门不存在"})

    def get_children(self) -> models.QuerySet:
        """获取当前部门的所有直接子部门"""
        return Department.objects.filter(parent=self)

    def get_employee_count(self) -> int:
        """获取当前部门的员工数量(仅未删除的员工)"""
        return Employee.objects.filter(employee_department=self).count()

    def get_all_descendants(self) -> list:
        """获取当前部门的所有后代部门(基于 path 查询,带缓存)"""
        if not self.path:
            return []
        from django.core.cache import cache

        cache_key = f"dept:{self.recordcode}:descendants"
        result = cache.get(cache_key)
        if result is not None:
            return result
        result = list(
            Department.objects.filter(path__startswith=f"{self.path}/").values_list("department_code", flat=True)
        )
        cache.set(cache_key, result, timeout=300)  # 5 分钟缓存
        return result


class EmployeeRole(models.TextChoices):
    """系统角色枚举(RBAC 权限矩阵)"""

    SYSTEM_ADMIN = "system_admin", "系统管理员"
    DEPT_MANAGER = "dept_manager", "部门经理"
    ASSET_ADMIN = "asset_admin", "资产管理员"
    REGULAR_USER = "regular_user", "普通用户"
    AUDITOR = "auditor", "审计员"


class Employee(BaseModel):
    """
    员工管理表

    继承 BaseModel 获得:recordcode、is_active、is_deleted、
    created_at、updated_at、SoftDeleteManager、delete/restore/hard_delete。
    """

    EMPLOYEE_STATUS_CHOICES = [("active", "在职员工"), ("left", "离职员工"), ("retirement", "退休员工")]

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "EMPLOYEE"

    employee_jobcode = models.CharField(max_length=20, verbose_name="员工工号")
    employee_name = models.CharField(max_length=100, verbose_name="员工名称")
    role = models.CharField(
        max_length=20,
        choices=EmployeeRole.choices,
        default=EmployeeRole.REGULAR_USER,
        verbose_name="系统角色",
        help_text="RBAC 角色:system_admin/dept_manager/asset_admin/regular_user/auditor",
    )
    employee_status = models.CharField(
        max_length=10, choices=EMPLOYEE_STATUS_CHOICES, default="active", verbose_name="员工状态"
    )
    employee_department = models.ForeignKey(
        Department,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="所属部门",
        help_text="所属部门(通过 recordcode 关联)",
    )
    employee_phone = models.CharField(max_length=15, verbose_name="员工电话")
    employee_location = models.CharField(max_length=100, verbose_name="员工位置")
    employee_description = models.TextField(blank=True, null=True, verbose_name="员工描述")
    auth_user = models.OneToOneField(
        "authusermanagement.AuthUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
        verbose_name="绑定的认证账号",
        help_text="绑定的认证账号 FK,null 表示未绑定。绑定请通过 EmployeeService.bind_auth_user(),禁止直接写库",
    )
    sort_order = models.IntegerField(
        default=0, verbose_name="排序顺序", help_text="数字越小排序越靠前,用于控制前端显示顺序"
    )

    class Meta:
        verbose_name = "员工管理"
        verbose_name_plural = "员工管理"
        db_table = "am_employee"
        constraints = [
            models.UniqueConstraint(
                fields=["employee_jobcode"],
                condition=models.Q(is_deleted=False),
                name="unique_employee_jobcode_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["employee_phone"],
                condition=models.Q(is_deleted=False),
                name="unique_employee_phone_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["auth_user"],
                condition=models.Q(is_deleted=False),
                name="unique_employee_auth_user_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["employee_jobcode"]),
            models.Index(fields=["employee_name"]),
            models.Index(fields=["sort_order"]),
            models.Index(fields=["employee_department"], name="idx_employee_department"),
        ]
        ordering = ["sort_order", "employee_jobcode"]

    def __str__(self) -> str:
        return str(self.employee_name)

    def save(self, *args, **kwargs):
        """保存时检测角色变更,若角色改变则黑名单当前 JWT Token"""
        # 检测角色是否变更
        if self.pk:
            try:
                old = Employee.objects.get(pk=self.pk)
                role_changed = old.role != self.role
            except Employee.DoesNotExist:
                role_changed = False
        else:
            role_changed = False

        super().save(*args, **kwargs)

        # 角色变更后,黑名单该用户的所有 Refresh Token
        if role_changed:
            self._blacklist_user_tokens()

    def _blacklist_user_tokens(self):
        """黑名单该用户的所有 Refresh Token,强制重新登录"""
        try:
            from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

            # 找到该用户的所有未过期 Refresh Token 并加入黑名单
            outstanding = OutstandingToken.objects.filter(
                user__auth_username=self.employee_jobcode,
            )
            blacklisted_count = 0
            for token in outstanding:
                _, created = BlacklistedToken.objects.get_or_create(token=token)
                if created:
                    blacklisted_count += 1

            if blacklisted_count > 0:
                import logging

                logger = logging.getLogger(__name__)
                logger.info(
                    f"角色变更:已黑名单 {blacklisted_count} 个 Token (employee_jobcode={self.employee_jobcode})"
                )
        except Exception:
            # Token 黑名单操作失败不影响业务
            pass


class Role(BaseModel):
    """角色表(RBAC)"""

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "ROLE"

    role_code = models.CharField(max_length=50, verbose_name="角色编码", help_text="唯一标识,如 system_admin")
    role_name = models.CharField(max_length=100, verbose_name="角色名称", help_text="显示名称,如 系统管理员")
    role_level = models.IntegerField(default=0, verbose_name="层级值", help_text="层级值:5/4/3/2/1,用于兼容旧权限判断")
    description = models.CharField(max_length=500, blank=True, verbose_name="角色描述")
    is_system = models.BooleanField(default=False, verbose_name="系统内置", help_text="系统内置角色不可删除")
    sort_order = models.IntegerField(default=0, verbose_name="排序顺序")

    class Meta:
        verbose_name = "角色管理"
        verbose_name_plural = "角色管理"
        db_table = "am_role"
        ordering = ["-role_level", "sort_order", "role_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["role_code"],
                condition=models.Q(is_deleted=False),
                name="unique_role_code_not_deleted",
            ),
        ]

    def __str__(self) -> str:
        return str(self.role_name)


class Permission(BaseModel):
    """权限点表(RBAC)"""

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "PERMISSION"

    permission_code = models.CharField(
        max_length=100, verbose_name="权限编码", help_text="格式:module:action,如 asset:create"
    )
    module = models.CharField(max_length=50, verbose_name="模块", help_text="所属模块,如 asset、outasset")
    action = models.CharField(max_length=50, verbose_name="操作", help_text="操作类型,如 read、create、update、delete")
    description = models.CharField(max_length=200, blank=True, verbose_name="权限描述")

    class Meta:
        verbose_name = "权限点管理"
        verbose_name_plural = "权限点管理"
        db_table = "am_permission"
        ordering = ["module", "action"]
        constraints = [
            models.UniqueConstraint(
                fields=["permission_code"],
                condition=models.Q(is_deleted=False),
                name="unique_permission_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["module", "action"],
                condition=models.Q(is_deleted=False),
                name="unique_module_action_not_deleted",
            ),
        ]

    def __str__(self) -> str:
        return str(self.permission_code)


class RolePermission(BaseModel):
    """角色-权限关联表(RBAC)"""

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "ROLEPERMISSION"

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
        verbose_name="角色",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
        verbose_name="权限点",
    )

    class Meta:
        verbose_name = "角色权限关联"
        verbose_name_plural = "角色权限关联"
        db_table = "am_role_permission"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="unique_role_permission"),
        ]


class UserRole(BaseModel):
    """用户-角色关联表(RBAC)"""

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "USERROLE"

    data_scope = models.JSONField(
        blank=True,
        default=dict,
        help_text='JSON 格式:{"scope_type": "all"} 或 {"scope_type": "department", "department_code": "IT-001", "include_children": true}',
        verbose_name="数据范围",
    )
    auth_user = models.ForeignKey(
        "authusermanagement.AuthUser",
        on_delete=models.CASCADE,
        related_name="user_roles",
        verbose_name="系统账号",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="user_roles",
        verbose_name="角色",
    )

    class Meta:
        verbose_name = "用户角色关联"
        verbose_name_plural = "用户角色关联"
        db_table = "am_user_role"
        constraints = [
            models.UniqueConstraint(fields=["auth_user", "role"], name="unique_user_role"),
        ]
        indexes = [
            models.Index(fields=["auth_user"], name="idx_ur_auth_user"),
            models.Index(fields=["role"], name="idx_ur_role"),
        ]
