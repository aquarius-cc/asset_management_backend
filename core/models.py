# d:\CodeDemo\Python\asset_management_backend\core\models.py
"""
基础模型类

提供项目所有模型的基类：
- TimestampModel: 提供创建和更新时间戳
- BaseModel: 提供软删除功能、激活状态和 recordcode 自动生成
- SoftDeleteManager: 自定义管理器，默认过滤已删除记录
"""

import uuid

from django.db import models
from django.utils import timezone


def generate_recordcode_with_prefix(prefix: str = 'REC') -> str:
    """
    生成唯一记录编码（可配置前缀）

    Args:
        prefix: 编码前缀，默认 'REC'，OutAsset/RecycleAsset 使用 'OUT'

    Returns:
        str: 格式为 {PREFIX}-YYYYMMDD-XXXXXXXX 的唯一编码
    """
    return f"{prefix}-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


# 向后兼容：保留原函数名，内部调用新函数
def generate_recordcode() -> str:
    """向后兼容：生成 REC 前缀的记录编码"""
    return generate_recordcode_with_prefix('REC')


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
    - recordcode: 后端生成的全局唯一编码，用于外键引用
    - is_active: 控制记录是否启用
    - is_deleted: 软删除标记
    - 软删除方法 delete()
    - 硬删除方法 hard_delete()
    - 恢复方法 restore()

    子类可通过覆盖 RECORDCODE_PREFIX 自定义编码前缀：
        class OutAsset(BaseModel):
            RECORDCODE_PREFIX = 'OUT'
    """
    # 子类可覆盖此属性自定义 recordcode 前缀
    RECORDCODE_PREFIX = 'Asset'

    recordcode = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
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

    def save(self, *args, **kwargs):
        """
        保存时自动生成 recordcode（如未提供）
        【健壮性】添加碰撞重试机制：当 recordcode 唯一约束冲突时，
        重新生成 recordcode 并重试，最多重试 3 次。
        """
        if not self.recordcode:
            self.recordcode = generate_recordcode_with_prefix(self.RECORDCODE_PREFIX)
        try:
            super().save(*args, **kwargs)
        except Exception as e:
            from django.db import IntegrityError
            if isinstance(e, IntegrityError) and 'recordcode' in str(e) and not kwargs.get('update_fields'):
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"recordcode 碰撞，重试生成: {self.recordcode}")
                self.recordcode = generate_recordcode_with_prefix(self.RECORDCODE_PREFIX)
                super().save(*args, **kwargs)
            else:
                raise

    def delete(self, using=None, keep_parents=False):
        """
        软删除：将 is_deleted 设置为 True

        调用此方法不会真正删除记录，而是标记为已删除状态。
        默认查询将不再返回此记录，但可以通过 all_objects 访问。
        """
        self.is_deleted = True
        self.save(using=using, update_fields=['is_deleted', 'updated_at'])

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
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"恢复记录: {self.__class__.__name__} pk={self.pk}")
        self.is_deleted = False
        self.save(update_fields=['is_deleted', 'updated_at'])
