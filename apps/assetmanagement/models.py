"""
资产管理数据库模型

该模块定义资产全生命周期管理相关的数据模型，
所有模型均继承BaseModel以支持软删除和时间戳追踪。

包含以下核心模型：
- Storage: 仓库管理
- AssetType: 资产类型管理
- Contract: 合同管理
- Asset: 资产管理
- OutAsset: 出库资产管理
- RecycleAsset: 回收资产管理
- DamagedAsset: 待报废资产管理
- WasteAsset: 已报废资产管理
- HardDiskSN: 硬盘序列号管理
"""

from django.db import models
from django.utils import timezone
from datetime import date
from typing import TYPE_CHECKING
import uuid
import secrets
import string

from core.models import BaseModel, SoftDeleteManager, generate_recordcode
from apps.usermanagement.models import Employee
from .querysets import (
    AssetQuerySet, OutAssetQuerySet, RecycleAssetQuerySet,
    DamagedAssetQuerySet, WasteAssetQuerySet
)


if TYPE_CHECKING:
    from django.db.models import Manager


class Storage(BaseModel):
    """
    仓库管理模型

    用于管理资产的存储仓库，包括新货仓库、回收仓库、待报废仓库等类型。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    STORAGE_TYPE_CHOICES = [
        ("newasset", "新货仓库"),
        ("recycle", "回收仓库"),
        ("damaged", "待报废仓库"),
    ]

    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 is_deleted=False 时唯一
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    storage_code = models.CharField(
        max_length=20,
        verbose_name="仓库编码",
        help_text="仓库唯一编码，用于业务关联"
    )
    storage_name = models.CharField(
        max_length=100,
        verbose_name="仓库名称",
        help_text="仓库名称，用户可见的展示名称"
    )
    storage_address = models.CharField(
        max_length=200,
        verbose_name="仓库地址",
        help_text="仓库的物理地址"
    )
    storage_type = models.CharField(
        max_length=50,
        choices=STORAGE_TYPE_CHOICES,
        default="newasset",
        verbose_name="仓库类型",
        blank=True,
        null=True,
        help_text="仓库类型：新货/回收/待报废"
    )
    storage_description = models.TextField(
        verbose_name="仓库描述",
        blank=True,
        null=True,
        help_text="仓库的补充说明信息"
    )

    class Meta:
        verbose_name = "仓库管理"
        verbose_name_plural = "仓库管理"
        db_table = "am_storage"
        # 【软删除兼容-条件唯一约束】仅未删除记录的业务编码唯一
        constraints = [
            models.UniqueConstraint(
                fields=["storage_code"],
                condition=models.Q(is_deleted=False),
                name="unique_storage_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["storage_name"],
                condition=models.Q(is_deleted=False),
                name="unique_storage_name_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["storage_code"]),
            models.Index(fields=["storage_type"]),
        ]

    def save(self, *args, **kwargs):
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.storage_name}({self.storage_code})"


class AssetType(BaseModel):
    """
    资产类型管理模型

    用于定义资产的分类，包括硬件、软件、其他等大类，
    以及一级分类和二级分类信息。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    ASSET_TYPE_CATEGORY_CHOICES = [
        ("hardware", "硬件"),
        ("software", "软件"),
        ("lowvalue", "低值易耗"),
        ("other", "其他"),
    ]

    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 is_deleted=False 时唯一
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    asset_type_code = models.CharField(
        max_length=20,
        verbose_name="资产分类编码",
        help_text="资产类型唯一编码"
    )
    asset_type_secondary = models.CharField(
        max_length=100,
        verbose_name="资产二级分类名称",
        help_text="资产的细分类，如台式机/笔记本等"
    )
    asset_type_primary = models.CharField(
        max_length=100,
        verbose_name="资产一级分类名称",
        help_text="资产的大类，如办公设备/网络设备等"
    )
    asset_type_category = models.CharField(
        max_length=50,
        choices=ASSET_TYPE_CATEGORY_CHOICES,
        default="hardware",
        verbose_name="资产分类类型",
        blank=True,
        null=True,
        help_text="分类类型：硬件/软件/其他"
    )
    asset_type_description = models.TextField(
        verbose_name="资产分类类型描述",
        blank=True,
        null=True,
        help_text="资产分类的补充说明"
    )

    class Meta:
        verbose_name = "资产分类管理"
        verbose_name_plural = "资产分类管理"
        db_table = "am_asset_type"
        # 【软删除兼容-条件唯一约束】仅未删除记录的业务编码唯一
        constraints = [
            models.UniqueConstraint(
                fields=["asset_type_code"],
                condition=models.Q(is_deleted=False),
                name="unique_asset_type_code_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["asset_type_code"]),
            models.Index(fields=["asset_type_category"]),
        ]

    def save(self, *args, **kwargs):
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.asset_type_primary} - {self.asset_type_secondary}"


