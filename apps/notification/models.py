"""
通知模型

存储系统通知(审批通知、状态变更通知等)
支持 WebSocket 实时推送 + 持久化存储
"""

from django.db import models


class Notification(models.Model):
    """系统通知"""

    class NotificationType(models.TextChoices):
        APPROVAL = "approval", "审批通知"
        STATUS_CHANGE = "status_change", "状态变更"
        SYSTEM = "system", "系统通知"

    class Priority(models.TextChoices):
        LOW = "low", "低"
        MEDIUM = "medium", "中"
        HIGH = "high", "高"

    recipient_jobcode = models.CharField(
        max_length=50,
        verbose_name="接收人工号",
        help_text="通知接收人的 employee_jobcode",
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        verbose_name="通知类型",
    )
    title = models.CharField(max_length=200, verbose_name="通知标题")
    message = models.TextField(verbose_name="通知内容")
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        verbose_name="优先级",
    )
    is_read = models.BooleanField(default=False, verbose_name="已读")
    related_asset_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="关联资产编码",
    )
    related_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="关联页面路径",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间", help_text="记录创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间", help_text="最后修改时间")
    recordcode = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name="记录编码",
        help_text="后端生成的全局唯一编码,用于外键引用",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用", help_text="控制记录是否激活")
    is_deleted = models.BooleanField(default=False, verbose_name="是否删除", help_text="软删除标记")

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = "通知"
        db_table = "am_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_jobcode", "is_read"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title}"
