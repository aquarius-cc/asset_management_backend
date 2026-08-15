"""
已报废资产管理模型
"""

from typing import TYPE_CHECKING

from django.db import models

from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.models.damaged_asset import DamagedAsset
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class WasteAssetQuerySet(models.QuerySet):
    """
    WasteAsset 查询集优化
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "damaged_recordcode",
        )

    def for_list(self):
        """已报废列表页专用"""
        return self.with_asset_details().defer(
            "waste_asset_description",
        )


class WasteAsset(BaseModel):
    """
    已报废资产管理模型

    记录已完成报废的资产信息,报废后资产状态为"已报废"。
    当待报废资产(DamagedAsset)审批通过后,自动创建已报废记录。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "WASTE"

    asset_recordcode = models.OneToOneField(
        Asset,
        to_field="recordcode",
        verbose_name="已报废资产的资产唯一标识码",
        related_name="waste_asset",
        on_delete=models.PROTECT,
        help_text="已报废的资产唯一标识码(通过 recordcode 关联)",
    )
    damaged_recordcode = models.OneToOneField(
        DamagedAsset,
        to_field="recordcode",
        related_name="waste_asset_record",
        verbose_name="来源待报废记录的资产唯一标识码",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="关联的待报废记录的资产唯一标识码,用于追溯来源",
    )
    waste_asset_number = models.IntegerField(verbose_name="已报废数量", default=1, help_text="报废的资产数量")
    waste_asset_date = models.DateField(verbose_name="报废日期", help_text="完成报废的日期")
    waste_asset_description = models.TextField(
        verbose_name="报废资产描述", blank=True, null=True, help_text="报废的补充说明"
    )
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(WasteAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "已报废资产管理"
        verbose_name_plural = "已报废资产管理"
        db_table = "am_waste_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["damaged_recordcode"]),
        ]

    def __str__(self) -> str:
        return f"已报废{self.asset_recordcode.asset_name}"
