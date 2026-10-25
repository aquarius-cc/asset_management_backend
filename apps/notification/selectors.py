"""
通知查询选择器

本模块封装通知列表的查询过滤逻辑,遵循 Selector 层职责:
- 只做数据查询(过滤/排序),不涉及业务判断与数据修改

符合 AGENTS 架构分层铁律 - Selector 层(查询唯一收敛, DR-3)

使用方式:
    from apps.notification.selectors import NotificationSelector

    qs = NotificationSelector.list_for_user(
        "EMP020",
        is_read="true",
        notification_type="system",
        priority="high",
        keyword="资产",
    )
"""

from django.db.models import Q, QuerySet

from apps.notification.models import Notification


class NotificationSelector:
    """
    通知查询选择器

    查询方法:
    - list_for_user(): 按接收人工号查询通知列表(支持筛选)

    参数说明:
    - recipient_jobcode: 接收人工号(登录身份 auth_username)
    - is_read: 原始查询串, "true"(忽略大小写)视为已读筛选, 其余值视为未读
      (与 P1-02 重构前 View 层行为逐字一致)
    - notification_type / priority: 精确匹配, 空值跳过
    - keyword: 标题/内容模糊匹配, 空串跳过
    - 排序由 Notification.Meta.ordering(["-created_at"]) 兜底, 分页结果稳定

    Example:
        >>> from apps.notification.selectors import NotificationSelector
        >>> qs = NotificationSelector.list_for_user("EMP020", is_read="true")
    """

    @staticmethod
    def list_for_user(
        recipient_jobcode: str,
        *,
        is_read: str | None = None,
        notification_type: str | None = None,
        priority: str | None = None,
        keyword: str | None = None,
    ) -> QuerySet[Notification]:
        """按接收人过滤通知列表(惰性 QuerySet, 不物化)"""
        queryset = Notification.objects.filter(recipient_jobcode=recipient_jobcode, is_deleted=False)

        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == "true")

        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)

        if priority:
            queryset = queryset.filter(priority=priority)

        if keyword:
            title_match = Q(title__icontains=keyword)
            message_match = Q(message__icontains=keyword)
            queryset = queryset.filter(title_match | message_match)

        return queryset

    @staticmethod
    def get_for_user(recipient_jobcode: str, notification_id: int) -> Notification | None:
        """按接收人取单条未删通知(不存在或已软删返回 None)"""
        return (
            Notification.objects.filter(
                recipient_jobcode=recipient_jobcode,
                id=notification_id,
                is_deleted=False,
            )
            .first()
        )
