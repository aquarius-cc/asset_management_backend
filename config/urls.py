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

from typing import Any

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from core.metrics import metrics_view


def api_root(request: Any) -> JsonResponse:
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


def health_check(request: Any) -> JsonResponse:
    """
    健康检查接口(OC-6 落地)

    检查数据库和 Redis 连接状态。
    所有依赖健康 → 200, 任一不健康 → 503
    """
    import os

    from django.db import connection

    checks = {}

    # 数据库检查
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"

    # Redis 检查 (WebSocket 通道层关键依赖)
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "")
        with redis.Redis.from_url(redis_url, socket_timeout=3) as conn:
            conn.ping()
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    is_healthy = all(v == "healthy" for v in checks.values())

    return JsonResponse(
        {
            "status": "healthy" if is_healthy else "unhealthy",
            "checks": checks,
            "version": "1.0.0",
        },
        status=200 if is_healthy else 503,
    )


def ready_check(request: Any) -> JsonResponse:
    """
    就绪检查接口(OC-6 落地)

    检查服务是否可以接受请求。
    数据库和 Redis 均连接 → 200, 任一不可用 → 503
    安全要求(H-3)：不向未认证请求暴露数据库错误详情。
    """
    import logging
    import os

    from django.db import connection

    logger = logging.getLogger("health")
    checks = {}

    # 数据库检查
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = "unavailable"
        logger.warning(" readiness check failed (db): %s", e, exc_info=True)

    # Redis 检查
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "")
        with redis.Redis.from_url(redis_url, socket_timeout=3) as conn:
            conn.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = "unavailable"
        logger.warning(" readiness check failed (redis): %s", e, exc_info=True)

    is_ready = all(v == "connected" for v in checks.values())

    return JsonResponse(
        {
            "status": "ready" if is_ready else "not_ready",
            "service": "asset-management-backend",
            "checks": checks,
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
    # Prometheus 指标端点(OC-4 落地) — 无认证,供 Prometheus 内部抓取
    path("metrics/", metrics_view, name="metrics"),
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
]

# 在开发环境中提供媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
