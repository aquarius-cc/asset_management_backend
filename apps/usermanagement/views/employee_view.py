"""
员工管理视图
"""

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.usermanagement.models import Employee
from apps.usermanagement.selectors import EmployeeSelector
from apps.usermanagement.serializers import (
    EmployeeBatchCreateSerializer,
    EmployeeBatchDeleteSerializer,
    EmployeeBatchSortSerializer,
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeSerializer,
    EmployeeUpdateSerializer,
)
from apps.usermanagement.services import EmployeeService
from apps.usermanagement.views.employee_auth_mixin import EmployeeAuthMixin
from core.mixins import LoggingMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsSystemAdmin
from utils.response_utils import error_response, success_response


if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.response import Response
    from rest_framework.serializers import Serializer


# LoggingMixin.perform_* 与 DRF Mixin 存根签名存在已知偏差(项目内 mixin, 运行时行为正确)
class EmployeeViewSet(  # type: ignore[misc]
    EmployeeAuthMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,  # type: ignore[type-arg]
):
    """
    员工管理视图集

    继承 ResponseWrapperMixin 自动处理统一的响应格式:
    - list: 分页/不分页均返回 {code, msg, data}
    - create: 返回 {code, msg, data}
    - retrieve: 返回 {code, msg, data}
    - update/partial_update: 返回 {code, msg, data}
    - destroy: 返回 {code, msg, data}

    自定义 action 中手动调用 success_response/error_response 保持统一格式

    【修复 S12】管理操作需要管理员权限,防止普通用户创建/修改/删除员工
    """

    queryset = EmployeeSelector.get_queryset_with_bind_status()
    serializer_class = EmployeeSerializer
    pagination_class = CustomPageNumberPagination

    def get_permissions(self) -> list[permissions.BasePermission]:
        permission_classes: list[type[permissions.BasePermission]]
        """
        自定义权限:管理员可管理员工,普通用户只能查看
        """
        # H2 修复:绑定/解绑操作使用 IsSystemAdmin 而非 IsAdminUser
        if self.action in [
            "bind_auth_user",
            "unbind_auth_user",
            "replace_auth_user",
        ]:
            permission_classes = [IsSystemAdmin]
        elif self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "batch_create",
            "batch_delete",
            "batch_sort",
            "change_status",
        ]:
            permission_classes = [IsSystemAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["employee_status", "employee_department__department_code"]
    search_fields = ["employee_name", "employee_jobcode", "employee_phone"]
    ordering_fields = [
        "employee_jobcode",
        "employee_name",
        "sort_order",
        "employee_department__level",
        "employee_department__department_code",
        "employee_department__sort_order",
    ]
    ordering = [
        "employee_department__level",
        "employee_department__department_code",
        "employee_department__sort_order",
        "sort_order",
        "employee_jobcode",
    ]
    lookup_field = "employee_jobcode"

    def update(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """更新员工(含审计日志)"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        before_data = EmployeeDetailSerializer(instance).data
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        # get_serializer 返回 BaseSerializer, 运行时为 Serializer 子类
        self.perform_update(serializer)  # type: ignore[arg-type]
        after_data = EmployeeDetailSerializer(instance).data
        from apps.usermanagement.employee_audit_adapter import EmployeeAuditAdapter

        EmployeeAuditAdapter.log_update(
            instance,
            before_data,
            after_data,
            request.user.auth_username if hasattr(request.user, "auth_username") else None,
            str(request.user) if hasattr(request.user, "__str__") else None,
        )
        return success_response(data=serializer.data, message="更新成功")

    def partial_update(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """部分更新员工(含审计日志)"""
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """删除员工(含审计日志)"""
        instance = self.get_object()
        from apps.usermanagement.employee_audit_adapter import EmployeeAuditAdapter

        EmployeeAuditAdapter.log_delete(
            instance.employee_jobcode,
            instance.employee_name,
            request.user.auth_username if hasattr(request.user, "auth_username") else None,
            str(request.user) if hasattr(request.user, "__str__") else None,
        )
        self.perform_destroy(instance)
        return success_response(message="删除成功")

    def get_serializer_class(self) -> "type[Serializer[Any]]":
        """根据不同的操作选择不同的序列化器"""
        if self.action == "create":
            return EmployeeCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return EmployeeUpdateSerializer
        elif self.action == "retrieve":
            return EmployeeDetailSerializer
        return EmployeeSerializer

    # ---------- 自定义动作 ----------
    @extend_schema(
        summary="根据 AuthUser ID 查询绑定的 Employee",
        parameters=[
            OpenApiParameter(
                name="auth_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="AuthUser ID",
                required=True,
            ),
        ],
        responses={200: EmployeeDetailSerializer},
    )
    @action(detail=False, methods=["get"], url_path="by-auth-user/(?P<auth_id>[^/.]+)")
    def by_auth_user(self, request: "Request", auth_id: str | None = None) -> "Response":
        """根据 AuthUser ID 查询绑定的 Employee"""
        try:
            employee = Employee.objects.select_related("employee_department", "auth_user").get(auth_user_id=auth_id)
            serializer = EmployeeDetailSerializer(employee)
            return success_response(data=serializer.data)
        except Employee.DoesNotExist:
            return error_response(
                message="未找到绑定的员工",
                status_code=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["get"], url_path="employees/(?P<employee_jobcode>[^/.]+)")
    def get_employee_by_jobcode(self, request: "Request", employee_jobcode: str | None = None) -> "Response":
        """根据工号查询员工(统一格式)"""
        employee = get_object_or_404(self.queryset, employee_jobcode=employee_jobcode)
        serializer = EmployeeDetailSerializer(employee)
        return success_response(data=serializer.data)

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: "Request") -> "Response":
        """批量创建员工"""
        serializer = EmployeeBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EmployeeService.batch_create_employee(serializer.validated_data["items"])

        success_serializer = EmployeeDetailSerializer(result["success_items"], many=True)

        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_items": success_serializer.data,
                "fail_items": result["fail_items"],
            },
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @action(detail=False, methods=["post"], url_path="batch-delete")
    def batch_delete(self, request: "Request") -> "Response":
        """批量删除员工"""
        serializer = EmployeeBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EmployeeService.batch_delete_employee(serializer.validated_data["ids"])

        return success_response(
            data={
                "total": result["total"],
                "success_count": result["success_count"],
                "fail_count": result["fail_count"],
                "success_ids": result["success_ids"],
                "fail_items": result["fail_items"],
            },
            message=f"批量删除完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="name",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="员工名称",
                required=True,
            ),
            OpenApiParameter(name="page", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="page_size", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: EmployeeDetailSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request: "Request") -> "Response":
        """获取员工统计信息(统一格式)"""
        # 【AGENTS 规范 - P1-10】统计逻辑迁移到 EmployeeSelector.get_employee_statistics()
        stats = EmployeeSelector.get_employee_statistics()
        return success_response(data=stats)

    # 显式指定 url_path 后,后端实际路径以 url_path 值为准。
    # @action 装饰器未指定 url_path,会默认使用方法名 active_employees
    @action(detail=False, methods=["get"], url_path="active_employees")
    def active_employees(self, request: "Request") -> "Response":
        """获取所有在职员工列表(统一格式)"""
        # 【AGENTS 规范 - P1-10】使用 EmployeeSelector.get_active_employees() 替代直接 ORM 调用
        queryset = EmployeeSelector.get_active_employees()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data={
                # 【P2-07 修复】使用 queryset.count() 替代 len(serializer.data),避免不必要的序列化
                "count": queryset.count(),
                "results": serializer.data,
            }
        )

    @action(detail=True, methods=["post"])
    def change_status(self, request: "Request", pk: int | None = None) -> "Response":
        """更改员工状态(统一格式)"""
        employee = self.get_object()
        request_body = request.data
        new_status = request_body.get("status") if isinstance(request_body, dict) else None

        if not new_status:
            return error_response(message="请提供要更改的状态值")

        # 【AGENTS 规范 - P1-10】状态变更逻辑迁移到 EmployeeService.change_employee_status()
        employee = EmployeeService.change_employee_status(employee, new_status)

        serializer = EmployeeDetailSerializer(employee)
        return success_response(
            data={
                "message": f"员工状态已更改为: {dict(Employee.EMPLOYEE_STATUS_CHOICES)[new_status]}",
                "employee": serializer.data,
            }
        )

    @extend_schema(
        summary="全局模糊搜索员工",
        description=(
            "在员工姓名、工号、手机号、部门名称等关键字段中进行不区分大小写的模糊搜索。\n"
            "✅ 支持中文/英文/数字混合搜索 | ✅ 自动去重 | ✅ 分页返回"
        ),
        parameters=[
            OpenApiParameter(
                name="keyword",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="搜索关键词",
                required=True,
            ),
            OpenApiParameter(name="page", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="page_size", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: EmployeeSerializer(many=True), 400: OpenApiResponse(description="参数错误")},
    )
    @action(detail=False, methods=["get"], url_path="search", permission_classes=[permissions.IsAuthenticated])
    def global_search(self, request: "Request") -> "Response":
        """
        全局模糊搜索员工(统一格式)

        【AGENTS 规范 - P3-29】搜索逻辑(含状态别名映射)已迁移到
        EmployeeSelector.search_employees(),视图层仅负责调用 Selector 和分页。
        """
        keyword = request.query_params.get("keyword", "").strip()
        if not keyword:
            return error_response(message="请提供搜索关键词")

        # 【AGENTS 规范 - P3-29】使用 EmployeeSelector 替代视图层手写 Q 条件
        queryset = EmployeeSelector.search_employees(keyword)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data={
                # 【P2-07 修复】使用 queryset.count() 替代 len(serializer.data)
                "count": queryset.count(),
                "results": serializer.data,
            }
        )

    # 【AGENTS 规范 - P3-44】启用 create() 方法,调用 EmployeeService.create_employee()
    # 实现工号唯一性校验,避免视图层直接 serializer.save() 跳过业务校验
    def create(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """
        创建员工

        【AGENTS 规范 - P3-44】通过 EmployeeService.create_employee() 创建,
        Service 层负责工号唯一性校验(抛出 ValidationError),
        视图层仅负责序列化验证和响应格式化。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 【AGENTS 规范 - P3-44】调用 Service 层创建,包含工号唯一性校验
        employee = EmployeeService.create_employee(serializer.validated_data)

        return success_response(
            data=EmployeeDetailSerializer(employee).data,
            message="员工创建成功",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["put"], url_path="sort")
    def batch_sort(self, request: "Request") -> "Response":
        """
        批量更新员工排序字段

        【AGENTS 规范 - P3-45】批量更新逻辑已迁移到 EmployeeSelector.batch_update_sort(),
        批量更新员工排序(前端传入列表,每个元素包含 employee_jobcode 和 sort_order)
        视图层仅负责调用 Selector 和返回成功响应。

        【修复】使用 EmployeeBatchSortSerializer 提供批量大小限制和重复校验
        """
        serializer = EmployeeBatchSortSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 【AGENTS 规范 - P3-45】调用 Selector 批量更新
        updated_employees = EmployeeSelector.batch_update_sort(serializer.validated_data["items"])
        # 返回更新后的员工数据
        response_serializer = self.get_serializer(updated_employees, many=True)
        return success_response(
            data=response_serializer.data, message="员工排序更新成功", status_code=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"], url_path="(?P<employee_jobcode>[^/.]+)/department")
    def get_department_by_jobcode(self, request: "Request", employee_jobcode: str | None = None) -> "Response":
        """
        根据员工工号查询所在部门

        返回字段:
        - department_code: 部门编码
        - department_name: 部门名称
        - level: 部门层级
        - parent_code: 上级部门编码
        """
        employee = (
            EmployeeSelector.get_employee_by_jobcode(employee_jobcode)
            if employee_jobcode
            else None
        )
        if not employee:
            return error_response(message=f"员工 {employee_jobcode} 不存在", status_code=status.HTTP_404_NOT_FOUND)

        if not employee.employee_department:
            return error_response(message=f"员工 {employee_jobcode} 未分配部门", status_code=status.HTTP_404_NOT_FOUND)

        dept = employee.employee_department
        return success_response(
            data={
                "recordcode": dept.recordcode,
                "department_code": dept.department_code,
                "department_name": dept.department_name,
                "level": dept.level,
                "parent_department_code": dept.parent.department_code if dept.parent else None,
                "path": dept.path,
            }
        )

