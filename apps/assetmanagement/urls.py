"""
资产管理URL配置
"""

from django.urls import include, path
from django.urls.resolvers import URLPattern, URLResolver
from rest_framework.routers import DefaultRouter

# 从 views/ 包导入主要视图
from apps.assetmanagement.views import (
    AssetGroupChildrenViewSet,
    AssetGroupedViewSet,
    AssetTypeViewSet,
    AssetViewSet,
    BrokenAssetViewSet,
    ContractViewSet,
    DamagedAssetViewSet,
    FoundAssetViewSet,
    HardDiskSNViewSet,
    LostAssetViewSet,
    OutAssetViewSet,
    RecycleAssetViewSet,
    RepairAssetViewSet,
    StorageViewSet,
    WasteAssetViewSet,
)

# 从 views/operation_log_views.py 导入操作日志视图
from apps.assetmanagement.views.operation_log_views import (
    AssetHistoryView,
    AssetOperationLogByLoggingIdView,
    AssetOperationLogDetailView,
    AssetOperationLogExportView,
    AssetOperationLogListView,
    AssetStatusTimelineView,
    RecentOperationsView,
    UserOperationsView,
)

# 公开扫码接口(无需认证)
from apps.assetmanagement.views.public_scan_view import public_scan_view


router: DefaultRouter = DefaultRouter()
router.register(prefix="storages", viewset=StorageViewSet, basename="storages")
router.register(prefix="asset-types", viewset=AssetTypeViewSet, basename="asset-types")
# router.register(prefix='asset-classifications', viewset=AssetClassificationViewSet, basename='asset-classifications')
router.register(prefix="contracts", viewset=ContractViewSet, basename="contracts")
router.register(prefix="assets", viewset=AssetViewSet, basename="assets")
# router.register(prefix='create', viewset=AssetViewSet, basename='create')
router.register(prefix="out-assets", viewset=OutAssetViewSet, basename="out-assets")
router.register(prefix="recycle-assets", viewset=RecycleAssetViewSet, basename="recycle-assets")
router.register(prefix="damaged-assets", viewset=DamagedAssetViewSet, basename="damaged-assets")
router.register(prefix="waste-assets", viewset=WasteAssetViewSet, basename="waste-assets")
router.register(prefix="harddisk-sn", viewset=HardDiskSNViewSet, basename="harddisk-sn")
router.register(prefix="broken-assets", viewset=BrokenAssetViewSet, basename="broken-assets")
router.register(prefix="lost-assets", viewset=LostAssetViewSet, basename="lost-assets")
router.register(prefix="found-assets", viewset=FoundAssetViewSet, basename="found-assets")
router.register(prefix="repair-assets", viewset=RepairAssetViewSet, basename="repair-assets")
# DashboardViewSet 已在 dashboard_urls.py 中单独配置

urlpatterns: list[URLResolver | URLPattern] = [
    path(route="", view=include(arg=router.urls)),
    # path('api/', include(router.urls)),  # 最终路由:/api/assets/contracts/{pk}/
    # ========== 资产操作记录API(只读)==========
    # 【AGENTS 规范 - 架构优化】新增操作记录查询接口
    path(
        "operation-logs/by-logging-id/<str:logging_id>/",
        AssetOperationLogByLoggingIdView.as_view(),
        name="operation-log-by-logging-id",
    ),
    path("operation-logs/", AssetOperationLogListView.as_view(), name="operation-log-list"),
    path(
        "operation-logs/export/",
        AssetOperationLogExportView.as_view(),
        name="operation-log-export",
    ),
    path("operation-logs/<int:id>/", AssetOperationLogDetailView.as_view(), name="operation-log-detail"),
    path("operation-logs/recent/", RecentOperationsView.as_view(), name="operation-log-recent"),
    path("operation-logs/user/<str:operator_jobcode>/", UserOperationsView.as_view(), name="operation-log-user"),
    path("assets/<str:asset_code>/history/", AssetHistoryView.as_view(), name="asset-history"),
    path("assets/<str:asset_code>/timeline/", AssetStatusTimelineView.as_view(), name="asset-timeline"),
    # 资产分组汇总(纯新增端点,不修改既有 assets 路由)
    # 目标 /api/v1/assets/grouped/(04 §2.4b.1)。此处写 "grouped/" 而非 "assets/grouped/":
    # 本文件已被 config/urls.py:159 以 "api/v1/assets/" 前缀 include,故 "grouped/" 即为契约路径。
    # ⚠️ 既有资产列表因 router 前缀叠加实际在 /api/v1/assets/assets/(前端 asset.ts:82 亦如此),
    #    新端点不跟随该叠加 —— 契约以 04 文档为准,前端按 request.get('/assets/grouped/') 调用。
    # as_view({"get": "list"}) 使 self.action == "list",RBAC 解析依赖该值。
    path("grouped/", AssetGroupedViewSet.as_view({"get": "list"}), name="asset-grouped"),
    # 资产分组明细(纯新增端点)。目标 /api/v1/assets/group_children/(04 §2.4b.2)。
    # 前缀规则与上面 grouped/ 完全一致(本文件已被 include 于 "api/v1/assets/"。
    path(
        "group_children/",
        AssetGroupChildrenViewSet.as_view({"get": "list"}),
        name="asset-group-children",
    ),
    # 公开扫码接口(无需认证)
    path("public/scan/<str:recordcode>/", public_scan_view, name="public-scan"),
]

"""
在 Django REST Framework 中,当你使用 router.register() 注册视图集时,
路由会自动映射到视图集中的标准方法,遵循 RESTful API 的设计规范。

映射关系如下:
HTTP方法    URL路径              对应方法        功能描述
GET         /assets/            list()         获取资源列表
POST        /assets/            create()       创建新资源
GET         /assets/{id}/       retrieve()     获取单个资源详情
PUT         /assets/{id}/       update()       全量更新资源
PATCH	            /assets/{id}/	             partial_update()	    部分更新资源
DELETE	            /assets/{id}/	             destroy()	            删除资源
自定义 action 的响应必须遵守 B1 信封契约（utils.response_utils.success_response），
状态变更必须经 Service 层与状态机（B5/B6），禁止在 View 内直接 save() 或裸 dict Response。
完整示例见 Rules_Fiels/backend-business-rules.md。
"""
