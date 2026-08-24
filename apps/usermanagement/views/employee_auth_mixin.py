"""
员工认证账号绑定相关视图 Mixin

从 employee_view.py 拆分(DR-5 文件规模红线),
仅包含员工与 AuthUser 绑定/解绑/替换及权限查询动作,
供 EmployeeViewSet 继承复用。
"""

from typing import Any
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action

from apps.authusermanagement.models import AuthUser
from apps.usermanagement.selectors import EmployeeSelector
from apps.usermanagement.serializers import EmployeeDetailSerializer
from apps.usermanagement.services import EmployeeService, PermissionService
from core.department_scope import get_effective_data_scope_for_user
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator


class EmployeeAuthMixin:
    """员工认证账号绑定/权限查询动作集合。"""

    @action(detail=False, methods=["get"], url_path="(?P<employee_jobcode>[^/.]+)/permissions")
    def get_employee_permissions(self, request: Any, employee_jobcode: Any = None) -> Any:
        """
        根据员工工号查询员工权限

        返回字段:
        - employee_jobcode: 员工工号
        - employee_name: 员工姓名
        - permissions: 权限码列表
        - data_scope: 数据范围字典

        权限查询链:Employee → AuthUser → UserRole → RolePermission → Permission

        权限要求:
        - 超级管理员:可查看任何员工
        - 普通用户:仅可查看自己的权限
        """
        # 权限检查:非超级管理员只能查看自己的权限
        if not getattr(request.user, "is_superuser", False):
            if request.user.auth_username != employee_jobcode:
                return error_response(
                    message="无权限查看其他员工权限",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        # 1. 查找员工
        employee = EmployeeSelector.get_employee_by_jobcode(employee_jobcode)
        if not employee:
            return error_response(
                message="员工不存在",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # 2. 查找对应的 AuthUser(通过 employee_jobcode == auth_username)
        # 【P1-6 顺带修复】AuthUser 模型无 is_deleted 字段,原过滤导致 FieldError→400
        try:
            auth_user = AuthUser.objects.get(auth_username=employee_jobcode)
        except AuthUser.DoesNotExist:
            # 员工没有对应的 AuthUser,返回空权限
            return success_response(
                data={
                    "employee_jobcode": employee_jobcode,
                    "employee_name": employee.employee_name,
                    "permissions": [],
                    "data_scope": {"scope_type": "departments", "department_codes": [], "include_children": False},
                }
            )

        # 3. 获取权限列表(G1-B 收敛:单入口)
        permissions = PermissionService.get_effective_permissions_for_user(auth_user)

        # 4. 获取数据范围(G1-B flavor a:直接派生自 Employee)
        data_scope = get_effective_data_scope_for_user(auth_user)

        return success_response(
            data={
                "employee_jobcode": employee_jobcode,
                "employee_name": employee.employee_name,
                "permissions": permissions,
                "data_scope": data_scope,
            }
        )

    @extend_schema(
        summary="绑定认证账号",
        description="将指定认证账号绑定到员工。员工必须未绑定认证账号,目标认证账号不能已绑定其他员工。",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "auth_username": {"type": "string", "description": "认证账号用户名"},
                },
                "required": ["auth_username"],
            }
        },
        responses={200: EmployeeDetailSerializer, 400: OpenApiResponse(description="绑定冲突或参数错误")},
    )
    @action(detail=True, methods=["post"], url_path="bind-auth-user")
    def bind_auth_user(self, request: Any, pk: Any = None) -> None:
        """
        绑定认证账号到员工

        POST /api/v1/users/{employee_jobcode}/bind-auth-user/
        Body: {"auth_username": "xxx"}

        权限要求:system_admin
        """
        auth_username = request.data.get("auth_username")
        if not auth_username:
            return error_response(message="请提供 auth_username 参数")

        operator_jobcode, operator_name = resolve_operator(request.user)

        employee = EmployeeService.bind_auth_user(
            employee_jobcode=pk,
            auth_username=auth_username,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        serializer = EmployeeDetailSerializer(employee)
        return success_response(data=serializer.data, message="绑定成功")

    @extend_schema(
        summary="解绑认证账号",
        description="解绑员工的认证账号。解绑后 AuthUser 权限保留(auth_user 可能是 API 账号)。",
        responses={200: EmployeeDetailSerializer, 400: OpenApiResponse(description="员工未绑定认证账号")},
    )
    @action(detail=True, methods=["post"], url_path="unbind-auth-user")
    def unbind_auth_user(self, request: Any, pk: Any = None) -> None:
        """
        解绑员工的认证账号

        POST /api/v1/users/{employee_jobcode}/unbind-auth-user/

        权限要求:system_admin
        """
        operator_jobcode, operator_name = resolve_operator(request.user)

        employee = EmployeeService.unbind_auth_user(
            employee_jobcode=pk,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        serializer = EmployeeDetailSerializer(employee)
        return success_response(data=serializer.data, message="解绑成功")

    @extend_schema(
        summary="替换认证账号",
        description="原子替换员工的认证账号(解绑旧 + 绑定新)。",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "auth_username": {"type": "string", "description": "新的认证账号用户名"},
                },
                "required": ["auth_username"],
            }
        },
        responses={200: EmployeeDetailSerializer, 400: OpenApiResponse(description="替换冲突或参数错误")},
    )
    @action(detail=True, methods=["post"], url_path="replace-auth-user")
    def replace_auth_user(self, request: Any, pk: Any = None) -> None:
        """
        替换员工的认证账号

        POST /api/v1/users/{employee_jobcode}/replace-auth-user/
        Body: {"auth_username": "new_user"}

        权限要求:system_admin
        """
        new_auth_username = request.data.get("auth_username")
        if not new_auth_username:
            return error_response(message="请提供 auth_username 参数")

        operator_jobcode, operator_name = resolve_operator(request.user)

        employee = EmployeeService.replace_auth_user(
            employee_jobcode=pk,
            new_auth_username=new_auth_username,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        serializer = EmployeeDetailSerializer(employee)
        return success_response(data=serializer.data, message="替换成功")
