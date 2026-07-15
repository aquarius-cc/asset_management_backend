"""
用户管理URL配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.usermanagement.views import DepartmentViewSet, EmployeeViewSet


router = DefaultRouter()
router.register(prefix="departments", viewset=DepartmentViewSet, basename="departments")
router.register(prefix="employees", viewset=EmployeeViewSet, basename="employees")

urlpatterns = [
    path("", include(router.urls)),
]
