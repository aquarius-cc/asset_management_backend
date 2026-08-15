"""
已遗失资产管理模型
"""

from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class LostAssetQuerySet(models.QuerySet):
    """
    LostAsset 查询集优化
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            "asset_recordcode",
            "operator_employee",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
        )

    def for_list(self):
        """遗失列表页专用"""
        return self.select_related(
            "asset_recordcode",
            "operator_employee",
        )


class LostAsset(BaseModel):
    """
    已遗失资产管理模型

    记录资产遗失信息,直接生效无需审批。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "LOST"

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="lost_assets",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="遗失资产编码",
        help_text="关联的资产唯一标识码",
    )
    lost_date = models.DateField(verbose_name="遗失日期", default=timezone.now, help_text="资产标记为遗失的日期")
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="lost_assets_operator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人",
        help_text="标记资产遗失的操作人",
    )
    last_known_location = models.CharField(
        max_length=200, verbose_name="最后已知位置", blank=True, null=True, help_text="资产最后已知的位置"
    )
    lost_reason = models.CharField(max_length=100, verbose_name="遗失原因", help_text="资产遗失的原因")
    lost_description = models.TextField(verbose_name="遗失描述", blank=True, null=True, help_text="遗失的详细描述")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(LostAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "已遗失资产管理"
        verbose_name_plural = "已遗失资产管理"
        db_table = "am_lost_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["lost_date"]),
        ]

    def __str__(self) -> str:
        return f"遗失-{self.recordcode}-{self.asset_recordcode.asset_name if self.asset_recordcode else '未知'}"
