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

from typing import Any

from django.http import Http404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from apps.usermanagement.models import Role, UserRole
from apps.usermanagement.rbac_serializers import (
    RoleCreateUpdateSerializer,
    RoleSerializer,
    UserRoleSerializer,
)
from apps.usermanagement.selectors import RoleSelector
from apps.usermanagement.services import RoleService
from core.exceptions import AppValidationError
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
class RoleViewSet(ResponseWrapperMixin, viewsets.ModelViewSet):  # type: ignore[type-arg]
    """
    角色管理 ViewSet

    权限定义:
    - 全部操作(读/写):仅系统管理员
    - [P3-9] 读面收口:list/retrieve 由需登录收紧为仅系统管理员
      (防角色/权限配置枚举泄露)
    """

    queryset = Role.objects.filter(is_deleted=False)
    serializer_class = RoleSerializer
    permission_classes = [IsSystemAdmin]  # [P3-9] 读面收口:读写面统一仅系统管理员

    def get_serializer_class(self) -> Any:
        if self.action in ("create", "update", "partial_update"):
            return RoleCreateUpdateSerializer
        return RoleSerializer

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """软删除角色(M-29: 守卫下沉 RoleService.delete_role;C1 修复保持:重写 destroy 而非 perform_destroy)"""
        try:
            instance = self.get_object()
            RoleService.delete_role(instance)
            return success_response(data={}, message="删除成功", status_code=status.HTTP_200_OK)
        except Http404:
            return error_response(message="资源不存在或已被删除", status_code=status.HTTP_404_NOT_FOUND)
        except AppValidationError as e:
            # 对齐 ResponseWrapperMixin.destroy 400 直传语义;文案逐字保留(view 原内联守卫文)
            return error_response(message=str(e.detail), status_code=status.HTTP_400_BAD_REQUEST)
        except APIException:
            # 让 DRF APIException 正常传播(对齐 core/mixins.py:210-212)
            raise

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
                            "data": {"role_code": "admin", "permissions": ["asset:read", "asset:create"]},
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
    def role_permissions(self, request: Any, pk: Any = None) -> Response:
        """
        获取或设置角色的权限码

        GET  /api/v1/users/roles/{id}/permissions/ — 获取权限码列表
        POST /api/v1/users/roles/{id}/permissions/ — 全量替换权限码
        """
        role = self.get_object()

        if request.method == "GET":
            perm_codes = RoleSelector.get_active_permission_codes(role)
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
class UserRoleViewSet(ResponseWrapperMixin, viewsets.ModelViewSet):  # type: ignore[type-arg]
    """
    用户-角色分配 ViewSet

    提供用户角色的 list/create/delete 操作。
    仅系统管理员可操作。
    """

    serializer_class = UserRoleSerializer
    permission_classes = [IsSystemAdmin]
    pagination_class = None  # 用户角色数量少,不需要分页
    http_method_names = ["get", "post", "delete", "head", "options"]  # C2 修复:禁止 update/patch

    def get_queryset(self) -> Any:
        # schema 离线导出无认证用户,返回 none() 仅供 spectacular 解析模型,运行时不走此分支
        if getattr(self, "swagger_fake_view", False):
            return UserRole.objects.none()
        return RoleSelector.get_active_user_roles(self.kwargs.get("user_id"), self.request.user)

    def perform_create(self, serializer: Any) -> None:
        """创建用户角色关联(D1: data_scope 由 Service 继承 Employee 部门)"""
        user_id = self.kwargs.get("user_id")
        raw_role = serializer.validated_data.get("role")
        role_id = raw_role.pk if hasattr(raw_role, "pk") else raw_role

        RoleService.assign_role(user_id, role_id)  # type: ignore[arg-type]

    def perform_destroy(self, instance: Any) -> None:
        """删除用户角色关联"""
        RoleService.remove_role(instance.auth_user_id, instance.role_id)
