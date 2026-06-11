"""
用户管理数据库模型
"""
from django.db import models
from django.core.exceptions import ValidationError as DjangoValidationError
from typing import TYPE_CHECKING, Optional

from core.models import generate_recordcode

if TYPE_CHECKING:
    from django.db.models import Manager


# 部门层级最大限制（level 0-5，共 6 层）
MAX_DEPARTMENT_LEVEL = 5


# 兼容旧代码的模型别名 - 使用 proxy 模式
# class Departmentdatabasetable(Department):
#     """部门管理表（兼容旧代码）"""
#     class Meta:
#         proxy = True
#         verbose_name = "部门管理(兼容)"
#         verbose_name_plural = "部门管理(兼容)"


class Department(models.Model):
    """
    部门管理表

    支持树形层级结构，最大层级限制为 6 层。

    【字段说明】
    - department_code: 部门唯一编码
    - department_name: 部门名称
    - parent_code: 上级部门编码，null 表示根部门
    - level: 部门层级，0=根部门，1=一级部门...
    - sort_order: 排序顺序，数字越小越靠前

    【约束】
    - 层级最大限制 6 层
    - 不允许循环引用（A->B->A）
    - 移动部门时需验证层级约束
    """

    if TYPE_CHECKING:
        objects: "Manager"

    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 is_deleted=False 时唯一
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    department_code = models.CharField(
        max_length=20, verbose_name="部门编码",
        help_text="部门唯一标识编码"
    )
    department_name = models.CharField(
        max_length=100, verbose_name="部门名称",
        help_text="部门显示名称"
    )
    department_information = models.CharField(
        max_length=20, verbose_name="部门信息员",
        help_text="部门信息负责人"
    )
    # 【新增】上级部门编码，支持树形结构
    parent_code = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name="上级部门编码",
        help_text="上级部门编码，null 表示根部门"
    )
    # 【新增】部门层级，0=根部门
    level = models.IntegerField(
        default=0,
        verbose_name="部门层级",
        help_text="部门层级：0=根部门，1=一级部门，最大 6 层"
    )
    # 【AGENTS规范】添加排序字段，支持前端自定义显示顺序
    sort_order = models.IntegerField(
        default=0, verbose_name="排序顺序",
        help_text="数字越小排序越靠前，用于控制前端显示顺序"
    )
    # 【软删除兼容-新增 is_deleted】Department 不继承 BaseModel，需手动添加软删除字段
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='是否删除',
        help_text='软删除标记'
    )

    class Meta:
        verbose_name = "部门管理"
        verbose_name_plural = "部门管理"
        db_table = 'department_database_table'
        ordering = ['sort_order', 'department_code']
        # 【软删除兼容-条件唯一约束】仅未删除记录的业务编码唯一
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
            models.Index(fields=['parent_code'], name='idx_department_parent'),
            models.Index(fields=['level'], name='idx_department_level'),
        ]

    def save(self, *args, **kwargs):
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.department_name)

    def clean(self) -> None:
        """
        模型验证：检查层级约束和循环引用

        Raises:
            DjangoValidationError: 层级超过限制或存在循环引用
        """
        super().clean()

        # 验证层级不超过最大限制
        if self.level > MAX_DEPARTMENT_LEVEL:
            raise DjangoValidationError({
                'level': f'部门层级不能超过 {MAX_DEPARTMENT_LEVEL} 层'
            })

        # 验证层级不为负数
        if self.level < 0:
            raise DjangoValidationError({
                'level': '部门层级不能为负数'
            })

        # 验证 parent_code 存在性
        if self.parent_code:
            # 不能将自己设为自己的父部门
            if self.parent_code == self.department_code:
                raise DjangoValidationError({
                    'parent_code': '不能将自己设为上级部门'
                })

            # 检查父部门是否存在
            if not Department.objects.filter(
                department_code=self.parent_code
            ).exists():
                raise DjangoValidationError({
                    'parent_code': f'上级部门 {self.parent_code} 不存在'
                })

    def get_children(self) -> models.QuerySet:
        """
        获取当前部门的所有直接子部门

        Returns:
            QuerySet: 子部门查询集
        """
        return Department.objects.filter(parent_code=self.department_code)

    def get_employee_count(self) -> int:
        """
        获取当前部门的员工数量（仅直接关联的员工）

        Returns:
            int: 员工数量
        """
        return Employee.objects.filter(
            employee_department=self
        ).count()

    def get_all_descendants(self) -> list:
        """
        获取当前部门的所有后代部门（递归）

        用于检查循环引用和层级计算。

        Returns:
            list: 所有后代部门的编码列表
        """
        descendants = []
        children = self.get_children()

        for child in children:
            descendants.append(child.department_code)
            descendants.extend(child.get_all_descendants())

        return descendants

    # 【软删除兼容-新增软删除方法】Department 不继承 BaseModel，需手动实现
    # 原因：支持 is_deleted 字段的软删除逻辑
    def delete(self, using=None, keep_parents=False):
        """软删除：将 is_deleted 设置为 True"""
        self.is_deleted = True
        self.save(using=using)

    def restore(self):
        """恢复软删除的记录"""
        self.is_deleted = False
        self.save()

    def hard_delete(self, using=None, keep_parents=False):
        """硬删除：真正从数据库删除记录"""
        super().delete(using=using, keep_parents=keep_parents)


