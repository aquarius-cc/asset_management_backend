"""
通知 API 视图

提供通知的 CRUD 操作：
- GET /api/notifications/ — 获取当前用户通知列表
- GET /api/notifications/unread-count/ — 获取未读数量
- POST /api/notifications/<id>/read/ — 标记已读
- POST /api/notifications/read-all/ — 全部标记已读
"""

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from apps.notification.models import Notification
from utils.response_utils import success_response, error_response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notification_list(request: Request) -> Response:
    """获取当前用户的通知列表"""
    jobcode = request.user.auth_id
    is_read = request.query_params.get("is_read")
    limit = int(request.query_params.get("limit", 20))

    queryset = Notification.objects.filter(recipient_jobcode=jobcode)

    if is_read is not None:
        queryset = queryset.filter(is_read=is_read.lower() == "true")

    notifications = queryset[:limit]

    data = [
        {
            "id": n.id,
            "type": n.notification_type,
            "title": n.title,
            "message": n.message,
            "priority": n.priority,
            "is_read": n.is_read,
            "related_asset_code": n.related_asset_code,
            "related_url": n.related_url,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]

    return success_response(data=data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def unread_count(request: Request) -> Response:
    """获取当前用户未读通知数量"""
    jobcode = request.user.auth_id
    count = Notification.objects.filter(
        recipient_jobcode=jobcode, is_read=False
    ).count()
    return success_response(data={"count": count})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def mark_read(request: Request, notification_id: int) -> Response:
    """标记单条通知为已读"""
    jobcode = request.user.auth_id
    try:
        notification = Notification.objects.get(
            id=notification_id, recipient_jobcode=jobcode
        )
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return success_response(message="已标记为已读")
    except Notification.DoesNotExist:
        return error_response(message="通知不存在", status_code=404)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def mark_all_read(request: Request) -> Response:
    """将当前用户所有未读通知标记为已读"""
    jobcode = request.user.auth_id
    count = Notification.objects.filter(
        recipient_jobcode=jobcode, is_read=False
    ).update(is_read=True)
    return success_response(data={"marked_count": count})
