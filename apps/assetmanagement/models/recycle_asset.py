"""
回收资产管理模型
"""

from django.db import models

from apps.assetmanagement.models.asset import Asset
from apps.assetmanagement.models.out_asset import OutAsset
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


class RecycleAssetQuerySet(models.QuerySet["RecycleAsset"]):
    """
    RecycleAsset 查询集优化
    """

    def with_asset_details(self) -> "RecycleAssetQuerySet":
        """预加载资产完整信息"""
        return self.select_related(
            "outasset_recordcode",
            "asset_recordcode",
            "asset_recordcode__asset_type_recordcode",
            "asset_recordcode__asset_contract_recordcode",
            "asset_recordcode__asset_storage_recordcode",
            "asset_recordcode__asset_manager_recordcode",
            "operator_employee",
        )

    def for_list(self) -> "RecycleAssetQuerySet":
        """回收列表页专用"""
        return self.with_asset_details().defer(
            "asset_recordcode__asset_description",
        )


class RecycleAsset(BaseModel):
    """
    回收资产管理模型

    记录资产的回收信息,关联出库记录,回收后资产状态自动变为"在库"。
    """

    RECORDCODE_PREFIX = "RECYCLE"

    class RecycleType(models.TextChoices):
        """回收类型"""

        NORMAL = "normal", "正常回收"
        ABNORMAL = "abnormal", "异常回收"
        OTHER = "other", "其他"

    outasset_recordcode = models.OneToOneField(
        OutAsset,
        to_field="recordcode",
        on_delete=models.PROTECT,
        verbose_name="对应的出库记录的资产唯一标识码",
        related_name="recycle_record",
        help_text="关联的出库记录的资产唯一标识码",
    )
    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        verbose_name="回收资产的资产唯一标识码",
        related_name="recycle_assets",
        on_delete=models.PROTECT,
        help_text="回收的资产唯一标识码(通过 recordcode 关联)",
    )
    recycle_asset_number = models.IntegerField(verbose_name="回收数量", default=1, help_text="回收的资产数量")
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="recycle_assets_operator",
        verbose_name="回收操作人工号",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="办理回收操作的人员工号(通过 recordcode 关联)",
    )
    recycle_type = models.CharField(
        verbose_name="回收类型",
        max_length=50,
        choices=RecycleType.choices,
        blank=True,
        null=True,
        help_text="回收原因/类型",
    )
    recycle_asset_date = models.DateField(verbose_name="回收日期", help_text="资产回收的日期")
    is_broken = models.BooleanField(default=False, verbose_name="回收时发现损坏", help_text="回收时是否发现资产损坏")
    broken_reason = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="损坏原因", help_text="回收时发现损坏的原因"
    )
    is_lost = models.BooleanField(default=False, verbose_name="回收时发现遗失", help_text="回收时是否发现资产遗失")
    lost_reason = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="遗失原因", help_text="回收时发现遗失的原因"
    )
    recycle_asset_description = models.TextField(
        verbose_name="回收资产描述", blank=True, null=True, help_text="回收的补充说明"
    )

    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(RecycleAssetQuerySet)()  # type: ignore[misc]
    all_objects = models.Manager()  # type: ignore[misc]

    class Meta:
        verbose_name = "回收资产管理"
        verbose_name_plural = "回收资产管理"
        db_table = "am_recycle_asset"
        indexes = [
            models.Index(fields=["outasset_recordcode"]),
            models.Index(fields=["asset_recordcode"]),
        ]

    def __str__(self) -> str:
        return f"回收{self.recordcode}-{self.asset_recordcode.asset_name}"
