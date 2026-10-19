"""
通知 API 视图

提供通知的 CRUD 操作:
- GET /api/notifications/ — 获取当前用户通知列表
- GET /api/notifications/unread-count/ — 获取未读数量
- POST /api/notifications/<id>/read/ — 标记已读
- POST /api/notifications/read-all/ — 全部标记已读
"""

from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notification.models import Notification
from apps.notification.selectors import NotificationSelector
from apps.notification.serializers import NotificationSerializer
from core.pagination import CustomPageNumberPagination
from utils.response_utils import error_response, success_response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notification_list(request: Request) -> Response:
    """获取当前用户通知列表(分页信封, P1-02 重构)"""
    jobcode = request.user.auth_username  # type: ignore[union-attr]
    queryset = NotificationSelector.list_for_user(
        jobcode,
        is_read=request.query_params.get("is_read"),
        notification_type=request.query_params.get("notification_type"),
        priority=request.query_params.get("priority"),
        keyword=request.query_params.get("keyword"),
    )

    # 统一分页格式: data 为 {count,total_pages,page,page_size,next,previous,results}
    # (内部已含 success_response 单层信封, 禁止二次包装)
    paginator = CustomPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)

    if page is not None:
        data = [NotificationSerializer(notification).data for notification in page]
        return paginator.get_paginated_response(data)  # type: ignore[no-any-return]

    # CustomPageNumberPagination 强制分页, 此分支恒不可达(与 operation_log_views 同构兜底)
    data = [NotificationSerializer(notification).data for notification in queryset]
    return success_response(data=data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def unread_count(request: Request) -> Response:
    """获取当前用户未读通知数量"""
    jobcode = request.user.auth_username  # type: ignore[union-attr]
    count = Notification.objects.filter(recipient_jobcode=jobcode, is_read=False).count()
    return success_response(data={"count": count})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def mark_read(request: Request, notification_id: int) -> Response:
    """标记单条通知为已读"""
    jobcode = request.user.auth_username  # type: ignore[union-attr]
    try:
        notification = Notification.objects.get(id=notification_id, recipient_jobcode=jobcode)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return success_response(message="已标记为已读")
    except Notification.DoesNotExist:
        return error_response(message="通知不存在", status_code=404)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def mark_all_read(request: Request) -> Response:
    """将当前用户所有未读通知标记为已读"""
    jobcode = request.user.auth_username  # type: ignore[union-attr]
    count = Notification.objects.filter(recipient_jobcode=jobcode, is_read=False).update(is_read=True)
    return success_response(data={"marked_count": count})
