"""
用户管理URL配置

路由:
  - departments / employees: 部门与员工管理
  - roles / permissions: 角色与权限点管理(只读)
  - users/<user_id>/roles: 用户角色分配(嵌套路由)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.usermanagement.views import (
    DepartmentViewSet,
    EmployeeViewSet,
    PermissionViewSet,
    RoleViewSet,
    UserRoleViewSet,
)


router = DefaultRouter()
router.register(prefix="departments", viewset=DepartmentViewSet, basename="departments")
router.register(prefix="employees", viewset=EmployeeViewSet, basename="employees")
router.register(prefix="roles", viewset=RoleViewSet, basename="roles")
router.register(prefix="permissions", viewset=PermissionViewSet, basename="permissions")
router.register(
    prefix=r"(?P<user_id>[^/.]+)/roles",
    viewset=UserRoleViewSet,
    basename="user-roles",
)


urlpatterns = [
    path("", include(router.urls)),
]
