"""
资产管理模型(核心模型)
"""

from typing import TYPE_CHECKING

from django.db import models

from apps.assetmanagement.models.asset_type import AssetType
from apps.assetmanagement.models.contract import Contract
from apps.assetmanagement.models.storage import Storage
from apps.usermanagement.models import Employee
from core.models import BaseModel, SoftDeleteManager


if TYPE_CHECKING:
    from django.db.models import Manager


class AssetQuerySet(models.QuerySet):
    """
    Asset 查询集优化

    提供预加载关联和字段精简方法,用于列表页和详情页的不同查询需求。
    """

    def with_basic_relations(self):
        """预加载基础关联(类型、合同、仓库)"""
        return self.select_related("asset_type_recordcode", "asset_contract_recordcode", "asset_storage_recordcode")

    def with_person_relations(self):
        """预加载人员关联(入库人、申请人、保管人)"""
        return self.select_related(
            "asset_entry_person_recordcode", "asset_applicant_recordcode", "asset_manager_recordcode"
        )

    def with_all_relations(self):
        """预加载所有常用关联"""
        return self.with_basic_relations().with_person_relations()

    def with_harddisk_sns(self):
        """预加载硬盘序列号"""
        return self.prefetch_related("harddisk_sns")

    def for_list(self):
        """列表页专用"""
        return (
            self.with_basic_relations()
            .with_person_relations()
            .defer(
                "asset_description",
            )
        )

    def for_search_list(self):
        """搜索结果列表"""
        return self.select_related(
            "asset_type_recordcode",
            "asset_storage_recordcode",
        ).defer(
            "asset_description",
        )


