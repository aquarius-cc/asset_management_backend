"""
出库资产管理模型
"""

import uuid
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class OutAssetQuerySet(models.QuerySet):
    """
    OutAsset 查询集优化
    """

    def with_asset_details(self):
        """预加载资产完整信息"""
        return self.select_related(
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_applicant_recordcode",
            "asset_recordcode__asset_manager_recordcode",
        )

    def for_list(self):
        """出库列表页专用"""
        return self.with_asset_details().defer(
            "outasset_description",
        )


def generate_outassetrecordcode() -> str:
    """生成唯一出库记录编码"""
    prefix = "OUT"
    date_str = timezone.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"{prefix}-{date_str}-{unique_id}"


class OutAsset(BaseModel):
    """
    出库资产管理模型

    记录资产的领用和借用信息,包含申请人、保管人、使用地点等信息。
    资产出库后状态自动变为"在用"。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    class OutassetType(models.TextChoices):
        """出库类型"""

        RECEIVE = "receive", "领用"
        BORROW = "borrow", "借用"
        REISSUE = "reissue", "重新发放"

    class OutassetPreviousStatus(models.TextChoices):
        IN_STORE = "in_store", "在库"
        RECYCLED_PENDING = "recycled_pending", "已回收待发放"

    # 向后兼容
    OUTASSET_TYPE_CHOICES = OutassetType.choices
    OUTASSET_STATUS_CHOICES = OutassetPreviousStatus.choices

    RECORDCODE_PREFIX = "OUTASSET"

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        related_name="out_assets",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="出库资产的资产唯一标识码",
        help_text="关联的资产唯一标识码(通过 recordcode 关联)",
    )
    outasset_number = models.IntegerField(verbose_name="出库数量", default=1, help_text="出库的资产数量")
    outasset_previous_status = models.CharField(
        max_length=20,
        choices=OutassetPreviousStatus.choices,
        default=OutassetPreviousStatus.IN_STORE,
        null=True,
        blank=True,
        verbose_name="出库前资产状态",
        help_text="记录出库前资产的状态,用于取消出库时恢复。历史数据可能为空。",
    )
    return_date = models.DateField(
        verbose_name="归还日期", blank=True, null=True, help_text="借用资产的预计或实际归还日期"
    )
    outasset_date = models.DateField(verbose_name="出库日期", default=timezone.now, help_text="资产出库的日期")
    outasset_type = models.CharField(
        max_length=50,
        choices=OutassetType.choices,
        default=OutassetType.RECEIVE,
        verbose_name="出库类型",
        blank=True,
        null=True,
        help_text="出库类型:领用/借用",
    )
    outasset_description = models.TextField(
        verbose_name="出库资产描述", blank=True, null=True, help_text="出库的补充说明"
    )
    outasset_applicant_recordcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="out_assets_applicant",
        verbose_name="出库申请人",
        help_text="出库时的申请人(FK 关联)",
    )
    outasset_manager_recordcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="out_assets_manager",
        verbose_name="出库保管人",
        help_text="出库时的保管人(FK 关联)",
    )
    outasset_using_location = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="出库使用地点", help_text="出库时的使用地点"
    )
    outasset_snapshot = models.JSONField(
        blank=True, null=True, verbose_name="出库快照", help_text="保存出库时的申请人、保管人等关键信息(用于历史追溯)"
    )
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(OutAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "出库资产管理"
        verbose_name_plural = "出库资产管理"
        db_table = "am_out_asset"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["outasset_date"]),
        ]

    def __str__(self) -> str:
        asset_name = self.asset_recordcode.asset_name if self.asset_recordcode else "未关联"
        return f"出库{self.recordcode}-{asset_name}"
