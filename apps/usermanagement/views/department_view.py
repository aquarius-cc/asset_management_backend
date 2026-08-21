"""
部门管理视图
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.usermanagement.models import Department
from apps.usermanagement.selectors import DepartmentSelector, EmployeeSelector
from apps.usermanagement.serializers import (
    DepartmentBatchCreateSerializer,
    DepartmentBatchDeleteSerializer,
    DepartmentBatchSortSerializer,
    DepartmentMoveSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
)
from apps.usermanagement.services import DepartmentService
from core.mixins import LoggingMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import IsSystemAdmin
from utils.response_utils import error_response, success_response


class DepartmentViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ModelViewSet):
    """
    部门管理视图集

    统一使用 ResponseWrapperMixin 确保响应格式一致
    统一使用 LoggingMixin 记录日志
    统一使用 GetSerializerClassMixin 自动选择序列化器

    【修复 S12】管理操作需要管理员权限,防止普通用户创建/修改/删除部门
    """

    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    pagination_class = CustomPageNumberPagination

    def get_permissions(self) -> list:
        """
        自定义权限:管理员可管理部门,普通用户只能查看
        """
        if self.action in ["create", "update", "partial_update", "destroy", "batch_create", "batch_delete", "sort"]:
            permission_classes = [IsSystemAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["department_name", "department_code"]
    ordering_fields = ["department_code", "department_name"]
    ordering = ["department_code"]
    lookup_field = "department_code"

    @extend_schema(
        operation_id="department_employees_list",
        summary="获取部门员工列表",
        description="获取指定部门下的所有员工列表,支持按状态筛选",
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="员工状态筛选(可选):active-在职, left-离职, retirement-退休",
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(description="成功获取员工列表"),
            404: OpenApiResponse(description="部门不存在"),
        },
        tags=["部门管理"],
    )
    @action(detail=True, methods=["get"], url_path="employees")
    def employees(self, request, department_code: str | None = None) -> Response:
        """
        获取指定部门下的所有员工(支持状态筛选)

        Query Parameters:
            status: 员工状态筛选(可选): active/left/retirement
        """
        department: Department = self.get_object()
        employees = EmployeeSelector.get_employees_by_department_instance(department)

        status_filter: str | None = request.query_params.get("status")
        if status_filter:
            valid_statuses: list[str] = ["active", "left", "retirement"]
            if status_filter not in valid_statuses:
                return error_response(
                    message=f"无效的状态值: {status_filter},有效值为: {', '.join(valid_statuses)}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            employees = employees.filter(employee_status=status_filter)

        serializer = EmployeeSerializer(employees, many=True)
        return success_response(
            data={
                "department": DepartmentSerializer(department).data,
                "employees_count": employees.count(),
                "employees": serializer.data,
            },
            message="查询成功",
        )

    # ==================== 部门树形结构相关接口 ====================

    @extend_schema(
        operation_id="department_tree",
        summary="获取部门树",
        description="返回完整的部门树形结构,包含子部门和员工数量统计",
        responses={200: OpenApiResponse(description="部门树")},
        tags=["部门管理"],
    )
    @action(detail=False, methods=["get"])
    def tree(self, request):
        """获取部门树形结构"""
        tree = DepartmentSelector.build_department_tree()
        return success_response(data=tree)

    @extend_schema(
        operation_id="department_children",
        summary="获取子部门",
        description="获取指定部门的直接子部门列表",
        responses={200: OpenApiResponse(description="子部门列表"), 404: OpenApiResponse(description="部门不存在")},
        tags=["部门管理"],
    )
    @action(detail=True, methods=["get"])
    def children(self, request, department_code=None):
        """获取指定部门的直接子部门"""
        department = self.get_object()
        children = DepartmentSelector.get_children(department_code)

        data = [
            {
                "recordcode": child.recordcode,
                "department_code": child.department_code,
                "department_name": child.department_name,
                "department_information": child.department_information,
                "parent": child.parent_id,
                "parent_department_code": child.parent.department_code if child.parent else None,
                "path": child.path,
                "level": child.level,
                "sort_order": child.sort_order,
                "employee_count": child.get_employee_count(),
            }
            for child in children
        ]

        return success_response(
            data={"parent": DepartmentSerializer(department).data, "children_count": len(data), "children": data}
        )

    @extend_schema(
        operation_id="department_path",
        summary="获取部门路径(面包屑导航)",
        description="获取从根部门到指定部门的完整路径,用于面包屑导航",
        responses={200: OpenApiResponse(description="部门路径"), 404: OpenApiResponse(description="部门不存在")},
        tags=["部门管理"],
    )
    @action(detail=True, methods=["get"])
    def path(self, request, department_code=None):
        """获取部门路径(面包屑导航)"""
        department = self.get_object()
        path_departments = DepartmentSelector.get_department_path(department_code)

        path_data = [
            {
                "recordcode": dept.recordcode,
                "department_code": dept.department_code,
                "department_name": dept.department_name,
                "department_information": dept.department_information,
                "parent": dept.parent_id,
                "path": dept.path,
                "level": dept.level,
            }
            for dept in path_departments
        ]

        return success_response(
            data={
                "current": DepartmentSerializer(department).data,
                "path": path_data,
                "depth": len(path_data),
            }
        )

    @extend_schema(
        operation_id="department_descendants",
        summary="获取所有后代部门",
        description="递归获取指定部门的所有后代部门(子部门、孙部门等)",
        responses={200: OpenApiResponse(description="后代部门列表"), 404: OpenApiResponse(description="部门不存在")},
        tags=["部门管理"],
    )
    @action(detail=True, methods=["get"])
    def descendants(self, request, department_code=None):
        """获取所有后代部门"""
        department = self.get_object()
        descendant_departments = DepartmentSelector.get_all_descendants(department_code)

        descendants_data = [
            {
                "recordcode": dept.recordcode,
                "department_code": dept.department_code,
                "department_name": dept.department_name,
                "department_information": dept.department_information,
                "parent": dept.parent_id,
                "parent_department_code": dept.parent.department_code if dept.parent else None,
                "path": dept.path,
                "level": dept.level,
                "sort_order": dept.sort_order,
                "employee_count": dept.get_employee_count(),
            }
            for dept in descendant_departments
        ]

        return success_response(
            data={
                "current": DepartmentSerializer(department).data,
                "descendants_count": len(descendants_data),
                "descendants": descendants_data,
            }
        )

    @action(detail=True, methods=["get"])
    def parent(self, request, department_code=None):
        """获取父部门信息"""
        department = self.get_object()

        if not department.parent:
            return error_response(
                message=f"部门 {department_code} 是根部门,没有上级部门", status_code=status.HTTP_404_NOT_FOUND
            )

        parent = department.parent
        return success_response(
            data={
                "recordcode": parent.recordcode,
                "department_code": parent.department_code,
                "department_name": parent.department_name,
                "level": parent.level,
                "parent_department_code": parent.parent.department_code if parent.parent else None,
                "path": parent.path,
            }
        )

    @extend_schema(
        operation_id="department_move",
        summary="移动部门",
        description="修改部门的父级关系,支持拖拽排序场景。会自动验证循环引用和层级约束(最大6层)",
        request=DepartmentMoveSerializer,
        responses={
            200: OpenApiResponse(description="移动成功"),
            400: OpenApiResponse(description="参数错误或层级超限"),
            404: OpenApiResponse(description="部门不存在"),
        },
        tags=["部门管理"],
    )
    @action(detail=True, methods=["put"])
    def move(self, request, department_code=None):
        """移动部门到新的父部门下(支持拖拽排序)"""
        department = self.get_object()
        serializer = DepartmentMoveSerializer(data=request.data, context={"department": department})

        if not serializer.is_valid():
            return error_response(message="参数验证失败", errors=serializer.errors)

        target_parent_code = serializer.validated_data.get("target_parent_department_code")
        updated_department = DepartmentService.move_department(
            department_code=department_code, target_parent_code=target_parent_code
        )

        return success_response(data=DepartmentSerializer(updated_department).data, message="部门移动成功")

    @extend_schema(
        operation_id="department_batch_sort",
        summary="批量排序",
        description="批量更新部门的 sort_order 字段,支持前端拖拽排序",
        request=DepartmentBatchSortSerializer,
        responses={200: OpenApiResponse(description="排序成功"), 400: OpenApiResponse(description="参数验证失败")},
        tags=["部门管理"],
    )
    @action(detail=False, methods=["put"])
    def sort(self, request):
        """批量更新部门排序"""
        serializer = DepartmentBatchSortSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(message="参数验证失败", errors=serializer.errors)

        items = serializer.validated_data["items"]
        updated_count = DepartmentService.batch_update_sort_order(items)

        return success_response(data={"updated_count": updated_count}, message="排序更新成功")

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request):
        """批量创建部门"""
        serializer = DepartmentBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = DepartmentService.batch_create_department(serializer.validated_data["items"])

        success_serializer = DepartmentSerializer(result["success_items"], many=True)

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
    def batch_delete(self, request):
        """批量删除部门"""
        serializer = DepartmentBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = DepartmentService.batch_delete_department(serializer.validated_data["ids"])

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
