"""
资产找回记录模型
"""

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.models.lost_asset import LostAsset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


class FoundAssetQuerySet(models.QuerySet["FoundAsset"]):
    """
    FoundAsset 查询集优化
    """

    def with_asset_details(self) -> "FoundAssetQuerySet":
        """预加载资产完整信息"""
        return self.select_related(
            "lost_asset_recordcode",
            "asset_recordcode",
            "operator_employee",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
        )

    def for_list(self) -> "FoundAssetQuerySet":
        """找回列表页专用"""
        return self.select_related(
            "lost_asset_recordcode",
            "asset_recordcode",
            "operator_employee",
        )


class FoundAsset(BaseModel):
    """
    资产找回记录模型

    记录遗失资产找回信息,关联LostAsset。
    """

    RECORDCODE_PREFIX = "FOUND"

    lost_asset_recordcode = models.OneToOneField(
        LostAsset,
        to_field="recordcode",
        related_name="found_record",
        on_delete=models.PROTECT,
        verbose_name="关联的遗失记录",
        help_text="关联的遗失资产记录",
    )
    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="found_assets",
        on_delete=models.PROTECT,
        verbose_name="找回资产编码",
        help_text="找回的资产唯一标识码",
    )
    found_date = models.DateField(verbose_name="找回日期", default=timezone.now, help_text="资产找回的日期")
    found_location = models.CharField(
        max_length=200, verbose_name="找回地点", blank=True, null=True, help_text="资产找回的地点"
    )
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="found_assets_operator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人",
        help_text="执行找回操作的操作人",
    )
    found_description = models.TextField(verbose_name="找回描述", blank=True, null=True, help_text="找回的详细描述")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(FoundAssetQuerySet)()  # type: ignore[misc]
    all_objects = models.Manager()  # type: ignore[misc]

    class Meta:
        verbose_name = "资产找回记录"
        verbose_name_plural = "资产找回记录"
        db_table = "am_found_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["lost_asset_recordcode"]),
            models.Index(fields=["found_date"]),
        ]

    def __str__(self) -> str:
        return f"找回-{self.recordcode}-{self.asset_recordcode.asset_name if self.asset_recordcode else '未知'}"
