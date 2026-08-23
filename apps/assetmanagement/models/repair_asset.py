from django.db import models

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


class RepairAssetQuerySet(models.QuerySet["RepairAsset"]):
    """维修记录查询集优化"""

    def with_asset_details(self) -> "RepairAssetQuerySet":
        return self.select_related(
            "asset_recordcode",
            "operator_employee",
        )

    def for_list(self) -> "RepairAssetQuerySet":
        return self.with_asset_details()


class RepairAsset(BaseModel):
    RECORDCODE_PREFIX = "REPAIR"

    class RepairStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "维修中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "维修失败"

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        on_delete=models.PROTECT,
        related_name="repair_assets",
        null=True,
        blank=True,
        verbose_name="维修资产",
        help_text="关联的资产唯一标识码",
    )
    repair_date = models.DateField(verbose_name="送修日期", help_text="资产送修日期")
    expected_return_date = models.DateField(
        null=True, blank=True, verbose_name="预计完成日期", help_text="预计维修完成日期"
    )
    actual_return_date = models.DateField(
        null=True, blank=True, verbose_name="实际完成日期", help_text="实际维修完成日期"
    )
    repair_status = models.CharField(
        max_length=20,
        choices=RepairStatus.choices,
        default=RepairStatus.IN_PROGRESS,
        verbose_name="维修状态",
        help_text="维修状态:维修中/已完成/维修失败",
    )
    repair_reason = models.CharField(max_length=100, verbose_name="维修原因", help_text="资产维修的原因")
    repair_description = models.TextField(null=True, blank=True, verbose_name="维修描述", help_text="维修的详细描述")
    repair_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="维修费用", help_text="维修产生的费用(元)"
    )
    physical_grade_before = models.CharField(
        max_length=20,
        choices=Asset.PhysicalGrade.choices,
        null=True,
        blank=True,
        verbose_name="维修前成色",
        help_text="维修前的物理成色",
    )
    physical_grade_after = models.CharField(
        max_length=20,
        choices=Asset.PhysicalGrade.choices,
        null=True,
        blank=True,
        verbose_name="维修后成色",
        help_text="维修后的物理成色",
    )
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="repair_assets_operator",
        null=True,
        blank=True,
        verbose_name="维修操作人",
        help_text="执行维修操作的人员",
    )
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(RepairAssetQuerySet)()  # type: ignore[misc]
    all_objects = models.Manager()  # type: ignore[misc]

    class Meta:
        verbose_name = "维修记录"
        verbose_name_plural = verbose_name
        db_table = "am_repair_asset"
        constraints = [
            models.UniqueConstraint(
                fields=["asset_recordcode"],
                condition=models.Q(repair_status="in_progress"),
                name="uniq_active_repair_per_asset",
            ),
        ]
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["repair_status"]),
        ]

    def __str__(self) -> str:
        return f"维修记录-{self.asset_recordcode}"
