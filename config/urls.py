"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

# 新增:导入 drf-spectacular 的核心视图类(关键修复)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def api_root(request):
    """
    API 根路径视图

    【修复 H10】返回 API 信息而非重定向到 admin,避免暴露后台入口
    """
    return JsonResponse(
        {
            "message": "资产管理系统 API",
            "version": "1.0.0",
            "docs": {
                "swagger": "/api/v1/swagger/",
                "redoc": "/api/v1/redoc/",
                "schema": "/api/v1/schema/",
            },
            "admin": "/admin/",
        }
    )


def health_check(request):
    """
    健康检查接口(OC-6 落地)

    用于监控系统状态,检查数据库连接是否正常。
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return JsonResponse(
        {
            "status": "ok",
            "database": db_status,
            "version": "1.0.0",
        }
    )


def ready_check(request):
    """
    就绪检查接口(OC-6 落地)

    检查服务是否可以接受请求。
    用于 Kubernetes readiness probe 和监控系统。
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e!s}"

    is_ready = db_status == "connected"

    return JsonResponse(
        {
            "status": "ready" if is_ready else "not_ready",
            "service": "asset-management-backend",
            "checks": {
                "database": db_status,
            },
        },
        status=200 if is_ready else 503,
    )


urlpatterns = [
    # 【修复 H10】根路径返回 API 信息,不暴露 admin 入口
    path("", api_root, name="api-root"),
    path("admin/", admin.site.urls),
    # 健康检查接口(OC-6 落地)
    path("health/", health_check, name="health-check"),
    path("ready/", ready_check, name="ready-check"),
    # ==================== API v1 路由(主路径) ====================
    path("api/v1/auth/", include("apps.authusermanagement.urls")),
    path("api/v1/users/", include("apps.usermanagement.urls")),
    path("api/v1/assets/", include("apps.assetmanagement.urls")),
    path("api/v1/unregisteredassets/", include("apps.unregisteredasset.urls")),
    path("api/v1/dashboard/", include("apps.assetmanagement.dashboard_urls")),
    path("api/v1/", include("core.audit_log_urls")),
    path("api/v1/notifications/", include("apps.notification.urls")),
    # ==================== API v1 文档路由 ====================
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema-v1"),
    path("api/v1/swagger/", SpectacularSwaggerView.as_view(url_name="schema-v1"), name="swagger-ui-v1"),
    path("api/v1/redoc/", SpectacularRedocView.as_view(url_name="schema-v1"), name="redoc-v1"),
    # ==================== 向后兼容:旧 /api/ 前缀(保留过渡期) ====================
    path("api/auth/", include("apps.authusermanagement.urls")),
    path("api/users/", include("apps.usermanagement.urls")),
    path("api/assets/", include("apps.assetmanagement.urls")),
    path("api/unregisteredassets/", include("apps.unregisteredasset.urls")),
    path("api/dashboard/", include("apps.assetmanagement.dashboard_urls")),
    path("api/", include("core.audit_log_urls")),
    path("api/notifications/", include("apps.notification.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# 在开发环境中提供媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
