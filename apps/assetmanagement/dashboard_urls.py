"""
仪表盘专用URL配置
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DashboardViewSet

router = DefaultRouter()
router.register(prefix='', viewset=DashboardViewSet, basename='dashboard')

urlpatterns = [
    path('', include(router.urls)),
]