class Asset(BaseModel):
    """
    资产管理模型(架构优化版)

    核心资产模型,管理资产从入库、领用、报废全生命周期。

    状态流转:
    - in_store → in_use: 新资产出库
    - in_use → recycled_pending: 资产回收
    - recycled_pending → in_use: 回收资产重新发放
    - in_use → broken: 资产损坏
    - in_use → lost: 资产遗失
    - broken → damaged: 提交报废申请
    - lost → damaged: 提交报废申请
    - damaged → scrapped: 审批通过,完成报废
    - damaged → broken: 审批拒绝,退回损坏状态
    - damaged → lost: 审批拒绝,退回遗失状态
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "ASSET"

    class AssetStatus(models.TextChoices):
        """资产状态枚举(P2-6: TextChoices 改造)"""

        IN_STORE = "in_store", "在库"
        IN_USE = "in_use", "在用"
        RECYCLED_PENDING = "recycled_pending", "已回收待发放"
        BROKEN = "broken", "已损坏"
        REPAIRING = "repairing", "维修中"
        LOST = "lost", "已遗失"
        DAMAGED = "damaged", "待报废"
        SCRAPPED = "scrapped", "已报废"

    class UsageType(models.TextChoices):
        """资产使用性质"""

        NEW = "new", "全新"
        USED = "used", "二手"
        REFURBISHED = "refurbished", "翻新"

    class PhysicalGrade(models.TextChoices):
        """资产物理成色"""

        EXCELLENT = "excellent", "全新"
        GOOD = "good", "良好"
        FAIR = "fair", "一般"
        POOR = "poor", "较差"

    ASSET_STATUS_CHOICES = AssetStatus.choices

    asset_code = models.CharField(
        max_length=100, editable=False, verbose_name="资产编码", help_text="资产唯一编码,不可修改"
    )
    asset_name = models.CharField(max_length=100, verbose_name="资产名称", help_text="资产的名称")
    asset_purchase_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="资产购买价格", help_text="资产采购单价(元)"
    )
    asset_purchase_number = models.IntegerField(default=1, verbose_name="资产购买数量", help_text="采购数量")
    asset_unit = models.CharField(
        max_length=50, verbose_name="资产单位", blank=True, null=True, help_text="计量单位:台/套/个等"
    )
    asset_brand = models.CharField(
        max_length=100, verbose_name="资产品牌", blank=True, null=True, help_text="资产的品牌"
    )
    asset_specification = models.CharField(
        max_length=100, verbose_name="资产规格", blank=True, null=True, help_text="资产的规格型号"
    )
    asset_type_recordcode = models.ForeignKey(
        AssetType,
        to_field="recordcode",
        on_delete=models.PROTECT,
        related_name="assets",
        verbose_name="资产类型",
        help_text="关联的资产类型(通过 recordcode 关联)",
    )
    asset_contract_recordcode = models.ForeignKey(
        Contract,
        to_field="recordcode",
        related_name="assets",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="asset_contract",
        verbose_name="资产合同",
        help_text="关联的采购合同(通过 recordcode 关联)",
    )
    asset_purchase_date = models.DateField(verbose_name="资产购买日期", help_text="资产采购的日期")
    asset_warranty_period = models.IntegerField(
        default=0, verbose_name="保修期(年)", blank=True, null=True, help_text="资产保修期限(年)"
    )
    asset_entry_date = models.DateField(verbose_name="入库日期", help_text="资产入库的日期")
    asset_storage_recordcode = models.ForeignKey(
        Storage,
        to_field="recordcode",
        on_delete=models.PROTECT,
        related_name="assets",
        verbose_name="存储仓库",
        blank=True,
        null=True,
        help_text="资产当前所在仓库(通过 recordcode 关联)",
    )
    asset_entry_person_recordcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="assets_entry",
        verbose_name="资产入库人工号",
        blank=True,
        null=True,
        help_text="办理入库的人员工号(通过 recordcode 关联)",
    )
    asset_applicant_recordcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="assets_applicant",
        verbose_name="资产申请人工号",
        null=True,
        blank=True,
        help_text="资产申请人的工号(通过 recordcode 关联)",
    )
    asset_manager_recordcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="assets_manager",
        verbose_name="资产保管人",
        null=True,
        blank=True,
        help_text="资产保管人的工号(通过 recordcode 关联)",
    )
    asset_using_location = models.CharField(
        max_length=100, verbose_name="资产使用地点", blank=True, null=True, help_text="资产使用的地点"
    )
    usage_type = models.CharField(
        max_length=20,
        choices=UsageType.choices,
        default=UsageType.NEW,
        verbose_name="使用性质",
        help_text="资产使用性质:全新/二手/翻新",
    )
    physical_grade = models.CharField(
        max_length=20,
        choices=PhysicalGrade.choices,
        default=PhysicalGrade.GOOD,
        verbose_name="物理成色",
        help_text="资产物理成色:全新/良好/一般/较差",
    )
    qr_code = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="二维码",
        help_text="二维码内容(JSON格式),存储扫码查看资产详情的链接与资产编码",
    )
    asset_current_status = models.CharField(
        max_length=20,
        choices=ASSET_STATUS_CHOICES,
        default=AssetStatus.IN_STORE,
        verbose_name="资产当前状态",
        db_index=True,
        help_text="资产状态:在库/已回收待发放/在用/已损坏/维修中/已遗失/待报废/已报废",
    )
    asset_description = models.TextField(verbose_name="资产描述", blank=True, null=True, help_text="资产的补充说明")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    objects = SoftDeleteManager.from_queryset(AssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "资产管理"
        verbose_name_plural = "资产管理"
        db_table = "am_asset"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recordcode"]),
            models.Index(fields=["asset_code"]),
            models.Index(fields=["asset_current_status"]),
            models.Index(fields=["asset_type_recordcode"]),
            models.Index(fields=["asset_storage_recordcode"]),
            models.Index(fields=["asset_entry_person_recordcode"]),
            models.Index(fields=["asset_applicant_recordcode"]),
            models.Index(fields=["asset_manager_recordcode"]),
            models.Index(fields=["asset_contract_recordcode"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["asset_type_recordcode", "asset_current_status"], name="idx_asset_type_status"),
            models.Index(fields=["asset_storage_recordcode", "asset_current_status"], name="idx_asset_storage_status"),
            models.Index(
                fields=["asset_contract_recordcode", "asset_current_status"], name="idx_asset_contract_status"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["asset_code"],
                condition=models.Q(is_deleted=False),
                name="unique_asset_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["qr_code"],
                condition=models.Q(is_deleted=False),
                name="unique_qr_code_not_deleted",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.asset_name}({self.asset_code})"
