"""
合同管理模型
"""

from typing import TYPE_CHECKING

from django.db import models

from core.models import BaseModel


if TYPE_CHECKING:
    from django.db.models import Manager


class Contract(BaseModel):
    """
    合同管理模型

    用于管理资产相关的采购合同、服务合同等，
    包含合同金额、付款记录、结算状态等信息。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "CONTRACT"

    CONTRACT_TYPE_CHOICES = [
        ("tender_procurement", "招标采购合同"),
        ("service", "服务合同"),
        ("information_construction", "信息化建设合同"),
        ("direct_procurement", "直接采购合同"),
    ]

    CONTRACT_STATUS_CHOICES = [
        ("purchasing", "供货中"),
        ("purchase_finished", "供货完成"),
        ("receive_check", "到货验收"),
        ("initial_check", "初步验收"),
        ("project_settlement", "结算中"),
        ("settlement_done", "结算完成"),
        ("final_check", "最终验收"),
        ("project_finished", "项目结束"),
    ]

    PROJECT_CHANGE_TYPE_CHOICES = [
        ("equipment_increase", "设备增加变更"),
        ("equipment_decrease", "设备减少变更"),
        ("model_change_only", "只涉及型号变更"),
        ("quantity_increase_with_model", "设备数量增加和型号变更"),
        ("quantity_decrease_with_model", "设备数量减少和型号变更"),
    ]

    contract_code = models.CharField(max_length=50, verbose_name="合同编号", help_text="合同唯一编码")
    contract_name = models.CharField(max_length=200, verbose_name="合同名称", help_text="合同的完整名称")
    contract_type = models.CharField(
        max_length=30,
        choices=CONTRACT_TYPE_CHOICES,
        verbose_name="合同类型",
        blank=True,
        null=True,
        help_text="合同类型：招标采购/服务/信息化建设/直接采购",
    )
    supplier_name = models.CharField(max_length=100, verbose_name="供应商名称", blank=True, null=True, help_text="供应商名称")
    contract_amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="合同总金额", blank=True, null=True, help_text="合同总金额（元）"
    )
    settlemented_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="结算价格", blank=True, null=True, help_text="最终结算金额（元）"
    )
    contract_total_quantity = models.IntegerField(verbose_name="合同总数量", blank=True, null=True, help_text="合同约定的总数量")
    contract_start_date = models.DateField(verbose_name="合同开始日期", blank=True, null=True, help_text="合同开始日期")
    contract_end_date = models.DateField(verbose_name="合同结束日期", blank=True, null=True, help_text="合同结束日期")
    contract_status = models.CharField(
        max_length=20,
        choices=CONTRACT_STATUS_CHOICES,
        default="purchasing",
        verbose_name="合同状态",
        help_text="合同状态：供货中/供货完成/到货验收/初步验收/结算中/结算完成/最终验收/项目结束",
    )
    project_change = models.BooleanField(default=False, verbose_name="项目变更", help_text="是否存在项目变更")
    project_change_type = models.CharField(
        max_length=50,
        choices=PROJECT_CHANGE_TYPE_CHOICES,
        verbose_name="变更类型",
        blank=True,
        null=True,
        help_text="变更类型：设备增加/设备减少/只涉及型号/数量增加和型号/数量减少和型号",
    )
    project_change_description = models.TextField(
        verbose_name="变更描述", blank=True, null=True, help_text="简单介绍变更内容"
    )
    receive_check_date = models.DateField(verbose_name="到货验收日期", blank=True, null=True, help_text="到货验收日期")
    initial_check_date = models.DateField(verbose_name="初步验收日期", blank=True, null=True, help_text="初步验收日期")
    final_check_date = models.DateField(verbose_name="最终验收日期", blank=True, null=True, help_text="最终验收日期")
    paid_record = models.TextField(verbose_name="支付记录", blank=True, null=True, help_text="支付记录（可存储JSON格式的支付明细）")
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="已支付金额", blank=True, null=True, help_text="已支付金额，默认为0"
    )
    amount_unpaid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="未支付金额", blank=True, null=True, help_text="未支付金额（自动计算）"
    )
    contract_description = models.TextField(verbose_name="合同描述", blank=True, null=True, help_text="补充说明")
    sort_order = models.IntegerField(default=0, verbose_name="排序", help_text="排序字段")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    class Meta:
        verbose_name = "合同管理"
        verbose_name_plural = "合同管理"
        db_table = "am_contract"
        constraints = [
            models.UniqueConstraint(
                fields=["contract_code"],
                condition=models.Q(is_deleted=False),
                name="unique_contract_code_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier_name"]),
            models.Index(fields=["contract_status"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_name}({self.contract_code})"
