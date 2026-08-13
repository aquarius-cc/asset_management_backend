"""
资产操作记录模型 & 资产状态变更日志模型
"""

import secrets
import string
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from apps.assetmanagement.models.asset import Asset
from apps.usermanagement.models import Employee
from core.models import BaseModel


if TYPE_CHECKING:
    from django.db.models import Manager


# ==================== AssetStateLog(需求定义的状态变更日志) ====================


class AssetStateLog(BaseModel):
    """
    资产状态变更日志(需求 §15)

    记录资产状态的每次变更,仅供审计查询,不可修改、不可删除。
    """

    RECORDCODE_PREFIX = "STATELOG"

    asset_recordcode = models.ForeignKey(
        Asset,
        to_field="recordcode",
        on_delete=models.PROTECT,
        related_name="state_logs",
        verbose_name="关联资产",
        help_text="关联的资产唯一标识码",
    )
    from_state = models.CharField(
        max_length=20,
        choices=Asset.AssetStatus.choices,
        verbose_name="变更前状态",
        help_text="变更前的资产状态",
    )
    to_state = models.CharField(
        max_length=20,
        choices=Asset.AssetStatus.choices,
        verbose_name="变更后状态",
        help_text="变更后的资产状态",
    )
    operator_employee = models.ForeignKey(
        Employee,
        to_field="recordcode",
        on_delete=models.SET_NULL,
        related_name="state_logs_operator",
        null=True,
        blank=True,
        verbose_name="操作人",
        help_text="执行状态变更的操作人",
    )
    business_doc_no = models.CharField(
        max_length=128, blank=True, default="", verbose_name="关联业务单据号", help_text="关联的业务单据号"
    )
    reason = models.TextField(blank=True, default="", verbose_name="变更原因", help_text="状态变更的原因说明")
    version = models.IntegerField(default=1, verbose_name="版本号", help_text="乐观锁版本号")

    class Meta:
        verbose_name = "资产状态变更日志"
        verbose_name_plural = "资产状态变更日志"
        db_table = "am_asset_state_log"
        indexes = [
            models.Index(fields=["asset_recordcode"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self) -> str:
        return f"状态变更-{self.asset_recordcode}:{self.from_state}→{self.to_state}"


# ==================== AssetOperationLog(原有操作记录,保留兼容) ====================


class AssetOperationLog(models.Model):
    """
    资产操作记录表(只读)

    记录资产全生命周期中的所有操作。
    此表数据只增不改,业务逻辑中禁止调用 save() 更新或 delete() 删除。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    class OperationType(models.TextChoices):
        """操作类型"""

        CREATE = "create", "创建"
        UPDATE = "update", "更新"
        DELETE = "delete", "删除"
        OUT = "out", "出库"
        RECYCLE = "recycle", "回收"
        BROKEN = "broken", "已损坏"
        LOST = "lost", "已遗失"
        FOUND = "found", "找回"
        DAMAGED = "damaged", "待报废"
        WASTE = "waste", "已报废"
        REPAIR = "repair", "送修"
        REPAIR_DONE = "repair_done", "维修完成"
        REPAIR_FAILED = "repair_failed", "维修失败"
        APPROVE = "approve", "审批"
        TRANSFER = "transfer", "转移"
        STATE_CHANGE = "state_change", "状态变更"

    # 向后兼容
    OPERATION_TYPE_CHOICES = OperationType.choices

    asset_code = models.CharField(max_length=64, verbose_name="资产编码", db_index=True, help_text="关联的资产编码")
    asset_name = models.CharField(
        max_length=100, verbose_name="资产名称", null=True, blank=True, help_text="资产名称(冗余存储)"
    )
    asset_specification = models.CharField(
        max_length=100, verbose_name="资产规格", null=True, blank=True, help_text="资产规格(冗余存储)"
    )
    operation_type = models.CharField(
        max_length=20, choices=OperationType.choices, verbose_name="操作类型", db_index=True, help_text="操作类型"
    )
    logging_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="日志记录ID",
        blank=True,
        help_text="系统自动生成的日志记录唯一标识",
    )
    operation_time = models.DateTimeField(
        auto_now_add=True, verbose_name="操作时间", db_index=True, help_text="操作执行的时间"
    )
    operator_jobcode = models.CharField(
        max_length=20, verbose_name="操作人工号", blank=True, null=True, help_text="执行操作的人员工号"
    )
    operator_name = models.CharField(
        max_length=100, verbose_name="操作人姓名", blank=True, null=True, help_text="执行操作的人员姓名"
    )
    before_data = models.JSONField(
        verbose_name="变更前数据", blank=True, null=True, help_text="操作前的资产数据(JSON格式)"
    )
    after_data = models.JSONField(
        verbose_name="变更后数据", blank=True, null=True, help_text="操作后的资产数据(JSON格式)"
    )
    description = models.TextField(verbose_name="操作描述", help_text="操作的详细描述")
    related_record_code = models.CharField(
        max_length=50, verbose_name="关联记录编码", blank=True, null=True, help_text="关联的业务记录编码"
    )
    related_record_type = models.CharField(
        max_length=20, verbose_name="关联记录类型", blank=True, null=True, help_text="关联记录的类型"
    )
    ip_address = models.GenericIPAddressField(
        verbose_name="操作IP地址", blank=True, null=True, help_text="执行操作的IP地址"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = "资产操作记录"
        verbose_name_plural = "资产操作记录"
        db_table = "am_asset_operation_log"
        ordering = ["-operation_time"]
        indexes = [
            models.Index(fields=["asset_code", "-operation_time"]),
            models.Index(fields=["operation_type", "-operation_time"]),
            models.Index(fields=["operator_jobcode", "-operation_time"]),
            models.Index(fields=["asset_code", "operation_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.asset_code}-{self.get_operation_type_display()}-{self.operation_time.strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def _generate_random_suffix(length: int = 8) -> str:
        """生成随机后缀字符"""
        chars = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(chars) for _ in range(length))

    def save(self, *args, **kwargs) -> None:
        """阻止更新已有记录,创建时自动生成 logging_id"""
        if self.pk:
            raise PermissionError("AssetOperationLog 是只读表,禁止修改已有记录。")
        if not self.logging_id:
            op_time = self.operation_time or timezone.now()
            date_str = op_time.strftime("%Y%m%d")
            random_suffix = self._generate_random_suffix()
            self.logging_id = f"{self.operation_type}-Log-{date_str}-{random_suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        """阻止删除记录"""
        raise PermissionError("AssetOperationLog 是只读表,禁止删除记录。")
