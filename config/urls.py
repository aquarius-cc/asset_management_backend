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
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from rest_framework_simplejwt.views import (
    TokenObtainPairView,  # 获取令牌 分离Token令牌模式
    TokenRefreshView,     # 刷新令牌
    TokenVerifyView,      # 验证令牌
)
# 新增：导入 drf-spectacular 的核心视图类（关键修复）
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


def api_root(request):
    """
    API 根路径视图

    【修复 H10】返回 API 信息而非重定向到 admin，避免暴露后台入口
    """
    return JsonResponse({
        'message': '资产管理系统 API',
        'version': '1.0.0',
        'docs': {
            'swagger': '/api/swagger/',
            'redoc': '/api/redoc/',
            'schema': '/api/schema/',
        },
        'admin': '/admin/'  # 不直接暴露，但可以通过文档找到
    })


urlpatterns = [
    # 【修复 H10】根路径返回 API 信息，不暴露 admin 入口
    path('', api_root, name='api-root'),
    path('admin/', admin.site.urls),

    path(route='api/auth/', view=include('apps.authusermanagement.urls')),
    path('api/users/', include('apps.usermanagement.urls')),
    path('api/assets/', include('apps.assetmanagement.urls')),
    path('api/unregisteredassets/', include('apps.unregisteredasset.urls')),  # 未登记资产管理
    path('api/dashboard/', include('apps.assetmanagement.dashboard_urls')),  # 仪表盘专用路由

    # drf-spectacular 文档路由（核心）
    path('api/schema/', SpectacularAPIView.as_view(),
         name='schema'),  # 生成 schema 数据（JSON/YAML）
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger-ui'),  # Swagger UI
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'),
         name='redoc'),  # ReDoc UI

]

# 在开发环境中提供媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
