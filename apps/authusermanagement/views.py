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
from rest_framework_simplejwt.exceptions import TokenError

from apps.authusermanagement.authentication import (
    JWTCookieAuthentication,
    enforce_csrf_if_cookie_channel,
    get_auth_channel,
)
from apps.authusermanagement.cookie_utils import delete_auth_cookies, get_refresh_token, set_auth_cookies
from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.selectors import AuthUserSelector
from apps.authusermanagement.serializers import (
    AuthUserSerializer,
    LoginSerializer,
    LogoutSerializer,  # 【新增】退出登录序列化器
    ProfileSerializer,
    RegisterSerializer,
    UserProfileUpdateSerializer,
)
from apps.authusermanagement.services import AuthService
from core.exceptions import AppValidationError
from core.permissions import IsSystemAdmin
from utils.response_utils import error_response, success_response
from utils.user_utils import resolve_operator


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
        自定义权限:
        - 创建用户:任何人可注册
        - 列表和详情页:仅管理员可访问
        - 更新和删除:仅管理员或本人可操作
        """
        if self.action == "create":
            permission_classes = [permissions.AllowAny]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsSystemAdmin]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self) -> type[AuthUserSerializer] | type[RegisterSerializer]:
        """根据不同的操作选择不同的序列化器"""
        if self.action == "create":
            return RegisterSerializer
        return AuthUserSerializer

    def check_object_permissions(self, request: Any, obj: Any) -> None:
        """检查对象权限(本人账号或系统管理员)"""
        if self.action in ["update", "partial_update", "destroy"]:
            is_admin = IsSystemAdmin().has_permission(request, self)
            if not (is_admin or obj.auth_id == request.user.auth_id):
                self.permission_denied(request, message="您没有权限执行此操作。")

        return super().check_object_permissions(request, obj)

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        创建新用户

        【修复 S8】使用 RegisterSerializer,它会自动忽略 auth_is_staff 等敏感字段
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            data = {"user": AuthUserSerializer(user).data, **AuthService.issue_tokens(user)}
            response = success_response(data=data, message="注册成功", status_code=status.HTTP_201_CREATED)
            set_auth_cookies(request, response, data["access"], data["refresh"])
            return response
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

        【P2-08 修复】使用 AuthService.update_user() 替代直接 perform_update,
        确保业务校验和审计日志记录。
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            from apps.authusermanagement.services import AuthService

            user = AuthService.update_user(
                auth_id=instance.auth_id,
                update_data=serializer.validated_data,
                operator_jobcode=resolve_operator(request.user)[0],
                operator_name=resolve_operator(request.user)[1],
            )
            return success_response(data=self.get_serializer(user).data, message="更新成功")
        return error_response(message="更新失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """删除用户"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(message="删除成功")

    # 【AGENTS 规范 - P3-35】添加获取所有激活用户的 action
    @action(detail=False, methods=["get"], permission_classes=[IsSystemAdmin])
    def list_active(self, request: Any) -> Response:
        """
        获取所有激活用户

        返回 auth_is_active=True 的用户列表,支持分页。
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
    # 【修复】限制注册频率,防止批量注册攻击(5次/分钟)
    from core.throttles import RegisterRateThrottle

    throttle_classes = [RegisterRateThrottle]

    @extend_schema(
        operation_id="auth_register",
        summary="用户注册",
        description="注册新用户账号,注册成功后自动返回JWT Token",
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
            400: OpenApiResponse(description="注册失败,参数校验错误"),
        },
        tags=["认证管理"],
    )
    def post(self, request: Any) -> Response:
        """
        用户注册

        【修复 S8】使用 RegisterSerializer,它会自动忽略 auth_is_staff 等敏感字段
        """
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            data = {"user": AuthUserSerializer(user).data, **AuthService.issue_tokens(user)}
            response = success_response(data=data, message="注册成功", status_code=status.HTTP_201_CREATED)
            set_auth_cookies(request, response, data["access"], data["refresh"])
            return response
        return error_response(message="注册失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    """
    用户登录视图
    """

    permission_classes = [permissions.AllowAny]
    # 【修复】限制登录频率,防止暴力破解攻击
    throttle_classes = []  # 使用全局 throttle 配置

    @extend_schema(
        operation_id="auth_login",
        summary="用户登录",
        description="使用用户名、邮箱或手机号登录,登录成功返回JWT Token(access + refresh)",
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
        """用户登录(双通道签发: 响应体 Bearer + PC Cookie 双写)"""
        # 登录 CSRF 加固: 要求 X-Requested-With 头(跨域表单无法携带该头)
        if request.META.get("HTTP_X_REQUESTED_WITH") != "XMLHttpRequest":
            return error_response(message="非法请求来源", status_code=status.HTTP_403_FORBIDDEN)

        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="登录失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        validated_data = cast(dict[str, Any], serializer.validated_data)
        user = AuthService.authenticate_user(
            validated_data.get("auth_username", ""), validated_data.get("password", "")
        )

        if user and user.auth_is_active:
            data = {"user": AuthUserSerializer(user).data, **AuthService.issue_tokens(user)}
            response = success_response(data=data, message="登录成功")
            set_auth_cookies(request, response, data["access"], data["refresh"])
            return response

        return error_response(message="用户名或密码错误", status_code=status.HTTP_401_UNAUTHORIZED)


class UserProfileAPIView(APIView):
    """
    用户信息视图

    【修复 S7】使用 UserProfileUpdateSerializer,仅允许更新 email 和 auth_phone
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTCookieAuthentication]

    @extend_schema(
        operation_id="auth_profile",
        summary="获取当前用户信息",
        description="获取当前登录用户的详细信息",
        responses={200: AuthUserSerializer},
        tags=["认证管理"],
    )
    def get(self, request: Any) -> Response:
        """获取当前用户信息(含 RBAC 派生字段)"""
        serializer = ProfileSerializer(request.user)
        return success_response(data=serializer.data)

    @extend_schema(
        operation_id="auth_profile_update",
        summary="更新当前用户信息",
        description="更新当前登录用户的个人信息(仅允许修改email、手机号、密码)",
        request=UserProfileUpdateSerializer,
        responses={200: AuthUserSerializer},
        tags=["认证管理"],
    )
    def put(self, request: Any) -> Response:
        """
        更新当前用户信息

        【修复 S7】使用 UserProfileUpdateSerializer,防止修改敏感字段
        """
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response(data=AuthUserSerializer(request.user).data, message="更新成功")
        return error_response(message="更新失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class LogoutAPIView(APIView):
    """
    用户退出登录视图(双通道, 宽容清理)

    - bearer 通道: body 提交 refresh 作废
    - cookie 通道: 从 refresh Cookie 读取, 无需 body
    - 宽容策略: refresh 无效/已作废/已过期也返回成功并清除 Cookie
    - 认证类置空: 过期 access cookie 不应阻断登出流程
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        operation_id="auth_logout",
        summary="用户退出登录",
        description="将 refresh_token 加入黑名单,使其无法再用于获取新的 access_token。"
        "双通道: 移动端 body 携带 refresh, PC 端从 refresh Cookie 自动读取。",
        request=LogoutSerializer,
        responses={
            200: OpenApiResponse(
                description="退出成功",
                examples=[
                    OpenApiExample("退出成功", value={"code": 0, "message": "退出成功,Token 已作废", "data": {}})
                ],
            ),
            400: OpenApiResponse(description="请求参数错误"),
            403: OpenApiResponse(description="CSRF 校验失败"),
        },
        tags=["认证管理"],
    )
    def post(self, request: Any) -> Response:
        """处理退出登录请求(cookie 通道强制 CSRF, 失败宽容返回成功)"""
        enforce_csrf_if_cookie_channel(request)

        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="退出失败", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        refresh_token = cast(dict[str, Any], serializer.validated_data).get("refresh") or get_refresh_token(request)
        if refresh_token:
            try:
                AuthService.logout_user(refresh_token=refresh_token)
            except AppValidationError:
                pass  # 宽容清理: refresh 已作废/过期也继续清除 Cookie

        response = success_response(message="退出成功,Token 已作废")
        delete_auth_cookies(response)
        return response


class RBACTokenRefreshView(APIView):
    """
    RBAC Token 刷新视图(双通道)

    - bearer 通道: body 取 refresh, 轮换并黑名单旧 token
    - cookie 通道: 从 refresh Cookie 取 token, 轮换并回写 Cookie
    - 刷新时重新注入最新 RBAC claims, 角色变更后立即生效
    - 认证类置空: access cookie 过期时不阻断 refresh
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Any) -> Response:
        enforce_csrf_if_cookie_channel(request)
        channel = get_auth_channel(request)
        refresh_token = request.data.get("refresh") if channel == "bearer" else get_refresh_token(request)
        if not refresh_token:
            return error_response(message="缺少 refresh 参数", status_code=400)

        try:
            data = AuthService.refresh_tokens(refresh_token)
        except TokenError:
            return error_response(message="Token 无效或已过期", status_code=401)
        except AuthUser.DoesNotExist:
            return error_response(message="用户不存在", status_code=400)

        response = success_response(data=data, message="Token 刷新成功")
        if channel == "cookie":
            set_auth_cookies(request, response, data["access"], data.get("refresh"))
        return response
