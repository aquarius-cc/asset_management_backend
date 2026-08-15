"""
角色管理视图集,提供角色 CRUD 和用户角色分配 API

类:
  - RoleViewSet: 角色管理视图集(CRUD + 权限设置)
  - UserRoleViewSet: 用户-角色分配视图集(list/create/delete)

方法:
  - role_permissions: 获取或设置角色的权限码(GET/POST)
  - destroy: 软删除角色(含系统内置/已分配用户检查)

调用链:
  本模块被 urls.py 路由注册
  本模块依赖 RoleService、models(Role, UserRole)
"""

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action

from apps.usermanagement.models import Role, UserRole
from apps.usermanagement.rbac_serializers import (
    RoleCreateUpdateSerializer,
    RoleSerializer,
    UserRoleSerializer,
)
from apps.usermanagement.services import RoleService
from core.mixins import ResponseWrapperMixin
from core.permissions import IsSystemAdmin
from utils.response_utils import error_response, success_response


@extend_schema_view(
    list=extend_schema(
        summary="获取角色列表",
        description="查询所有角色列表,支持分页。",
        tags=["角色管理"],
    ),
    create=extend_schema(
        summary="创建角色",
        description="创建新角色,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    retrieve=extend_schema(
        summary="获取角色详情",
        description="根据角色ID获取角色详细信息。",
        tags=["角色管理"],
    ),
    update=extend_schema(
        summary="更新角色",
        description="更新角色的全部信息,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    partial_update=extend_schema(
        summary="部分更新角色",
        description="部分更新角色信息,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    destroy=extend_schema(
        summary="删除角色",
        description="软删除角色,系统内置角色和已分配用户的角色不可删除。",
        tags=["角色管理"],
    ),
)
class RoleViewSet(ResponseWrapperMixin, viewsets.ModelViewSet):
    """
    角色管理 ViewSet

    权限定义:
    - 写操作(create/update/destroy):仅系统管理员
    - 读操作(list/retrieve):需登录
    """

    queryset = Role.objects.filter(is_deleted=False)
    serializer_class = RoleSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "role_permissions"):
            return [IsSystemAdmin()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return RoleCreateUpdateSerializer
        return RoleSerializer

    def destroy(self, request, *args, **kwargs):
        """软删除角色(C1 修复:重写 destroy 而非 perform_destroy)"""
        instance = self.get_object()
        if instance.is_system:
            return error_response(
                message="系统内置角色不可删除",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        # H4 修复:检查角色是否已分配给用户
        if UserRole.objects.filter(role=instance, is_deleted=False).exists():
            return error_response(
                message="该角色已分配给用户,不可删除。请先移除所有用户的角色分配。",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        operation_id="role_permissions",
        summary="获取或设置角色权限",
        description=(
            "GET: 获取指定角色的权限码列表。\n"
            "POST: 全量替换指定角色的权限码,需提交 permission_codes 列表。仅系统管理员可操作。"
        ),
        tags=["角色管理"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "permission_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "权限码列表(POST 时必填)",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="成功",
                examples=[
                    OpenApiExample(
                        "GET成功",
                        value={
                            "code": 0,
                            "message": "",
                            "data": {"role_code": "admin", "permissions": ["asset:view", "asset:create"]},
                        },
                    ),
                    OpenApiExample(
                        "POST成功",
                        value={"code": 0, "message": "权限设置成功", "data": None},
                    ),
                ],
            ),
            400: OpenApiResponse(description="参数错误"),
            404: OpenApiResponse(description="角色不存在"),
        },
    )
    @action(detail=True, methods=["get", "post"], url_path="permissions")
    def role_permissions(self, request, pk=None):
        """
        获取或设置角色的权限码

        GET  /api/v1/users/roles/{id}/permissions/ — 获取权限码列表
        POST /api/v1/users/roles/{id}/permissions/ — 全量替换权限码
        """
        role = self.get_object()

        if request.method == "GET":
            perm_codes = list(
                role.role_permissions.filter(is_deleted=False).values_list("permission__permission_code", flat=True)
            )
            return success_response(data={"role_code": role.role_code, "permissions": perm_codes})

        # POST: 设置权限码
        permission_codes = request.data.get("permission_codes", [])

        if not isinstance(permission_codes, list):
            return error_response(
                message="permission_codes 必须是列表",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        RoleService.sync_role_permissions(role.id, permission_codes)
        return success_response(message="权限设置成功")


@extend_schema_view(
    list=extend_schema(
        summary="获取用户角色列表",
        description="查询用户的角色分配列表,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    create=extend_schema(
        summary="分配用户角色",
        description="为用户分配角色,支持设置数据范围,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    retrieve=extend_schema(
        summary="获取用户角色详情",
        description="获取用户角色分配的详细信息,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
    destroy=extend_schema(
        summary="移除用户角色",
        description="移除用户的角色分配,仅系统管理员可操作。",
        tags=["角色管理"],
    ),
)
class UserRoleViewSet(ResponseWrapperMixin, viewsets.ModelViewSet):
    """
    用户-角色分配 ViewSet

    提供用户角色的 list/create/delete 操作。
    仅系统管理员可操作。
    """

    serializer_class = UserRoleSerializer
    permission_classes = [IsSystemAdmin]
    pagination_class = None  # 用户角色数量少,不需要分页
    http_method_names = ["get", "post", "delete", "head", "options"]  # C2 修复:禁止 update/patch

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        if user_id:
            return UserRole.objects.filter(auth_user_id=user_id, is_deleted=False)
        # 无 user_id 时仅返回当前用户的角色分配(防止信息泄露)
        return UserRole.objects.filter(
            auth_user=self.request.user,
            is_deleted=False,
        )

    def perform_create(self, serializer):
        """创建用户角色关联(D1: data_scope 由 Service 继承 Employee 部门)"""
        user_id = self.kwargs.get("user_id")
        raw_role = serializer.validated_data.get("role")
        role_id = raw_role.pk if hasattr(raw_role, "pk") else raw_role

        RoleService.assign_role(user_id, role_id)

    def perform_destroy(self, instance):
        """删除用户角色关联"""
        RoleService.remove_role(instance.auth_user_id, instance.role_id)
