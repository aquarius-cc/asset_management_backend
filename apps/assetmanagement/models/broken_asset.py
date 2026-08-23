"""
已损坏资产管理模型
"""

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


class BrokenAssetQuerySet(models.QuerySet["BrokenAsset"]):
    """
    BrokenAsset 查询集优化
    """

    def with_asset_details(self) -> "BrokenAssetQuerySet":
        """预加载资产完整信息"""
        return self.select_related(
            "asset_recordcode",
            "operator_employee",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
        )

    def for_list(self) -> "BrokenAssetQuerySet":
        """损坏列表页专用"""
        return self.select_related(
            "asset_recordcode",
            "operator_employee",
        )


class BrokenAsset(BaseModel):
    """
    已损坏资产管理模型

    记录资产损坏信息,直接生效无需审批。
    """

    RECORDCODE_PREFIX = "BROKEN"

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="broken_assets",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="损坏资产编码",
        help_text="关联的资产唯一标识码",
    )
    broken_date = models.DateField(verbose_name="损坏日期", default=timezone.now, help_text="资产标记为损坏的日期")
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="broken_assets_operator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人",
        help_text="标记资产损坏的操作人",
    )
    broken_reason = models.CharField(max_length=100, verbose_name="损坏原因", help_text="资产损坏的原因")
    broken_description = models.TextField(verbose_name="损坏描述", blank=True, null=True, help_text="损坏的详细描述")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(BrokenAssetQuerySet)()  # type: ignore[misc]
    all_objects = models.Manager()  # type: ignore[misc]

    class Meta:
        verbose_name = "已损坏资产管理"
        verbose_name_plural = "已损坏资产管理"
        db_table = "am_broken_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["broken_date"]),
        ]

    def __str__(self) -> str:
        return f"损坏-{self.recordcode}-{self.asset_recordcode.asset_name if self.asset_recordcode else '未知'}"
