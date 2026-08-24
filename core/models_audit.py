"""
通用审计日志模型

用于记录非资产操作的审计日志(部门、员工、用户、未登记资产等)。
与 AssetOperationLog 结构一致,但不关联 Asset 模型。
"""

from typing import Any

from django.db import models


class AuditLog(models.Model):
    """
    通用审计日志表(只读)

    记录所有非资产操作的审计信息,结构与 AssetOperationLog 一致。
    用于:部门增删改、员工增删改、用户注册/登录/权限变更、未登记资产审批。
    """

    OPERATION_TYPE_CHOICES = [
        ("create", "创建"),
        ("update", "更新"),
        ("delete", "删除"),
        ("approve", "审批"),
        ("login", "登录"),
        ("logout", "登出"),
        ("permission_change", "权限变更"),
        ("state_change", "状态变更"),
    ]

    record_code = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="记录编码",
        help_text="被操作记录的唯一编码(如部门编码、员工工号、用户名等)",
    )
    app_label = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="应用标识",
        help_text="操作所属的应用(如 department、employee、authuser)",
    )
    operation_type = models.CharField(
        max_length=20, choices=OPERATION_TYPE_CHOICES, verbose_name="操作类型", db_index=True
    )
    logging_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="日志记录ID",
        blank=True,
        help_text="系统自动生成的日志记录唯一标识",
    )
    operation_time = models.DateTimeField(auto_now_add=True, verbose_name="操作时间", db_index=True)
    operator_jobcode = models.CharField(max_length=20, verbose_name="操作人工号", blank=True, null=True)
    operator_name = models.CharField(max_length=100, verbose_name="操作人姓名", blank=True, null=True)
    before_data = models.JSONField(verbose_name="变更前数据", blank=True, null=True)
    after_data = models.JSONField(verbose_name="变更后数据", blank=True, null=True)
    description = models.TextField(verbose_name="操作描述")
    ip_address = models.GenericIPAddressField(verbose_name="操作IP地址", blank=True, null=True)

    class Meta:
        verbose_name = "通用审计日志"
        verbose_name_plural = "通用审计日志"
        db_table = "core_audit_log"
        ordering = ["-operation_time"]
        indexes = [
            models.Index(fields=["record_code", "-operation_time"]),
            models.Index(fields=["app_label", "operation_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.app_label}-{self.operation_type}-{self.record_code}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk:
            raise PermissionError("审计日志是只读表,禁止修改已有记录")
        if not self.logging_id:
            import secrets
            import string

            chars = string.ascii_uppercase + string.digits
            suffix = "".join(secrets.choice(chars) for _ in range(8))
            from django.utils import timezone

            date_str = timezone.now().strftime("%Y%m%d")
            self.logging_id = f"{self.operation_type}-Log-{date_str}-{suffix}"
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        raise PermissionError("审计日志是只读表,禁止删除记录")