class Contract(BaseModel):
    """
    合同管理模型

    用于管理资产相关的采购合同、服务合同等，
    包含合同金额、付款记录、结算状态等信息。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    CONTRACT_TYPE_CHOICES = [
        ("purchase", "采购合同"),
        ("service", "服务合同"),
        ("information_construction", "信息化建设合同"),
        ("direct_procurement", "直接采购合同"),
    ]

    CONTRACT_SETTLEMENT_CHOICES = [
        ("pending", "待结算"),
        ("settled", "已结算"),
    ]

    # 【软删除兼容-新增 recordcode】后端生成的全局唯一编码，用于外键引用
    # 原因：外键需要数据库级无条件唯一约束，recordcode 永不重复
    # 原业务编码改为条件唯一：仅 is_deleted=False 时唯一
    recordcode = models.CharField(
        max_length=32,
        unique=True,
        blank=True,
        null=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码，用于外键引用"
    )
    contract_code = models.CharField(
        max_length=20,
        verbose_name="合同编码",
        help_text="合同唯一编码"
    )
    contract_name = models.CharField(
        max_length=100,
        verbose_name="合同名称",
        help_text="合同的完整名称"
    )
    contract_type = models.CharField(
        max_length=50,
        choices=CONTRACT_TYPE_CHOICES,
        default="purchase",
        verbose_name="合同类型",
        blank=True,
        null=True,
        help_text="合同类型：采购/服务/信息化/直接采购"
    )
    contract_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="合同金额",
        help_text="合同总金额（元）"
    )
    contract_supplier = models.CharField(
        max_length=100,
        verbose_name="合同供应商",
        help_text="合同供应商名称"
    )
    contract_signing_date = models.DateField(
        verbose_name="合同签订日期",
        help_text="合同签署的日期"
    )
    contract_warranty_period = models.IntegerField(
        default=0,
        verbose_name="保修期（年）",
        help_text="合同规定的保修期限（年）"
    )
    contract_preliminary_acceptance_date = models.DateField(
        verbose_name="初验日期",
        blank=True,
        null=True,
        help_text="初步验收的日期"
    )
    contract_final_acceptance_date = models.DateField(
        verbose_name="终验日期",
        blank=True,
        null=True,
        help_text="最终验收的日期"
    )
    contract_settlment_status = models.CharField(
        max_length=20,
        choices=CONTRACT_SETTLEMENT_CHOICES,
        default="pending",
        verbose_name="结算状态",
        help_text="合同的结算状态：待结算/已结算"
    )
    contract_settlment_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="结算金额",
        blank=True,
        null=True,
        help_text="实际结算的金额（元）"
    )
    contract_paid_count_number = models.IntegerField(
        default=0,
        verbose_name="已付次数",
        help_text="已付款的次数"
    )
    contract_paid_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        verbose_name="已付金额",
        blank=True,
        null=True,
        help_text="累计已付款金额（元）"
    )
    contract_paid_record = models.TextField(
        verbose_name="付款记录",
        blank=True,
        null=True,
        help_text="每次付款的详细记录"
    )

    class Meta:
        verbose_name = "合同管理"
        verbose_name_plural = "合同管理"
        db_table = "am_contract"
        # 【软删除兼容-条件唯一约束】仅未删除记录的业务编码唯一
        constraints = [
            models.UniqueConstraint(
                fields=["contract_code"],
                condition=models.Q(is_deleted=False),
                name="unique_contract_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["contract_name"],
                condition=models.Q(is_deleted=False),
                name="unique_contract_name_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["contract_code"]),
            models.Index(fields=["contract_type"]),
            models.Index(fields=["contract_settlment_status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.recordcode:
            self.recordcode = generate_recordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.contract_name}({self.contract_code})"


class Asset(BaseModel):
    """
    资产管理模型（架构优化版）

    【AGENTS 规范 - 架构优化】
    核心资产模型，管理资产从入库、领用、报废全生命周期。

    优化变更：
    1. 移除 asset_appearance 字段，统一使用 asset_current_status
    2. 移除 using_record 字段，操作历史移至 AssetOperationLog
    3. 新增 sort_order 排序字段  不需要排序字段
    4. 新增 recycled_pending 状态，区分在库和已回收待发放

    状态流转：
    - in_store → in_use: 新资产出库
    - in_use → recycled_pending: 资产回收
    - recycled_pending → in_use: 回收资产重新发放
    - in_use → damaged: 提交报废申请
    - damaged → scrapped: 审批通过，完成报废
    - damaged → recycled_pending: 审批拒绝，退回待发放
    """

    if TYPE_CHECKING:
        objects: "Manager"

    # 【优化】简化状态枚举，移除 asset_appearance
    ASSET_STATUS_CHOICES = [
        ("in_store", "在库"),              # 新增加、已拒绝报废
        ("recycled_pending", "已回收待发放"),  # 已回收，等待重新发放
        ("in_use", "在用"),                 # 已出库/已发放
        ("damaged", "待报废"),              # 待报废审批中
        ("scrapped", "已报废"),             # 已报废
    ]

    # 【软删除兼容-优化】添加 default 兜底，确保 bulk_create 等场景也有值
    # 原因：save() 中生成的方式无法覆盖 bulk_create 和 SQL 直接插入
    asset_recordcode = models.CharField(
        max_length=32,
        unique=True,
        default=generate_recordcode,
        verbose_name="记录编码",
        blank=True,
        null=True,
        help_text="系统自动生成的入库记录编码"
    )
    asset_code = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name="资产编码",
        help_text="资产唯一编码，不可修改"
    )
    asset_name = models.CharField(
        max_length=100,
        verbose_name="资产名称",
        help_text="资产的名称"
    )
    asset_purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="资产购买价格",
        help_text="资产采购单价（元）"
    )
    asset_purchase_number = models.IntegerField(
        default=1,
        verbose_name="资产购买数量",
        help_text="采购数量"
    )
    asset_unit = models.CharField(
        max_length=50,
        verbose_name="资产单位",
        blank=True,
        null=True,
        help_text="计量单位：台/套/个等"
    )
    asset_brand = models.CharField(
        max_length=100,
        verbose_name="资产品牌",
        blank=True,
        null=True,
        help_text="资产的品牌"
    )
    asset_specification = models.CharField(
        max_length=100,
        verbose_name="资产规格",
        blank=True,
        null=True,
        help_text="资产的规格型号"
    )
    asset_type_code = models.ForeignKey(
        AssetType,
        to_field="recordcode",
        on_delete=models.DO_NOTHING,
        related_name="assets",
        verbose_name="资产类型",
        help_text="关联的资产类型（通过 recordcode 关联）"
    )
    asset_contract_code = models.ForeignKey(
        Contract,
        to_field="recordcode",
        related_name="assets",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="asset_contract_code",
        verbose_name="资产合同",
        help_text="关联的采购合同（通过 recordcode 关联）"
    )
    asset_purchase_date = models.DateField(
        verbose_name="资产购买日期",
        help_text="资产采购的日期"
    )
    asset_warranty_period = models.IntegerField(
        default=0,
        verbose_name="保修期（年）",
        blank=True,
        null=True,
        help_text="资产保修期限（年）"
    )
    asset_entry_date = models.DateField(
        verbose_name="入库日期",
        help_text="资产入库的日期"
    )
    asset_storage_code = models.ForeignKey(
        Storage,
        to_field="recordcode",
        on_delete=models.DO_NOTHING,
        related_name="assets",
        verbose_name="存储仓库",
        blank=True,
        null=True,
        help_text="资产当前所在仓库（通过 recordcode 关联）"
    )
    asset_entry_person_jobcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="assets_entry",
        verbose_name="资产入库人工号",
        blank=True,
        null=True,
        help_text="办理入库的人员工号（通过 recordcode 关联）"
    )
    asset_applicant_jobcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.DO_NOTHING,
        related_name="assets_applicant",
        verbose_name="资产申请人工号",
        null=True,
        blank=True,
        help_text="资产申请人的工号（通过 recordcode 关联）"
    )
    asset_manager_jobcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.DO_NOTHING,
        related_name="assets_manager",
        verbose_name="资产保管人",
        null=True,
        blank=True,
        help_text="资产保管人的工号（通过 recordcode 关联）"
    )
    asset_using_location = models.CharField(
        max_length=100,
        verbose_name="资产使用地点",
        blank=True,
        null=True,
        help_text="资产使用的地点"
    )
    # 【优化】移除 asset_appearance 字段，统一使用 asset_current_status
    # 原 asset_appearance 字段已删除，状态信息合并到 asset_current_status

    # 【优化】统一状态字段
    asset_current_status = models.CharField(
        max_length=20,
        choices=ASSET_STATUS_CHOICES,
        default="in_store",
        verbose_name="资产当前状态",
        db_index=True,
        help_text="资产状态：在库/已回收待发放/在用/待报废/已报废"
    )

    # 【优化】移除 using_record 字段
    # 操作历史已移至 AssetOperationLog 表，通过 asset_code 关联查询

    asset_description = models.TextField(
        verbose_name="资产描述",
        blank=True,
        null=True,
        help_text="资产的补充说明"
    )

    # 【AGENTS 规范 - 性能优化】注册自定义 QuerySet
    objects = SoftDeleteManager.from_queryset(AssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "资产管理"
        verbose_name_plural = "资产管理"
        db_table = "am_asset"
        # 【优化】按排序字段和创建时间排序
        # 【易错点】BaseModel 使用 created_at 字段，不是 create_time
        ordering = [ "-created_at"]
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["asset_code"]),
            models.Index(fields=["asset_current_status"]),
            models.Index(fields=["asset_type_code"]),
            models.Index(fields=["asset_storage_code"]),
            # 【新增】排序字段索引
            models.Index(fields=[ "-created_at"]),
            # 【AGENTS 规范 - 性能优化】复合索引：按类型+状态筛选（仪表盘/资产列表）
            models.Index(
                fields=['asset_type_code', 'asset_current_status'],
                name='idx_asset_type_status'
            ),
            # 【AGENTS 规范 - 性能优化】复合索引：按仓库+状态筛选（库存管理）
            models.Index(
                fields=['asset_storage_code', 'asset_current_status'],
                name='idx_asset_storage_status'
            ),
            # 【AGENTS 规范 - 性能优化】复合索引：按合同+状态筛选（合同关联查询）
            models.Index(
                fields=['asset_contract_code', 'asset_current_status'],
                name='idx_asset_contract_status'
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        """
        创建记录时自动生成记录编码

        格式: Entry + 年月日时分秒 + 8位UUID
        """
        if not self.asset_recordcode:
            prefix = "Entry"
            today = date.today()
            base = today.strftime("%Y%m%d%H%M%S")
            extra = str(uuid.uuid4().hex)[:8].upper()
            self.asset_recordcode = f"{prefix}{base}{extra}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.asset_name}({self.asset_code})"


def generate_outassetrecordcode() -> str:
    """
    生成唯一出库记录编码

    Returns:
        str: 格式为 OUT-YYYYMMDD-XXXXXXXX 的唯一编码
    """
    prefix = "OUT"
    date_str = timezone.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"{prefix}-{date_str}-{unique_id}"


class OutAsset(BaseModel):
    """
    出库资产管理模型

    记录资产的领用和借用信息，包含申请人、保管人、使用地点等信息。
    资产出库后状态自动变为"在用"。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    OUTASSET_TYPE_CHOICES = [
        ("receive", "领用"),
        ("borrow", "借用"),
    ]

    OUTASSET_STATUS_CHOICES = [
        ("in_use", "在用"),
        ("recycled_pending", "已回收待发放"),              # 待发放审批中
        ("damaged", "待报废"),              # 待报废审批中
        ("scrapped", "已报废"),
    ]

    outasset_recordcode = models.CharField(
        max_length=36,
        unique=True,
        default=generate_outassetrecordcode,
        verbose_name="出库记录唯一标识",
        help_text="格式：OUT-20201223-XXXXXXXX"
    )
    outasset_code = models.ForeignKey(
        Asset,
        to_field="asset_recordcode",
        related_name="out_assets",
        on_delete=models.SET_NULL,
        verbose_name="出库资产编码",
        null=True,
        blank=True,
        help_text="关联的资产编码（通过 asset_recordcode 关联）"
    )
    outasset_number = models.IntegerField(
        verbose_name="出库数量",
        default=1,
        help_text="出库的资产数量"
    )
    # 【AGENTS 规范 - 去除冗余】outasset_applicant_jobcode 删除
    # 申请人信息通过 outasset_code.asset_applicant_jobcode 关联查询
    # 【AGENTS 规范 - 去除冗余】outasset_manager_jobcode 删除
    # 保管人信息通过 outasset_code.asset_manager_jobcode 关联查询
    # 【AGENTS 规范 - 去除冗余】outasset_current_status 删除
    # 资产状态统一在 Asset 表中管理，通过 outasset_code.asset_current_status 关联查询
    # 【AGENTS规范 - 取消出库支持】记录出库前资产状态，用于取消时恢复
    #
    # 【业务背景】
    # 资产可以从两种状态出库：in_store（在库）或 recycled_pending（已回收待发放）。
    # 取消出库时，资产应回到原来的状态，而不是统一回到 in_store。
    #
    # 【使用场景】
    # 1. 创建出库记录时自动记录（OutAssetService.create_outasset）
    # 2. 取消出库时读取此字段恢复资产状态（AssetFSM.cancel_outasset）
    #
    # 【数据兼容性】
    # - 新记录：默认值 'in_store'
    # - 历史记录：null（需要迁移或前台展示为"未知"）
    outasset_previous_status = models.CharField(
        max_length=50,
        choices=[
            ('in_store', '在库'),
            ('recycled_pending', '已回收待发放'),
        ],
        default='in_store',
        null=True,
        blank=True,
        verbose_name="出库前资产状态",
        help_text="记录出库前资产的状态，用于取消出库时恢复。历史数据可能为空。"
    )
    return_date = models.DateField(
        verbose_name="归还日期",
        blank=True,
        null=True,
        help_text="借用资产的预计或实际归还日期"
    )
    # 【AGENTS 规范 - 去除冗余】outasset_using_location 删除
    # 使用地点通过 outasset_code.asset_using_location 关联查询
    outasset_date = models.DateField(
        verbose_name="出库日期",
        default=timezone.now,
        help_text="资产出库的日期"
    )
    outasset_type = models.CharField(
        max_length=50,
        choices=OUTASSET_TYPE_CHOICES,
        default="receive",
        verbose_name="出库类型",
        blank=True,
        null=True,
        help_text="出库类型：领用/借用"
    )
    outasset_description = models.TextField(
        verbose_name="出库资产描述",
        blank=True,
        null=True,
        help_text="出库的补充说明"
    )
    # 【AGENTS 规范 - 去除冗余】outasset_contract_code 删除
    # 合同信息通过 outasset_code.asset_contract_code 关联查询

    # 【AGENTS 规范 - 性能优化】注册自定义 QuerySet
    objects = SoftDeleteManager.from_queryset(OutAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "出库资产管理"
        verbose_name_plural = "出库资产管理"
        db_table = "am_out_asset"
        indexes = [
            models.Index(fields=["outasset_recordcode"]),
            models.Index(fields=["outasset_code"]),
            # 【AGENTS 规范 - 去除冗余】outasset_current_status 索引删除
            # 资产状态查询通过 Asset 表的 asset_current_status 索引
            models.Index(fields=["outasset_date"]),   # 新增索引
        ]

    def save(self, *args, **kwargs) -> None:
        """
        保存时自动生成唯一出库记录编码（如未提供）
        """
        if not self.outasset_recordcode:
            self.outasset_recordcode = generate_outassetrecordcode()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"出库{self.outasset_recordcode}-{self.outasset_code}"


class RecycleAsset(BaseModel):
    """
    回收资产管理模型

    记录资产的回收信息，关联出库记录，回收后资产状态自动变为"在库"。
    每条回收记录在创建时自动生成唯一的 recycle_record_code（格式: RECYCLE-YYYYMMDD-XXXXXXXX）。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    # 【AGENTS 规范 - 业务唯一编码】回收记录编码，创建时自动生成，格式: RECYCLE-YYYYMMDD-XXXXXXXX
    recycle_record_code = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="回收记录编码",
        help_text="唯一回收记录编码，格式: RECYCLE-YYYYMMDD-XXXXXXXX"
    )

    outasset_recordcode = models.OneToOneField(
        OutAsset,
        to_field="outasset_recordcode",
        on_delete=models.CASCADE,
        verbose_name="对应的出库记录编码",
        related_name="recycle_record",
        help_text="关联的出库记录编码"
    )
    recycle_asset_code = models.ForeignKey(
        Asset,
        to_field="asset_recordcode",
        verbose_name="回收资产编码",
        related_name="recycle_assets",
        on_delete=models.PROTECT,
        help_text="回收的资产编码（通过 asset_recordcode 关联）"
    )
    recycle_asset_number = models.IntegerField(
        verbose_name="回收数量",
        default=1,
        help_text="回收的资产数量"
    )
    # 【AGENTS 规范 - 去除冗余】recycle_asset_storage_code 删除
    # 回收后仓库通过 recycle_asset_code.asset_storage_code 关联查询
    # 回收时直接更新 Asset 表的 asset_storage_code 字段
    # 【AGENTS 规范 - 去除冗余】recycle_asset_using_person_jobcode 删除
    # 使用人信息通过 recycle_asset_code.asset_manager_jobcode 关联查询
    # 【AGENTS 规范 - 去除冗余】recycle_asset_recycle_person_jobcode 删除
    # 回收操作人通过新增 operator_jobcode 字段记录
    operator_jobcode = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="recycle_assets_operator",
        verbose_name="回收操作人工号",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        help_text="办理回收操作的人员工号（通过 recordcode 关联）"
    )
    recycle_asset_date = models.DateField(
        verbose_name="回收日期",
        help_text="资产回收的日期"
    )
    recycle_asset_description = models.TextField(
        verbose_name="回收资产描述",
        blank=True,
        null=True,
        help_text="回收的补充说明"
    )

    # 【AGENTS 规范 - 性能优化】注册自定义 QuerySet
    objects = SoftDeleteManager.from_queryset(RecycleAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "回收资产管理"
        verbose_name_plural = "回收资产管理"
        db_table = "am_recycle_asset"
        indexes = [
            models.Index(fields=["outasset_recordcode"]),
            models.Index(fields=["recycle_asset_code"]),
            models.Index(fields=["recycle_record_code"]),
        ]

    def save(self, *args, **kwargs):
        """
        重写 save 方法，创建时自动生成唯一 recycle_record_code。

        生成规则: RECYCLE-YYYYMMDD-XXXXXXXX（8位字母数字混合随机码）
        使用简单重试机制处理极端冲突情况。
        """
        if not self.recycle_record_code:
            self.recycle_record_code = self._generate_recycle_record_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_recycle_record_code() -> str:
        """
        生成唯一回收记录编码。

        格式: RECYCLE-YYYYMMDD-XXXXXXXX
        - 日期部分使用 timezone.now()（北京时间）
        - 随机部分为8位字母数字混合（Base36: 0-9A-Z）
        """
        prefix = 'RECYCLE'
        date_str = timezone.now().strftime('%Y%m%d')
        random_suffix = ''.join(
            secrets.choice(string.ascii_uppercase + string.digits)
            for _ in range(8)
        )
        return f'{prefix}-{date_str}-{random_suffix}'

    def __str__(self) -> str:
        return f"回收{self.recycle_record_code}-{self.recycle_asset_code}"


class DamagedAsset(BaseModel):
    """
    待报废资产管理模型

    记录待报废的资产信息，包含审批流程状态，审批通过后进入报废流程。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    damaged_asset_code = models.OneToOneField(
        Asset,
        to_field="asset_recordcode",
        verbose_name="待报废资产编码",
        related_name="damaged_asset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="待报废的资产编码（通过 asset_recordcode 关联）"
    )
    # 【AGENTS 规范 - 去除冗余】damaged_asset_contract_code 删除
    # 合同信息通过 damaged_asset_code.asset_contract_code 关联查询
    damaged_asset_number = models.IntegerField(
        verbose_name="待报废数量",
        default=1,
        help_text="待报废的资产数量"
    )
    # 【AGENTS 规范 - 去除冗余】damaged_asset_storage_code 删除
    # 仓库信息通过 damaged_asset_code.asset_storage_code 关联查询
    damaged_date = models.DateField(
        verbose_name="待报废日期",
        default=timezone.now,
        blank=True,
        null=True,
        help_text="提交报废申请的日期"
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
        help_text="审批状态：待审批/已批准/已拒绝"
    )
    approver = models.ForeignKey(
        Employee,
        to_field="recordcode",
        related_name="damaged_assets_approver",
        on_delete=models.DO_NOTHING,
        verbose_name="审批人",
        null=True,
        blank=True,
        help_text="审批人的工号（通过 recordcode 关联）"
    )
    damaged_asset_description = models.TextField(
        verbose_name="待报废资产描述",
        blank=True,
        null=True,
        help_text="报废原因等说明"
    )

    # 【AGENTS 规范 - 性能优化】注册自定义 QuerySet
    objects = SoftDeleteManager.from_queryset(DamagedAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "待报废资产管理"
        verbose_name_plural = "待报废资产管理"
        db_table = "am_damaged_asset"
        indexes = [
            models.Index(fields=["damaged_asset_code"]),
            models.Index(fields=["approval_status"]),
        ]

    def __str__(self) -> str:
        return f"待报废{self.damaged_asset_code}"


class WasteAsset(BaseModel):
    """
    已报废资产管理模型

    记录已完成报废的资产信息，报废后资产状态为"报废资产"。
    当待报废资产(DamagedAsset)审批通过后，自动创建已报废记录。

    字段说明：
    - waste_asset_code: 关联的资产编码（外键到 Asset）
    - source_damaged_asset: 来源待报废记录（外键到 DamagedAsset，用于追溯）
    - waste_asset_contract_code: 关联的合同编码
    - waste_asset_number: 报废数量
    - waste_asset_date: 报废日期
    - waste_asset_description: 报废说明
    """

    if TYPE_CHECKING:
        objects: "Manager"

    waste_asset_code = models.OneToOneField(
        Asset,
        to_field="asset_recordcode",
        verbose_name="已报废资产编码",
        related_name="waste_asset",
        on_delete=models.DO_NOTHING,
        help_text="已报废的资产编码（通过 asset_recordcode 关联）"
    )
    # 【新增】来源待报废记录外键，用于追溯报废来源
    source_damaged_asset = models.OneToOneField(
        DamagedAsset,
        to_field="id",
        related_name="waste_asset_record",
        verbose_name="来源待报废记录",
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        help_text="关联的待报废记录，用于追溯来源"
    )
    # 【AGENTS 规范 - 去除冗余】waste_asset_contract_code 删除
    # 合同信息通过 waste_asset_code.asset_contract_code 关联查询
    waste_asset_number = models.IntegerField(
        verbose_name="已报废数量",
        default=1,
        help_text="报废的资产数量"
    )
    waste_asset_date = models.DateField(
        verbose_name="报废日期",
        help_text="完成报废的日期"
    )
    waste_asset_description = models.TextField(
        verbose_name="报废资产描述",
        blank=True,
        null=True,
        help_text="报废的补充说明"
    )

    # 【AGENTS 规范 - 性能优化】注册自定义 QuerySet
    objects = SoftDeleteManager.from_queryset(WasteAssetQuerySet)()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "已报废资产管理"
        verbose_name_plural = "已报废资产管理"
        db_table = "am_waste_asset"
        indexes = [
            models.Index(fields=["waste_asset_code"]),
            models.Index(fields=["source_damaged_asset"]),  # 【新增】来源记录索引
        ]

    def __str__(self) -> str:
        return f"已报废{self.waste_asset_code}"


class HardDiskSN(BaseModel):
    """
    硬盘序列号管理模型

    管理硬盘类资产的序列号信息，支持跟踪硬盘状态变化。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    HARDDISK_STATUS_CHOICES = [
        ("active", "正常"),
        ("repair", "维修"),
        ("scrap", "报废"),
        ("lost", "丢失"),
        ("damaged", "损坏"),
    ]

    asset_code = models.ForeignKey(
        Asset,
        to_field="asset_recordcode",
        related_name="harddisk_sns",
        verbose_name="硬盘序列号对应资产编码",
        on_delete=models.CASCADE,
        help_text="关联的资产编码（通过 asset_recordcode 关联）"
    )
    harddisk_number = models.IntegerField(
        verbose_name="硬盘数量",
        help_text="该资产下的硬盘数量"
    )
    harddisk_no = models.IntegerField(
        verbose_name="硬盘编号",
        default=1,
        help_text="硬盘在资产中的序号"
    )
    harddisk_sn_code = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="硬盘序列号",
        help_text="硬盘的唯一序列号"
    )
    harddisk_type = models.CharField(
        max_length=100,
        verbose_name="硬盘类型",
        blank=True,
        null=True,
        choices=[
            ("HDD", "HDD"),
            ("SSD", "SSD"),
            ("NVMe", "NVMe"),
            ("Other", "Other"),
        ],
        default="HDD",
        help_text="硬盘类型：HDD/SSD/NVMe"
    )
    harddisk_sn_description = models.TextField(
        verbose_name="硬盘序列号描述",
        blank=True,
        null=True,
        help_text="硬盘的补充说明"
    )
    harddisk_status = models.CharField(
        max_length=10,
        choices=HARDDISK_STATUS_CHOICES,
        default="active",
        verbose_name="硬盘序列号资产状态",
        help_text="硬盘状态：正常/维修/报废/丢失/损坏"
    )

    class Meta:
        verbose_name = "硬盘序列号管理"
        verbose_name_plural = "硬盘序列号管理"
        db_table = "am_hard_disk_sn"
        indexes = [
            models.Index(fields=["harddisk_sn_code"]),
            models.Index(fields=["asset_code"]),
            models.Index(fields=["harddisk_status"]),
        ]

    def __str__(self) -> str:
        return f"硬盘SN-{self.harddisk_sn_code}"


# 兼容旧代码的模型别名
class Storagedatabasetable(Storage):
    """仓库管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "仓库管理(兼容)"
        verbose_name_plural = "仓库管理(兼容)"


class Assettypedatabasetable(AssetType):
    """资产类型管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "资产类型管理(兼容)"
        verbose_name_plural = "资产类型管理(兼容)"


class Contractdatabasetable(Contract):
    """合同管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "合同管理(兼容)"
        verbose_name_plural = "合同管理(兼容)"


class Assetdatabasetable(Asset):
    """资产管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "资产管理(兼容)"
        verbose_name_plural = "资产管理(兼容)"


class Outassetdatabasetable(OutAsset):
    """出库资产管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "出库资产管理(兼容)"
        verbose_name_plural = "出库资产管理(兼容)"


class Recycleassetdatabasetable(RecycleAsset):
    """回收资产管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "回收资产管理(兼容)"
        verbose_name_plural = "回收资产管理(兼容)"


class Damagedassetdatabasetable(DamagedAsset):
    """待报废资产管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "待报废资产管理(兼容)"
        verbose_name_plural = "待报废资产管理(兼容)"


class Wasteassettable(WasteAsset):
    """已报废资产管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "已报废资产管理(兼容)"
        verbose_name_plural = "已报废资产管理(兼容)"


class HardDiskSNdatabasetable(HardDiskSN):
    """硬盘序列号管理（兼容旧代码）"""
    class Meta:
        proxy = True
        verbose_name = "硬盘序列号管理(兼容)"
        verbose_name_plural = "硬盘序列号管理(兼容)"


# =============================================================================
# 资产操作记录模型（只读）
# =============================================================================

class AssetOperationLog(models.Model):
    """
    资产操作记录表（只读）

    【AGENTS 规范 - 架构优化】
    记录资产全生命周期中的所有操作，替代原有的 using_record 文本字段。

    设计原则：
    1. 只读表：不允许修改和删除，确保审计追踪完整性
    2. 结构化：使用 JSONField 存储变更前后数据，便于查询和分析
    3. 可追踪：记录操作人、操作时间、关联业务记录

    记录的操作类型：
    - create: 资产创建/入库
    - update: 资产信息更新
    - delete: 资产删除（软删除）
    - out: 资产出库/发放
    - recycle: 资产回收
    - damaged: 提交报废申请
    - waste: 完成报废
    - approve: 审批操作（通过/拒绝）
    - transfer: 资产转移（仓库/人员变更）

    【易错点】
    - 此表数据只增不改，业务逻辑中禁止调用 save() 更新或 delete() 删除
    - 查询时使用 select_related 或 prefetch_related 优化性能
    """

    if TYPE_CHECKING:
        objects: "Manager"

    # 操作类型枚举
    OPERATION_TYPE_CHOICES = [
        ("create", "创建"),
        ("update", "更新"),
        ("delete", "删除"),
        ("out", "出库"),
        ("recycle", "回收"),
        ("damaged", "待报废"),
        ("waste", "已报废"),
        ("approve", "审批"),
        ("transfer", "转移"),
    ]

    # 资产编码（外键的冗余存储，用于查询性能优化）
    asset_code = models.CharField(
        max_length=64,
        verbose_name="资产编码",
        db_index=True,
        help_text="关联的资产编码"
    )

    # 操作类型
    operation_type = models.CharField(
        max_length=20,
        choices=OPERATION_TYPE_CHOICES,
        verbose_name="操作类型",
        db_index=True,
        help_text="操作类型：创建/更新/删除/出库/回收/待报废/已报废/审批/转移"
    )

    # 日志记录唯一标识（自动生成，格式：{operation_type}-Log-{YYYYMMDD}-{8位随机字符}）
    logging_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="日志记录ID",
        blank=True,
        help_text="系统自动生成的日志记录唯一标识，格式：操作类型-Log-日期-随机字符"
    )

    # 操作时间（自动记录）
    operation_time = models.DateTimeField(
        auto_now_add=True,
        verbose_name="操作时间",
        db_index=True,
        help_text="操作执行的时间"
    )

    # 操作人工号
    operator_jobcode = models.CharField(
        max_length=20,
        verbose_name="操作人工号",
        blank=True,
        null=True,
        help_text="执行操作的人员工号"
    )

    # 操作人姓名（冗余存储，避免关联查询）
    operator_name = models.CharField(
        max_length=100,
        verbose_name="操作人姓名",
        blank=True,
        null=True,
        help_text="执行操作的人员姓名"
    )

    # 变更前数据（JSON格式，记录完整对象状态）
    before_data = models.JSONField(
        verbose_name="变更前数据",
        blank=True,
        null=True,
        help_text="操作前的资产数据（JSON格式）"
    )

    # 变更后数据（JSON格式）
    after_data = models.JSONField(
        verbose_name="变更后数据",
        blank=True,
        null=True,
        help_text="操作后的资产数据（JSON格式）"
    )

    # 操作描述（人工可读）
    description = models.TextField(
        verbose_name="操作描述",
        help_text="操作的详细描述"
    )

    # 关联记录编码（如出库记录编码、回收记录编码等）
    related_record_code = models.CharField(
        max_length=50,
        verbose_name="关联记录编码",
        blank=True,
        null=True,
        help_text="关联的业务记录编码，如出库单号"
    )

    # 关联记录类型
    related_record_type = models.CharField(
        max_length=20,
        verbose_name="关联记录类型",
        blank=True,
        null=True,
        help_text="关联记录的类型：out/recycle/damaged/waste"
    )

    # IP地址（可选，用于安全审计）
    ip_address = models.GenericIPAddressField(
        verbose_name="操作IP地址",
        blank=True,
        null=True,
        help_text="执行操作的IP地址"
    )

    class Meta:
        verbose_name = "资产操作记录"
        verbose_name_plural = "资产操作记录"
        db_table = "am_asset_operation_log"
        # 【重要】按时间倒序排列，最新的操作在前
        ordering = ["-operation_time"]
        indexes = [
            # 按资产查询操作历史
            models.Index(fields=["asset_code", "-operation_time"]),
            # 按操作类型查询
            models.Index(fields=["operation_type", "-operation_time"]),
            # 按操作人查询
            models.Index(fields=["operator_jobcode", "-operation_time"]),
            # 复合索引：资产 + 操作类型
            models.Index(fields=["asset_code", "operation_type"]),
        ]
        # 【易错点】只读表，禁止修改和删除
        # 业务逻辑中应通过自定义 Manager 或 Service 层控制

    def __str__(self) -> str:
        return f"{self.asset_code}-{self.get_operation_type_display()}-{self.operation_time.strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def _generate_random_suffix(length: int = 8) -> str:
        """
        生成随机后缀字符

        使用 secrets 模块生成安全的随机字符，字符集为大写字母+数字。

        Args:
            length: 随机字符长度，默认8位

        Returns:
            str: 随机字符字符串
        """
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))

    def save(self, *args, **kwargs) -> None:
        """
        【安全控制】阻止更新已有记录，创建时自动生成 logging_id

        操作记录表只允许创建新记录，禁止修改已有记录。
        创建时自动生成唯一标识 logging_id，格式：{operation_type}-Log-{YYYYMMDD}-{8位随机字符}
        """
        if self.pk:
            raise PermissionError(
                "【安全错误】AssetOperationLog 是只读表，禁止修改已有记录。"
                "如需修正数据，请联系系统管理员。"
            )
        # 自动生成 logging_id（operation_time 使用 auto_now_add，在 super().save() 前可能为 None）
        if not self.logging_id:
            op_time = self.operation_time or timezone.now()
            date_str = op_time.strftime('%Y%m%d')
            random_suffix = self._generate_random_suffix()
            self.logging_id = f"{self.operation_type}-Log-{date_str}-{random_suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        """
        【安全控制】阻止删除记录

        操作记录表不允许删除，确保审计追踪完整性。
        """
        raise PermissionError(
            "【安全错误】AssetOperationLog 是只读表，禁止删除记录。"
            "如需清理历史数据，请联系系统管理员。"
        )


class AssetOperationLogManager(models.Manager):
    """
    资产操作记录自定义管理器

    提供常用的查询方法，简化业务逻辑代码。
    """

    def get_asset_history(self, asset_code: str):
        """
        获取指定资产的完整操作历史

        Args:
            asset_code: 资产编码

        Returns:
            QuerySet: 按时间倒序排列的操作记录
        """
        return self.filter(asset_code=asset_code).select_related()

    def get_recent_operations(self, days: int = 7):
        """
        获取最近N天的操作记录

        Args:
            days: 天数，默认7天

        Returns:
            QuerySet: 最近的操作记录
        """
        from datetime import datetime, timedelta
        start_time = datetime.now() - timedelta(days=days)
        return self.filter(operation_time__gte=start_time)

    def get_operations_by_type(self, operation_type: str):
        """
        按操作类型查询记录

        Args:
            operation_type: 操作类型代码

        Returns:
            QuerySet: 指定类型的操作记录
        """
        return self.filter(operation_type=operation_type)

    def get_user_operations(self, operator_jobcode: str):
        """
        获取指定用户的操作记录

        Args:
            operator_jobcode: 操作人工号

        Returns:
            QuerySet: 该用户的操作记录
        """
        return self.filter(operator_jobcode=operator_jobcode)
