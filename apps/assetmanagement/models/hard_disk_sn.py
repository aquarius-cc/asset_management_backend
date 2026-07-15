"""
硬盘序列号管理模型
"""

from typing import TYPE_CHECKING

from django.db import models

from apps.assetmanagement.models.asset import Asset
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class HardDiskSN(BaseModel):
    """
    硬盘序列号管理模型

    管理硬盘类资产的序列号信息，支持跟踪硬盘状态变化。
    关系：Asset (1) → (0..N) HardDiskSN
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "HDSN"

    HARDDISK_TYPE_CHOICES = [
        ("HDD", "HDD"),
        ("SSD", "SSD"),
        ("NVMe", "NVMe"),
        ("Other", "其他"),
    ]

    HARDDISK_STATUS_CHOICES = [
        ("active", "正常"),
        ("repair", "维修"),
        ("scrap", "报废"),
        ("lost", "丢失"),
        ("damaged", "损坏"),
    ]

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="harddisk_sns",
        on_delete=models.PROTECT,
        verbose_name="关联资产",
        help_text="关联的资产唯一标识码（通过 recordcode 关联）",
    )
    harddisk_sn_code = models.CharField(
        max_length=100, verbose_name="硬盘序列号", help_text="硬盘的唯一序列号"
    )
    harddisk_type = models.CharField(
        max_length=20,
        choices=HARDDISK_TYPE_CHOICES,
        default="HDD",
        blank=True,
        verbose_name="硬盘类型",
        help_text="硬盘类型：HDD/SSD/NVMe/Other",
    )
    harddisk_capacity = models.CharField(
        max_length=20,
        default="",
        blank=True,
        verbose_name="硬盘容量",
        help_text="硬盘容量标识，如 500GB/1TB/2TB",
    )
    harddisk_status = models.CharField(
        max_length=20,
        choices=HARDDISK_STATUS_CHOICES,
        default="active",
        verbose_name="硬盘状态",
        help_text="硬盘状态：正常/维修/报废/丢失/损坏",
    )
    harddisk_description = models.TextField(
        blank=True, default="", verbose_name="硬盘描述", help_text="硬盘的补充说明"
    )
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "硬盘序列号管理"
        verbose_name_plural = "硬盘序列号管理"
        db_table = "am_hard_disk_sn"
        constraints = [
            models.UniqueConstraint(
                fields=["harddisk_sn_code"],
                condition=models.Q(is_deleted=False),
                name="unique_harddisk_sn_code_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["harddisk_status"]),
            models.Index(fields=["harddisk_type"]),
        ]

    def __str__(self) -> str:
        asset_name = self.asset_recordcode.asset_name if self.asset_recordcode else "未知"
        return f"硬盘SN-{self.harddisk_sn_code} ({asset_name})"
