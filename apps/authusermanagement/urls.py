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
# DefaultRouter 注册全部 ModelViewSet 动作。create 为自助注册路径(AllowAny +
# RegisterSerializer 过滤敏感字段 + RegisterRateThrottle 5/min,与 /auth/register/
# 同口径);管理端建用户走同一端点(前端 AuthUserManage -> POST /auth/users/)。
# P2-03 修复前本注释误称「仅注册 list/retrieve/update/delete」,与实现不符。
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
