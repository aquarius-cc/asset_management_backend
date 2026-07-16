"""
仓库管理模型
"""

from typing import TYPE_CHECKING

from django.db import models

from apps.usermanagement.models import Employee
from core.models import BaseModel


if TYPE_CHECKING:
    from django.db.models import Manager


class Storage(BaseModel):
    """
    仓库管理模型

    用于管理资产的存储仓库，包括新货仓库、回收仓库、待报废仓库等类型。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "STORAGE"

    class StorageType(models.TextChoices):
        """仓库类型"""
        NEW_ASSET = "newasset", "新货仓库"
        RECYCLE = "recycle", "回收仓库"
        BROKEN = "broken", "损坏存放出库"
        DAMAGED = "damaged", "待报废仓库"

    # 向后兼容
    STORAGE_TYPE_CHOICES = StorageType.choices

    storage_code = models.CharField(max_length=30, verbose_name="仓库编码", help_text="仓库唯一编码，用于业务关联")
    storage_name = models.CharField(max_length=100, verbose_name="仓库名称", help_text="仓库名称，用户可见的展示名称")
    storage_address = models.CharField(max_length=200, verbose_name="仓库地址", help_text="仓库的物理地址")
    storage_type = models.CharField(
        max_length=50,
        choices=STORAGE_TYPE_CHOICES,
        default=StorageType.NEW_ASSET,
        verbose_name="仓库类型",
        blank=True,
        null=True,
        help_text="仓库类型：新货/回收/损坏存放出库/待报废",
    )
    storage_description = models.TextField(
        verbose_name="仓库描述", blank=True, null=True, help_text="仓库的补充说明信息"
    )
    storage_location = models.CharField(
        max_length=200, verbose_name="仓库位置", blank=True, null=True, help_text="仓库的详细位置描述"
    )
    storage_manager = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="managed_storages",
        verbose_name="仓库管理员",
        blank=True,
        null=True,
        help_text="仓库管理员（通过 recordcode 关联）",
    )
    storage_capacity = models.IntegerField(
        verbose_name="仓库容量", blank=True, null=True, help_text="仓库的最大存储容量"
    )
    sort_order = models.IntegerField(default=0, verbose_name="排序号", help_text="排序号，数值越小越靠前")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    class Meta:
        verbose_name = "仓库管理"
        verbose_name_plural = "仓库管理"
        db_table = "am_storage"
        constraints = [
            models.UniqueConstraint(
                fields=["storage_code"],
                condition=models.Q(is_deleted=False),
                name="unique_storage_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["storage_name"],
                condition=models.Q(is_deleted=False),
                name="unique_storage_name_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["storage_code"]),
            models.Index(fields=["storage_type"]),
            models.Index(fields=["storage_manager"]),
        ]

    def __str__(self) -> str:
        return f"{self.storage_name}({self.storage_code})"
