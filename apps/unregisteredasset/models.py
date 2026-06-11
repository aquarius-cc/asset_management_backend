"""
未登记资产管理模型

该模块定义未登记资产的数据模型，管理不在账资产的发现、核实、处理全流程。

【AGENTS 规范 - 模型设计】
- 继承 BaseModel 获得软删除和时间戳功能
- 字段数量控制在 25 个以内
- 使用字符串形式引用跨应用模型（'app.Model'）
- 定义清晰的 choices 和 help_text

【跨应用关联】
- assetmanagement.Asset: 关联资产（字符串引用）
- assetmanagement.AssetType: 资产类型（字符串引用）
- assetmanagement.Storage: 仓库（字符串引用）
- assetmanagement.RecycleAsset: 回收记录（字符串引用）
- assetmanagement.DamagedAsset: 待报废记录（字符串引用）
- usermanagement.Employee: 人员（字符串引用）

【场景说明】
- S1 (s1_no_record): 实物有系统无 → 创建新资产
- S2 (s2_no_outasset): 系统有无出库 → 补建出库记录
- S3 (s3_status_mismatch): 状态异常 → 修正状态
"""

import secrets
import string
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from core.models import BaseModel

if TYPE_CHECKING:
    from django.db.models import Manager


class UnregisteredAsset(BaseModel):
    """
    未登记资产管理模型

    管理不在账资产的全生命周期：发现 → 申请 → 审批 → 处理。

    【状态流转】
    pending → approved → 根据 handle_type 创建对应记录
    pending → rejected → 流程结束

    【关键字段】
    - unregistered_code: 系统自动生成的唯一编码
    - scenario_type: 场景类型（S1/S2/S3）
    - approval_status: 审批状态
    - handle_type: 处理方式（审批时确定）
    - result_*: 处理结果追踪字段

    【约束】
    - 审批通过后不可修改
    - 删除仅允许待审批状态

    Attributes:
        objects: 默认管理器（过滤已删除）
        all_objects: 完整管理器（包含已删除）
    """

    if TYPE_CHECKING:
        objects: "Manager"

    # ==========================================
    # 场景类型定义
    # ==========================================
    class ScenarioType(models.TextChoices):
        """不在账资产场景类型枚举"""
        S1_NO_RECORD = 's1_no_record', '实物有系统无'
        S2_NO_OUTASSET = 's2_no_outasset', '系统有无出库'
        S3_STATUS_MISMATCH = 's3_status_mismatch', '状态异常'

    # ==========================================
    # 处理方式定义
    # ==========================================
    class HandleType(models.TextChoices):
        """处理方式枚举"""
        CREATE_AND_RECYCLE = 'create_and_recycle', '新建资产并回收'
        CREATE_AND_DAMAGED = 'create_and_damaged', '新建资产并报废'
        SUPPLEMENT_AND_RECYCLE = 'supplement_and_recycle', '补建记录并回收'
        CORRECT_AND_RECYCLE = 'correct_and_recycle', '修正状态并回收'
        REJECT = 'reject', '拒绝处理'

    # ==========================================
    # 审批状态定义
    # ==========================================
    class ApprovalStatus(models.TextChoices):
        """审批状态枚举"""
        PENDING = 'pending', '待审批'
        APPROVED = 'approved', '已批准'
        REJECTED = 'rejected', '已拒绝'

    # ==========================================
    # 基础信息（发现时采集）
    # ==========================================
    unregistered_code = models.CharField(
        max_length=32,
        unique=True,
        verbose_name='未登记资产编码',
        help_text='系统自动生成的唯一编码，格式：UNR-YYYYMMDD-XXXXXX'
    )
    scenario_type = models.CharField(
        max_length=20,
        choices=ScenarioType.choices,
        verbose_name='场景类型',
        help_text='不在账资产的具体场景：S1实物有系统无/S2系统有无出库/S3状态异常'
    )
    discovery_date = models.DateField(
        verbose_name='发现日期',
        help_text='发现资产的日期'
    )
    discovery_location = models.CharField(
        max_length=200,
        verbose_name='发现地点',
        help_text='资产发现的具体位置'
    )
    discovery_person_jobcode = models.ForeignKey(
        'usermanagement.Employee',
        to_field='recordcode',
        on_delete=models.DO_NOTHING,
        related_name='unregistered_discovered',
        verbose_name='发现人',
        help_text='发现资产的人员工号（通过 recordcode 关联）'
    )

    # ==========================================
    # 资产信息（发现时采集）
    # ==========================================
    asset_name = models.CharField(
        max_length=100,
        verbose_name='资产名称',
        help_text='资产的名称'
    )
    asset_brand = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='资产品牌',
        help_text='资产的品牌（可选）'
    )
    asset_specification = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='资产规格',
        help_text='资产的规格型号（可选）'
    )
    asset_type_code = models.ForeignKey(
        'assetmanagement.AssetType',
        to_field='recordcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_assets',
        verbose_name='资产类型',
        help_text='资产的分类（可选，通过 recordcode 关联）'
    )
    estimated_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='预估价值',
        help_text='资产的预估价值（元，可选）'
    )

    # ==========================================
    # 关联资产（S2/S3场景使用）
    # ==========================================
    related_asset_code = models.ForeignKey(
        'assetmanagement.Asset',
        to_field='asset_recordcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_records',
        verbose_name='关联资产编码',
        help_text='系统中已存在的资产编码（S2/S3场景必填，通过 asset_recordcode 关联）'
    )

    # ==========================================
    # 处理信息（审批时确定）
    # ==========================================
    handle_type = models.CharField(
        max_length=30,
        choices=HandleType.choices,
        null=True,
        blank=True,
        verbose_name='处理方式',
        help_text='审批后选择的处理方式'
    )
    target_storage_code = models.ForeignKey(
        'assetmanagement.Storage',
        to_field='recordcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_targets',
        verbose_name='目标仓库',
        help_text='回收后存放的仓库（通过 recordcode 关联）'
    )
    handle_description = models.TextField(
        blank=True,
        null=True,
        verbose_name='处理说明',
        help_text='处理的补充说明（可选）'
    )

    # ==========================================
    # 审批信息
    # ==========================================
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        verbose_name='审批状态',
        help_text='审批的当前状态：待审批/已批准/已拒绝'
    )
    approver_jobcode = models.ForeignKey(
        'usermanagement.Employee',
        to_field='recordcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_approved',
        verbose_name='审批人',
        help_text='审批人的人员工号（通过 recordcode 关联）'
    )
    approval_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='审批日期',
        help_text='审批完成的日期'
    )
    approval_remark = models.TextField(
        blank=True,
        null=True,
        verbose_name='审批备注',
        help_text='审批的备注说明（可选）'
    )

    # ==========================================
    # 结果追踪（处理完成后填充）
    # ==========================================
    result_asset_code = models.ForeignKey(
        'assetmanagement.Asset',
        to_field='asset_recordcode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_source',
        verbose_name='结果资产编码',
        help_text='处理后创建的资产编码（通过 asset_recordcode 关联）'
    )
    result_recycle_code = models.ForeignKey(
        'assetmanagement.RecycleAsset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_source',
        verbose_name='结果回收记录',
        help_text='处理后创建的回收记录'
    )
    result_damaged_code = models.ForeignKey(
        'assetmanagement.DamagedAsset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unregistered_source',
        verbose_name='结果待报废记录',
        help_text='处理后创建的待报废记录'
    )

    # ==========================================
    # 凭证附件（JSON格式存储文件路径列表）
    # ==========================================
    attachments = models.JSONField(
        default=list,
        blank=True,
        verbose_name='附件列表',
        help_text='照片/凭证文件路径列表（JSON数组格式）'
    )

    class Meta:
        """模型元数据配置"""
        verbose_name = '未登记资产管理'
        verbose_name_plural = '未登记资产管理'
        db_table = 'am_unregistered_asset'
        ordering = ['-created_at']
        indexes = [
            # 按编码查询
            models.Index(fields=['unregistered_code']),
            # 按场景类型筛选
            models.Index(fields=['scenario_type']),
            # 按审批状态筛选
            models.Index(fields=['approval_status']),
            # 按发现人查询
            models.Index(fields=['discovery_person_jobcode']),
            # 复合索引：发现人 + 审批状态
            models.Index(fields=['discovery_person_jobcode', 'approval_status']),
        ]

    def save(self, *args, **kwargs) -> None:
        """
        保存模型实例

        自动生成未登记资产编码（如果未提供）。
        编码格式：UNR-YYYYMMDD-XXXXXX（6位随机字符）

        Args:
            *args: 位置参数
            **kwargs: 关键字参数
        """
        if not self.unregistered_code:
            self.unregistered_code = self._generate_code()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """返回模型的字符串表示"""
        return f'{self.asset_name}({self.unregistered_code})'

    @staticmethod
    def _generate_code() -> str:
        """
        生成唯一未登记资产编码

        Returns:
            str: 格式为 UNR-YYYYMMDD-XXXXXX 的唯一编码

        Example:
            >>> UnregisteredAsset._generate_code()
            'UNR-20260526-A3B7K9'
        """
        prefix = 'UNR'
        date_str = timezone.now().strftime('%Y%m%d')
        # 使用 secrets 生成安全的随机字符
        random_suffix = ''.join(
            secrets.choice(string.ascii_uppercase + string.digits)
            for _ in range(6)
        )
        return f'{prefix}-{date_str}-{random_suffix}'

    def can_modify(self) -> bool:
        """
        检查记录是否允许修改

        只有待审批状态的记录允许修改。

        Returns:
            bool: 是否允许修改
        """
        return self.approval_status == self.ApprovalStatus.PENDING

    def can_delete(self) -> bool:
        """
        检查记录是否允许删除

        只有待审批状态的记录允许删除（软删除）。

        Returns:
            bool: 是否允许删除
        """
        return self.approval_status == self.ApprovalStatus.PENDING
