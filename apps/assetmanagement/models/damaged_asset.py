"""
待报废资产管理模型
"""

from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class DamagedAssetQuerySet(models.QuerySet):
    """
    DamagedAsset 查询集优化
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "approver",
        )

    def for_list(self):
        """待报废列表页专用"""
        return self.with_asset_details().defer(
            "damaged_asset_description",
        )


class DamagedAsset(BaseModel):
    """
    待报废资产管理模型

    记录待报废的资产信息，包含审批流程状态，审批通过后进入报废流程。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "DAMAGED"

    asset_recordcode = models.OneToOneField(
        Asset,
        to_field="recordcode",
        verbose_name="待报废资产的资产唯一标识码",
        related_name="damaged_assets",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="待报废的资产唯一标识码（通过 recordcode 关联）",
    )
    damaged_asset_number = models.IntegerField(verbose_name="待报废数量", default=1, help_text="待报废的资产数量")
    damaged_date = models.DateField(
        verbose_name="待报废日期", default=timezone.now, blank=True, null=True, help_text="提交报废申请的日期"
    )
    approval_status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "待审批"),
            ("approved", "已批准"),
            ("rejected", "已拒绝"),
        ],
        verbose_name="报废审批状态",
        help_text="审批状态：待审批/已批准/已拒绝",
    )
    approver = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="damaged_assets_approver",
        on_delete=models.SET_NULL,
        verbose_name="审批人",
        null=True,
        blank=True,
        help_text="审批人的工号（通过 recordcode 关联）",
    )
    damaged_asset_description = models.TextField(
        verbose_name="待报废资产描述", blank=True, null=True, help_text="报废原因等说明"
    )
    original_status = models.CharField(
        max_length=20,
        verbose_name="原状态",
        blank=True,
        null=True,
        help_text="进入damaged前的资产状态，用于reject时回退",
    )
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(DamagedAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "待报废资产管理"
        verbose_name_plural = "待报废资产管理"
        db_table = "am_damaged_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["approval_status"]),
        ]

    def __str__(self) -> str:
        asset_name = self.asset_recordcode.asset_name if self.asset_recordcode else "未关联"
        return f"待报废{asset_name}"
