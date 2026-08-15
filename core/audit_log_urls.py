"""
通用审计日志 URL 配置

提供通用审计日志的只读查询 API 路由。
"""

from django.urls import path

from core.audit_log_views import (
    AuditLogByLoggingIdView,
    AuditLogDetailView,
    AuditLogListView,
    AuditLogsByAppLabelView,
    AuditLogsByOperatorView,
    RecentAuditLogsView,
)


urlpatterns = [
    path("audit-logs/", AuditLogListView.as_view(), name="audit-log-list"),
    path("audit-logs/<int:pk>/", AuditLogDetailView.as_view(), name="audit-log-detail"),
    path(
        "audit-logs/by-logging-id/<str:logging_id>/", AuditLogByLoggingIdView.as_view(), name="audit-log-by-logging-id"
    ),
    path("audit-logs/recent/", RecentAuditLogsView.as_view(), name="audit-log-recent"),
    path("audit-logs/by-app/<str:app_label>/", AuditLogsByAppLabelView.as_view(), name="audit-log-by-app"),
    path(
        "audit-logs/by-operator/<str:operator_jobcode>/",
        AuditLogsByOperatorView.as_view(),
        name="audit-log-by-operator",
    ),
]
