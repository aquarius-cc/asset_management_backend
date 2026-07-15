"""
仪表盘专用URL配置

【AGENTS 规范】使用 SimpleRouter 替代 DefaultRouter，
避免自动生成标准 CRUD 路由（list/create/retrieve 等），
DashboardViewSet 仅使用 @action 自定义路由。
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.assetmanagement.views import DashboardViewSet


router = SimpleRouter()
router.register(prefix="", viewset=DashboardViewSet, basename="dashboard")

urlpatterns = [
    path("", include(router.urls)),
]