class Employee(models.Model):
    """员工管理表"""
    EMPLOYEE_STATUS_CHOICES = [
        ('active', '在职员工'),
        ('left', '离职员工'),
        ('retirement', '退休员工')
    ]

    if TYPE_CHECKING:
        objects: "Manager"

    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 is_deleted=False 时唯一
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    employee_jobcode = models.CharField(
        max_length=20, verbose_name="员工工号")
    employee_name = models.CharField(
        max_length=100, verbose_name="员工名称")
    employee_status = models.CharField(
        max_length=10,
        choices=EMPLOYEE_STATUS_CHOICES,
        default='active',
        verbose_name="员工状态"
    )
    employee_department = models.ForeignKey(
        Department,
        to_field='recordcode',
        on_delete=models.SET_DEFAULT,
        null=True,
        blank=True,
        default='Error',
        verbose_name="所属部门",
        help_text="所属部门（通过 recordcode 关联）"
    )
    employee_phone = models.CharField(
        max_length=15, verbose_name="员工电话")
    employee_location = models.CharField(max_length=100, verbose_name="员工位置")
    employee_description = models.TextField(
        blank=True, null=True, verbose_name="员工描述")
    # 【AGENTS规范】添加排序字段，支持前端自定义显示顺序
    sort_order = models.IntegerField(
        default=0, verbose_name="排序顺序",
        help_text="数字越小排序越靠前，用于控制前端显示顺序"
    )
    # 【软删除兼容-新增 is_deleted】Employee 不继承 BaseModel，需手动添加软删除字段
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='是否删除',
        help_text='软删除标记'
    )

    class Meta:
        verbose_name = "员工管理"
        verbose_name_plural = "员工管理"
        db_table = 'user_database_table'
        # 【软删除兼容-条件唯一约束】仅未删除记录的业务编码唯一
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
        ]
        indexes = [
            models.Index(fields=['employee_jobcode']),
            models.Index(fields=['employee_name']),
            models.Index(fields=['sort_order']),  # 【AGENTS规范】排序字段索引
        ]
        ordering = ['sort_order', 'employee_jobcode']  # 按排序字段优先排序

    def save(self, *args, **kwargs):
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.employee_name)

    # 【软删除兼容-新增软删除方法】Employee 不继承 BaseModel，需手动实现
    # 原因：支持 is_deleted 字段的软删除逻辑
    def delete(self, using=None, keep_parents=False):
        """软删除：将 is_deleted 设置为 True"""
        self.is_deleted = True
        self.save(using=using)

    def restore(self):
        """恢复软删除的记录"""
        self.is_deleted = False
        self.save()

    def hard_delete(self, using=None, keep_parents=False):
        """硬删除：真正从数据库删除记录"""
        super().delete(using=using, keep_parents=keep_parents)


# class Userdatabasetable(Employee):
#     """
#     员工管理表（兼容旧代码）

#     此模型为兼容旧代码而保留，新代码应使用 Employee 模型。
#     继承自 Employee 以保持数据兼容性。

#     提供旧字段名的属性别名以保持向后兼容：
#     - user_jobcode -> employee_jobcode
#     - user_name -> employee_name
#     """

#     # 为旧字段名提供属性别名
#     @property
#     def user_jobcode(self):
#         return self.employee_jobcode

#     @user_jobcode.setter
#     def user_jobcode(self, value):
#         self.employee_jobcode = value

#     @property
#     def user_name(self):
#         return self.employee_name

#     @user_name.setter
#     def user_name(self, value):
#         self.employee_name = value

#     class Meta:
#         verbose_name = "员工管理(兼容)"
#         verbose_name_plural = "员工管理(兼容)"
#         proxy = True
