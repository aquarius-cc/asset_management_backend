"""
通知 API 路由
"""

from django.urls import path

from apps.notification import views


urlpatterns = [
    path("", views.notification_list, name="notification-list"),
    path("unread-count/", views.unread_count, name="notification-unread-count"),
    path("<int:notification_id>/read/", views.mark_read, name="notification-mark-read"),
    path("read-all/", views.mark_all_read, name="notification-mark-all-read"),
]
