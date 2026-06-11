"""
未登记资产 URL 配置

该模块定义未登记资产应用的 URL 路由。

【AGENTS 规范 - URL 配置】
- 使用 DRF 的 DefaultRouter 自动生成路由
- URL 前缀使用 kebab-case（短横线连接）
- 版本控制：/api/v1/unregistered-assets/

【路由列表】
- GET    /api/v1/unregistered-assets/          list
- POST   /api/v1/unregistered-assets/          create
- GET    /api/v1/unregistered-assets/{code}/   retrieve
- PUT    /api/v1/unregistered-assets/{code}/   update
- DELETE /api/v1/unregistered-assets/{code}/   destroy
- POST   /api/v1/unregistered-assets/{code}/approve/  approve
"""

from rest_framework.routers import DefaultRouter

from .views import UnregisteredAssetViewSet


app_name = 'unregisteredasset'

# 创建路由器
router = DefaultRouter()

# 注册视图集
# lookup 参数指定 URL 中的参数名，这里使用 unregistered_code 作为 lookup field
router.register(
    r'unregistered-assets',
    UnregisteredAssetViewSet,
    basename='unregisteredasset'
)

# URL 模式
urlpatterns = router.urls
