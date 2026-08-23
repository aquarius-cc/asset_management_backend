"""
硬盘序列号管理模型
"""

from django.db import models

from apps.assetmanagement.models.asset import Asset
from core.models import BaseModel, SoftDeleteManager


class HardDiskSN(BaseModel):
    """
    硬盘序列号管理模型

    管理硬盘类资产的序列号信息,支持跟踪硬盘状态变化。
    关系:Asset (1) → (0..N) HardDiskSN
    """

    RECORDCODE_PREFIX = "HDSN"

    class HarddiskType(models.TextChoices):
        HDD = "HDD", "HDD"
        SSD = "SSD", "SSD"
        NVME = "NVMe", "NVMe"
        OTHER = "Other", "其他"

    class HarddiskStatus(models.TextChoices):
        ACTIVE = "active", "正常"
        REPAIR = "repair", "维修"
        SCRAP = "scrap", "报废"
        LOST = "lost", "丢失"
        DAMAGED = "damaged", "损坏"

    # 向后兼容
    HARDDISK_TYPE_CHOICES = HarddiskType.choices
    HARDDISK_STATUS_CHOICES = HarddiskStatus.choices

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="harddisk_sns",
        on_delete=models.PROTECT,
        verbose_name="关联资产",
        help_text="关联的资产唯一标识码(通过 recordcode 关联)",
    )
    harddisk_sn_code = models.CharField(max_length=100, verbose_name="硬盘序列号", help_text="硬盘的唯一序列号")
    harddisk_type = models.CharField(
        max_length=20,
        choices=HarddiskType.choices,
        default=HarddiskType.HDD,
        blank=True,
        verbose_name="硬盘类型",
        help_text="硬盘类型:HDD/SSD/NVMe/Other",
    )
    harddisk_capacity = models.CharField(
        max_length=20,
        default="",
        blank=True,
        verbose_name="硬盘容量",
        help_text="硬盘容量标识,如 500GB/1TB/2TB",
    )
    harddisk_status = models.CharField(
        max_length=20,
        choices=HarddiskStatus.choices,
        default=HarddiskStatus.ACTIVE,
        verbose_name="硬盘状态",
        help_text="硬盘状态:正常/维修/报废/丢失/损坏",
    )
    harddisk_description = models.TextField(blank=True, default="", verbose_name="硬盘描述", help_text="硬盘的补充说明")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager()  # type: ignore[misc]
    all_objects = models.Manager()  # type: ignore[misc]

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
