"""
用户管理URL配置
"""

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenVerifyView,
)

from apps.authusermanagement.my_permissions_view import MyPermissionsAPIView
from apps.authusermanagement.views import (
    AuthUserViewSet,
    LoginAPIView,
    LogoutAPIView,
    RBACTokenRefreshView,
    RegisterAPIView,
    UserProfileAPIView,
)


router = DefaultRouter()
# 【修复】仅注册 list/retrieve/update/delete 操作,create 使用独立的 RegisterAPIView
router.register("users", AuthUserViewSet, basename="users")

urlpatterns: list[URLResolver | URLPattern] = [
    path("", include(router.urls)),
    # 认证相关端点
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("profile/", UserProfileAPIView.as_view(), name="user_profile"),
    path("my-permissions/", MyPermissionsAPIView.as_view(), name="my_permissions"),
    # Token 刷新和验证(RBAC 版刷新:重新注入 role + department_code)
    path("token/refresh/", RBACTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
]
