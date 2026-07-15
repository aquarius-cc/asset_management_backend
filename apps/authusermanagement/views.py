"""
认证与用户管理视图

提供用户认证、注册、用户信息管理等API接口
"""

from typing import Any, cast

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.selectors import AuthUserSelector
from apps.authusermanagement.serializers import (
    AuthUserSerializer,
    LoginSerializer,
    LogoutSerializer,  # 【新增】退出登录序列化器
    RegisterSerializer,
    UserProfileUpdateSerializer,
)
from apps.authusermanagement.services import AuthService
from core.exceptions import AppValidationError
from core.permissions import IsAdminUser  # 【修复】使用自定义 IsAdminUser
from utils.response_utils import error_response, success_response


class AuthUserViewSet(viewsets.ModelViewSet):
    """
    用户管理视图集

    提供用户的CRUD操作
    【修复 S7/S8】防止权限提升和注册管理员
    """

    queryset = AuthUser.objects.all()
    serializer_class = AuthUserSerializer
    lookup_field = "auth_id"

    def get_permissions(self) -> list:
        """
        自定义权限：
        - 创建用户：任何人可注册
        - 列表和详情页：仅管理员可访问
        - 更新和删除：仅管理员或本人可操作
        """
        if self.action == "create":
            permission_classes = [permissions.AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self) -> type[AuthUserSerializer] | type[RegisterSerializer]:
        """根据不同的操作选择不同的序列化器"""
        if self.action == "create":
            return RegisterSerializer
        return AuthUserSerializer

    def check_object_permissions(self, request: Any, obj: Any) -> None:
        """检查对象权限"""
        if self.action in ["update", "partial_update", "destroy"]:
            if not (request.user.auth_is_staff or obj.auth_id == request.user.auth_id):
                self.permission_denied(request, message="您没有权限执行此操作。")

        return super().check_object_permissions(request, obj)

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        创建新用户

        【修复 S8】使用 RegisterSerializer，它会自动忽略 auth_is_staff 等敏感字段
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            data = {
                "user": AuthUserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
            return success_response(data=data, message="注册成功", status_code=status.HTTP_201_CREATED)
        return error_response(message="注册失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def list(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """列出所有用户"""
        queryset = AuthUserSelector.list_all_users()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    def retrieve(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """获取单个用户详情"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(data=serializer.data)

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        更新用户信息

        【P2-08 修复】使用 AuthService.update_user() 替代直接 perform_update，
        确保业务校验和审计日志记录。
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            try:
                from apps.authusermanagement.services import AuthService

                user = AuthService.update_user(
                    auth_id=instance.auth_id,
                    update_data=serializer.validated_data,
                    operator_jobcode=request.user.auth_id,
                    operator_name=request.user.auth_username,
                )
                return success_response(data=self.get_serializer(user).data, message="更新成功")
            except AppValidationError as e:
                return error_response(message=str(e), status_code=400)
        return error_response(message="更新失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """删除用户"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(message="删除成功")

    # 【AGENTS 规范 - P3-35】添加获取所有激活用户的 action
    @action(detail=False, methods=["get"], permission_classes=[IsAdminUser])
    def list_active(self, request: Any) -> Response:
        """
        获取所有激活用户

        返回 auth_is_active=True 的用户列表，支持分页。
        """
        queryset = AuthUserSelector.list_active_users()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)


class RegisterAPIView(APIView):
    """
    用户注册视图
    """

    permission_classes = [permissions.AllowAny]
    # 【修复】限制注册频率，防止批量注册攻击（5次/分钟）
    from core.throttles import RegisterRateThrottle

    throttle_classes = [RegisterRateThrottle]

    @extend_schema(
        operation_id="auth_register",
        summary="用户注册",
        description="注册新用户账号，注册成功后自动返回JWT Token",
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(
                description="注册成功",
                examples=[
                    OpenApiExample(
                        "注册成功",
                        value={
                            "code": 0,
                            "message": "注册成功",
                            "data": {
                                "user": {
                                    "auth_id": 1,
                                    "auth_username": "testuser",
                                    "email": "test@example.com",
                                },
                                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                                "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="注册失败，参数校验错误"),
        },
        tags=["认证管理"],
    )
    def post(self, request: Any) -> Response:
        """
        用户注册

        【修复 S8】使用 RegisterSerializer，它会自动忽略 auth_is_staff 等敏感字段
        """
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                refresh = RefreshToken.for_user(user)
                data = {
                    "user": AuthUserSerializer(user).data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
                return success_response(data=data, message="注册成功", status_code=status.HTTP_201_CREATED)
            except Exception as e:
                return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)
        return error_response(message="注册失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    """
    用户登录视图
    """

    permission_classes = [permissions.AllowAny]
    # 【修复】限制登录频率，防止暴力破解攻击
    throttle_classes = []  # 使用全局 throttle 配置

    @extend_schema(
        operation_id="auth_login",
        summary="用户登录",
        description="使用用户名、邮箱或手机号登录，登录成功返回JWT Token（access + refresh）",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(
                description="登录成功",
                examples=[
                    OpenApiExample(
                        "登录成功",
                        value={
                            "code": 0,
                            "message": "登录成功",
                            "data": {
                                "user": {
                                    "auth_id": 1,
                                    "auth_username": "admin",
                                    "email": "admin@example.com",
                                    "auth_is_active": True,
                                    "auth_is_staff": True,
                                },
                                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                                "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                            },
                        },
                    )
                ],
            ),
            401: OpenApiResponse(description="用户名或密码错误"),
            400: OpenApiResponse(description="请求参数错误"),
        },
        tags=["认证管理"],
    )
    def post(self, request: Any) -> Response:
        """用户登录"""
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="登录失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        validated_data = cast(dict, serializer.validated_data)
        auth_username = validated_data.get("auth_username", "")
        password = validated_data.get("password", "")

        user = AuthService.authenticate_user(auth_username, password)

        if user and user.auth_is_active:
            refresh = RefreshToken.for_user(user)

            # RBAC: 注入 role + department_code + is_superuser 到 JWT Token
            from apps.usermanagement.models import Employee
            employee = Employee.objects.select_related("employee_department").filter(
                employee_jobcode=user.auth_username
            ).first()

            # 超级管理员：role=system_admin，无 Employee 也注入
            if user.is_superuser:
                for token_obj in [refresh, refresh.access_token]:
                    token_obj["role"] = "system_admin"
                    token_obj["department_code"] = None
                    token_obj["is_superuser"] = True

            if employee:
                refresh["role"] = employee.role
                refresh["department_code"] = (
                    employee.employee_department.department_code
                    if employee.employee_department else None
                )
                refresh.access_token["role"] = employee.role
                refresh.access_token["department_code"] = (
                    employee.employee_department.department_code
                    if employee.employee_department else None
                )
            else:
                if not user.is_superuser:
                    refresh["role"] = "regular_user"
                    refresh["department_code"] = None
                    refresh.access_token["role"] = "regular_user"
                    refresh.access_token["department_code"] = None

            data = {
                "user": AuthUserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
            return success_response(data=data, message="登录成功")

        return error_response(message="用户名或密码错误", status_code=status.HTTP_401_UNAUTHORIZED)


class UserProfileAPIView(APIView):
    """
    用户信息视图

    【修复 S7】使用 UserProfileUpdateSerializer，仅允许更新 email 和 auth_phone
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_profile",
        summary="获取当前用户信息",
        description="获取当前登录用户的详细信息",
        responses={200: AuthUserSerializer},
        tags=["认证管理"],
    )
    def get(self, request: Any) -> Response:
        """获取当前用户信息"""
        serializer = AuthUserSerializer(request.user)
        return success_response(data=serializer.data)

    @extend_schema(
        operation_id="auth_profile_update",
        summary="更新当前用户信息",
        description="更新当前登录用户的个人信息（仅允许修改email、手机号、密码）",
        request=UserProfileUpdateSerializer,
        responses={200: AuthUserSerializer},
        tags=["认证管理"],
    )
    def put(self, request: Any) -> Response:
        """
        更新当前用户信息

        【修复 S7】使用 UserProfileUpdateSerializer，防止修改敏感字段
        """
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response(data=AuthUserSerializer(request.user).data, message="更新成功")
        return error_response(message="更新失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class LogoutAPIView(APIView):
    """
    用户退出登录视图

    接收客户端提交的 refresh_token，将其加入黑名单实现 Token 作废。

    【认证要求】
    - 需要携带有效的 access_token（IsAuthenticated）
    - 同时需要提交要作废的 refresh_token

    【安全设计】
    - 即使 access_token 仍然有效，refresh_token 被作废后无法获取新的 access_token
    - access_token 会在其自然过期后失效（短期有效，通常 2 小时）
    - 这种设计在安全性和用户体验之间取得平衡：
      · 立即阻止长期凭证（refresh_token）的后续使用
      · 不需要额外的 Token 撤销检查开销（access_token 自然过期）

    【使用流程】
    1. 客户端在退出时调用此接口，提交 refresh_token
    2. 服务端将 refresh_token 加入黑名单
    3. 客户端清除本地存储的 token 信息
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="auth_logout",
        summary="用户退出登录",
        description="将 refresh_token 加入黑名单，使其无法再用于获取新的 access_token。"
        "需要同时携带有效的 access_token 和要作废的 refresh_token。",
        request=LogoutSerializer,
        responses={
            200: OpenApiResponse(
                description="退出成功",
                examples=[OpenApiExample("退出成功", value={"code": 0, "message": "退出成功，Token 已作废", "data": {}})],
            ),
            400: OpenApiResponse(description="请求参数错误，refresh_token 无效或已过期"),
            401: OpenApiResponse(description="未认证，access_token 无效或已过期"),
        },
        tags=["认证管理"],
    )
    def post(self, request: Any) -> Response:
        """
        处理退出登录请求

        流程：
        1. 验证并解析请求中的 refresh_token
        2. 调用 AuthService.logout_user() 将 token 加入黑名单
        3. 返回成功响应

        Args:
            request: HTTP 请求对象，body 中需包含 refresh 字段

        Returns:
            Response: 退出成功或失败的统一格式响应
        """
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="退出失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        try:
            # 调用服务层执行 Token 黑名单写入
            validated_data = cast(dict, serializer.validated_data)
            AuthService.logout_user(refresh_token=validated_data["refresh"])
            return success_response(message="退出成功，Token 已作废")

        except AppValidationError as e:
            # 捕获服务层抛出的 Token 验证异常
            return error_response(message=str(e), status_code=status.HTTP_400_BAD_REQUEST)


class RBACTokenRefreshView(APIView):
    """
    RBAC Token 刷新视图

    在 SimpleJWT TokenRefreshView 基础上，刷新时重新注入 role + department_code。
    确保角色变更后，下次刷新 token 时能获取最新角色。
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request: Any) -> Response:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return error_response(message="缺少 refresh 参数", status_code=400)

        try:
            from rest_framework_simplejwt.tokens import RefreshToken as RefreshTokenClass
            from rest_framework_simplejwt.exceptions import TokenError

            refresh = RefreshTokenClass(refresh_token)

            # 从 refresh token 中获取 user_id（sub 字段）
            user_id = refresh.get("user_id")
            if not user_id:
                return error_response(message="Token 中无 user_id", status_code=400)

            from apps.authusermanagement.models import AuthUser
            try:
                user = AuthUser.objects.get(auth_id=user_id)
            except AuthUser.DoesNotExist:
                return error_response(message="用户不存在", status_code=400)

            # RBAC: 重新注入 role + department_code + is_superuser
            from apps.usermanagement.models import Employee
            employee = Employee.objects.select_related("employee_department").filter(
                employee_jobcode=user.auth_username
            ).first()

            # 超级管理员
            if user.is_superuser:
                for token_obj in [refresh, refresh.access_token]:
                    token_obj["role"] = "system_admin"
                    token_obj["department_code"] = None
                    token_obj["is_superuser"] = True

            if employee:
                refresh["role"] = employee.role
                refresh["department_code"] = (
                    employee.employee_department.department_code
                    if employee.employee_department else None
                )
                refresh.access_token["role"] = employee.role
                refresh.access_token["department_code"] = (
                    employee.employee_department.department_code
                    if employee.employee_department else None
                )
            else:
                if not user.is_superuser:
                    refresh["role"] = "regular_user"
                    refresh["department_code"] = None
                    refresh.access_token["role"] = "regular_user"
                    refresh.access_token["department_code"] = None

            data = {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
            return success_response(data=data, message="Token 刷新成功")

        except TokenError:
            return error_response(message="Token 无效或已过期", status_code=401)
        except Exception as e:
            return error_response(message=f"刷新失败: {str(e)}", status_code=400)
