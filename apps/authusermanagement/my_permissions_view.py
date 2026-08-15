"""
当前用户权限查询视图(MyPermissionsAPIView)

提供 /api/v1/auth/my-permissions/ 端点,返回当前登录用户的权限码列表与数据范围。

权限码来源:PermissionService.get_effective_permissions_for_user(superuser 全量 + G6 回退)
数据范围来源:core.department_scope.get_effective_data_scope_for_user(G1-B flavor a)
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usermanagement.services.permission_service import PermissionService
from core.department_scope import get_effective_data_scope_for_user
from utils.response_utils import success_response


class MyPermissionsAPIView(APIView):
    """
    当前用户权限查询视图(只读)

    返回 {permissions: [...], data_scope: {...}},对齐前端 MyPermissionsResponse。
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="my_permissions",
        summary="获取当前用户权限",
        description="返回当前登录用户的权限码列表与数据范围。",
        responses={200: OpenApiResponse(description="权限列表与数据范围")},
        tags=["认证管理"],
    )
    def get(self, request) -> Response:
        user = request.user
        data = {
            "permissions": PermissionService.get_effective_permissions_for_user(user),
            "data_scope": get_effective_data_scope_for_user(user),
        }
        return success_response(data=data, message="获取成功")
