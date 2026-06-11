"""
用户管理URL配置
"""
from django.urls import path, include, URLPattern, URLResolver
from rest_framework.routers import DefaultRouter
from .views import (
    AuthUserViewSet,
    RegisterAPIView,
    LoginAPIView,
    UserProfileAPIView,
    LogoutAPIView,  # 【新增】退出登录视图
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

router = DefaultRouter()
router.register('users', AuthUserViewSet, basename='users')

urlpatterns: list[URLResolver | URLPattern] = [
    path('', include(router.urls)),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('login/', LoginAPIView.as_view(), name='login'),
        path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('profile/', UserProfileAPIView.as_view(), name='user_profile'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]
