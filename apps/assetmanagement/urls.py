"""
资产管理URL配置
"""
from django.urls.resolvers import URLPattern, URLResolver


from django.urls import path, include
from rest_framework.routers import DefaultRouter

# 【修正】从 views.py 导入主要视图（不是 views/ 包）
from .views import (
    StorageViewSet, AssetTypeViewSet,
    ContractViewSet, AssetViewSet, OutAssetViewSet,
    RecycleAssetViewSet, DamagedAssetViewSet, WasteAssetViewSet,
    HardDiskSNViewSet
)

# 【修正】从 operation_log_views.py 导入操作日志视图（与 views.py 同级）
from .operation_log_views import (
    AssetOperationLogListView,
    AssetOperationLogDetailView,
    AssetOperationLogByLoggingIdView,
    AssetHistoryView,
    AssetStatusTimelineView,
    RecentOperationsView,
    UserOperationsView,
)

router: DefaultRouter = DefaultRouter()
router.register(prefix='storages', viewset=StorageViewSet, basename='storages')
router.register(prefix='asset-types', viewset=AssetTypeViewSet,
                basename='asset-types')
# router.register(prefix='asset-classifications', viewset=AssetClassificationViewSet, basename='asset-classifications')
router.register(prefix='contracts', viewset=ContractViewSet,
                basename='contracts')
router.register(prefix='assets', viewset=AssetViewSet, basename='assets')
# router.register(prefix='create', viewset=AssetViewSet, basename='create')
router.register(prefix='out-assets', viewset=OutAssetViewSet,
                basename='out-assets')
router.register(prefix='recycle-assets',
                viewset=RecycleAssetViewSet, basename='recycle-assets')
router.register(prefix='damaged-assets',
                viewset=DamagedAssetViewSet, basename='damaged-assets')
router.register(prefix='waste-assets',
                viewset=WasteAssetViewSet, basename='waste-assets')
router.register(prefix='harddisk-sn',
                viewset=HardDiskSNViewSet, basename='harddisk-sn')
# DashboardViewSet 已在 dashboard_urls.py 中单独配置

urlpatterns: list[URLResolver | URLPattern] = [
    path(route='', view=include(arg=router.urls)),
    # path('api/', include(router.urls)),  # 最终路由：/api/assets/contracts/{pk}/
    
    # ========== 资产操作记录API（只读）==========
    # 【AGENTS 规范 - 架构优化】新增操作记录查询接口
    path('operation-logs/by-logging-id/<str:logging_id>/', AssetOperationLogByLoggingIdView.as_view(), name='operation-log-by-logging-id'),
    path('operation-logs/', AssetOperationLogListView.as_view(), name='operation-log-list'),
    path('operation-logs/<int:pk>/', AssetOperationLogDetailView.as_view(), name='operation-log-detail'),
    path('operation-logs/recent/', RecentOperationsView.as_view(), name='operation-log-recent'),
    path('operation-logs/user/<str:operator_jobcode>/', UserOperationsView.as_view(), name='operation-log-user'),
    path('assets/<str:asset_code>/history/', AssetHistoryView.as_view(), name='asset-history'),
    path('assets/<str:asset_code>/timeline/', AssetStatusTimelineView.as_view(), name='asset-timeline'),
]

'''
在 Django REST Framework 中，当你使用router.register(prefix='assets', viewset=AssetViewSet, basename='assets')注册视图集时，路由会自动映射到AssetViewSet中的标准方法，遵循 RESTful API 的设计规范。
映射关系如下：
HTTP方法	          URL路径	                对应iewSet方法	           功能描述
GET	                /assets/	                 list()	                获取资源列表
POST	            /assets/	                 create()	            创建新资源
GET	                /assets/{id}/	             retrieve()	            获取单个资源详情
PUT	                /assets/{id}/	             update()	            全量更新资源
PATCH	            /assets/{id}/	             partial_update()	    部分更新资源
DELETE	            /assets/{id}/	             destroy()	            删除资源
这些方法都是ViewSet提供的默认动作，你可以在AssetViewSet中重写这些方法来实现自定义逻辑，例如
from rest_framework import viewsets
from .models import Asset
from .serializers import AssetSerializer
class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer
    
    # 重写list方法，自定义列表查询逻辑
    def list(self, request, *args, **kwargs):
        # 自定义逻辑
        return super().list(request, *args, **kwargs)
    
    # 重写create方法，自定义创建逻辑
    def create(self, request, *args, **kwargs):
        # 自定义逻辑
        return super().create(request, *args, **kwargs)

如果你需要添加额外的自定义动作，可以使用@action装饰器，例如：
from rest_framework.decorators import action
from rest_framework.response import Response

class AssetViewSet(viewsets.ModelViewSet):
    # ... 其他代码 ...    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        asset = self.get_object()
        asset.is_active = True
        asset.save()
        return Response({'status': 'asset activated'})
这个自定义动作会映射到POST /assets/{id}/activate/路径。
'''
