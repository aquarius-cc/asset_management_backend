# d:\CodeDemo\Python\asset_management_backend\core\models.py
"""
基础模型类

提供项目所有模型的基类：
- TimestampModel: 提供创建和更新时间戳
- BaseModel: 提供软删除功能和激活状态
- SoftDeleteManager: 自定义管理器，默认过滤已删除记录
"""

import uuid
from datetime import datetime
from typing import Any

from django.db import models
from django.utils import timezone


def generate_recordcode() -> str:
    """
    【软删除兼容-新增 recordcode】生成唯一记录编码

    原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    原业务编码改为条件唯一：仅 is_deleted=False 时唯一

    Returns:
        str: 格式为 REC-YYYYMMDD-XXXXXXXX 的唯一编码
    """
    return f"REC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


class SoftDeleteManager(models.Manager):
    """
    软删除管理器

    默认查询不包含已软删除的记录，通过 `all_objects` 可以查询所有记录。

    Example:
        class MyModel(BaseModel):
            objects = SoftDeleteManager()

        # 默认查询（排除已删除） 【关键】默认查询时自动排除 is_deleted=True 的数据
        MyModel.objects.all()

        # 查询所有记录（包含已删除）
        MyModel.all_objects.all()
    """

    def get_queryset(self):
        """返回不包含已软删除记录的查询集"""
        return super().get_queryset().filter(is_deleted=False)


class TimestampModel(models.Model):
    """
    抽象基类，提供创建和更新时间戳

    所有需要记录创建和修改时间的模型都应继承此类。
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
        help_text='最后修改时间'
    )

    class Meta:
        abstract = True


class BaseModel(TimestampModel):
    """
    基础模型类，包含所有模型通用的字段和方法

    提供：
    - is_active: 控制记录是否启用
    - is_deleted: 软删除标记
    - 软删除方法 delete()
    - 硬删除方法 hard_delete()
    - 恢复方法 restore()
    """
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='控制记录是否激活'
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='是否删除',
        help_text='软删除标记'
    )

    # 默认管理器（过滤已删除记录）
    objects = SoftDeleteManager()
    # 完整管理器（包含所有记录）
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        软删除：将 is_deleted 设置为 True

        调用此方法不会真正删除记录，而是标记为已删除状态。
        默认查询将不再返回此记录，但可以通过 all_objects 访问。
        """
        self.is_deleted = True
        self.save(using=using)

    def hard_delete(self, using=None, keep_parents=False):
        """
        硬删除：真正从数据库删除记录

        调用此方法会永久删除记录，谨慎使用。
        """
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """
        恢复软删除的记录

        将 is_deleted 设置为 False，使记录重新出现在默认查询中。
        """
        self.is_deleted = False
        self.save()
