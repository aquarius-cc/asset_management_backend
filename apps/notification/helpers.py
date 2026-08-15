"""
通知路由辅助函数

根据资产归属部门,查找所有 dept_manager 并发送通知。
"""

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.notification.service import send_notification_sync


if TYPE_CHECKING:
    from apps.assetmanagement.models import Asset


logger = logging.getLogger(__name__)


def notify_dept_managers(
    asset: "Asset",
    notification_type: str,
    title: str,
    message: str,
    priority: str = "medium",
    related_url: str | None = None,
) -> None:
    """
    向资产所属部门的所有 dept_manager 发送通知。

    Args:
        asset: 资产实例
        notification_type: 通知类型(approval/status_change/system)
        title: 通知标题
        message: 通知内容
        priority: 优先级(low/medium/high)
        related_url: 关联页面路径
    """
    from apps.usermanagement.models import Employee
    from core.department_scope import resolve_asset_department_codes

    dept_codes = resolve_asset_department_codes(asset)
    if not dept_codes:
        # 无法归属部门,仅通知操作人(由调用方处理)
        return

    # 查找该部门的所有 dept_manager
    managers = Employee.objects.filter(
        employee_department__department_code__in=dept_codes,
        role="dept_manager",
        employee_status="active",
        is_deleted=False,
    ).values_list("employee_jobcode", flat=True)

    for jobcode in managers:
        try:
            send_notification_sync(
                recipient_jobcode=jobcode,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                related_asset_code=asset.asset_code,
                related_url=related_url,
            )
        except Exception as e:
            logger.warning(f"通知发送失败 (to={jobcode}): {e}")


def send_notification_on_commit(
    asset: "Asset",
    notification_type: str,
    title: str,
    message: str,
    priority: str = "medium",
    related_url: str | None = None,
) -> None:
    """
    事务提交后向资产归属部门经理发送通知(B6)。

    必须与 @transaction.atomic 配合使用:将通知注册到 on_commit,
    确保数据提交成功后才推送,避免事务回滚导致误报。

    Args:
        asset: 资产实例
        notification_type: 通知类型(approval/status_change/system)
        title: 通知标题
        message: 通知内容
        priority: 优先级(low/medium/high)
        related_url: 关联页面路径
    """
    transaction.on_commit(
        lambda: notify_dept_managers(
            asset=asset,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            related_url=related_url,
        )
    )
