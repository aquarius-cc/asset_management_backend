"""
权限点管理视图集,提供权限点只读 API(list/retrieve)

类:
  - PermissionViewSet: 权限点只读视图集(禁止创建/更新/删除)

调用链:
  本模块被 urls.py 路由注册
  本模块依赖 models.Permission、rbac_serializers.PermissionSerializer
"""

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.viewsets import GenericViewSet

from apps.usermanagement.models import Permission
from apps.usermanagement.rbac_serializers import PermissionSerializer
from core.mixins import ResponseWrapperMixin
from core.permissions import IsSystemAdmin


@extend_schema_view(
    list=extend_schema(
        summary="获取权限列表",
        description="获取所有权限点列表,不分页一次性返回全部。",
        tags=["权限管理"],
    ),
    retrieve=extend_schema(
        summary="获取权限详情",
        description="根据权限ID获取权限点详细信息。",
        tags=["权限管理"],
    ),
)
class PermissionViewSet(ResponseWrapperMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):  # type: ignore[type-arg]
    """
    权限点 ViewSet(只读)

    仅支持 list 和 retrieve 操作,禁止创建/更新/删除。
    """

    # OP-09 方案 A 幽灵路由清理：基线 v1_users_permissions_create/update/destroy 三条
    # 永远 500 的幽灵路由（ResponseWrapperMixin 五方法因 GenericViewSet 缺
    # perform_create/perform_destroy 兜不住真实 CRUD）；http_method_names 过滤后写方法
    # 路由仍在但运行时 405（mixin 保留供 list/retrieve 信封），schema 侧 operation 消失。
    http_method_names = ["get", "head", "options"]

    queryset = Permission.objects.filter(is_deleted=False)
    serializer_class = PermissionSerializer
    permission_classes = [IsSystemAdmin]  # [P3-9] 读面收口:权限点枚举仅系统管理员
    pagination_class = None  # 权限列表不分页,一次性返回全部
