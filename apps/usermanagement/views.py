"""
用户管理视图
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.openapi import OpenApiParameter

from .models import Department, Employee
from .serializers import (
    DepartmentSerializer,
    DepartmentTreeSerializer,
    DepartmentMoveSerializer,
    DepartmentBatchSortSerializer,
    DepartmentBatchCreateSerializer,
    DepartmentBatchDeleteSerializer,
    EmployeeSerializer, EmployeeDetailSerializer,
    EmployeeCreateSerializer, EmployeeUpdateSerializer,
    EmployeeSortSerializer,
    EmployeeBatchCreateSerializer,
    EmployeeBatchDeleteSerializer
)
from .selectors import DepartmentSelector, EmployeeSelector
from .services import DepartmentService, EmployeeService
from core.pagination import CustomPageNumberPagination
from utils.response_utils import success_response, error_response
from core.mixins import ResponseWrapperMixin, GetSerializerClassMixin, LoggingMixin

class DepartmentViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ModelViewSet):
    """
    部门管理视图集

    统一使用 ResponseWrapperMixin 确保响应格式一致
    统一使用 LoggingMixin 记录日志
    统一使用 GetSerializerClassMixin 自动选择序列化器

    【修复 S12】管理操作需要管理员权限，防止普通用户创建/修改/删除部门
    """
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    pagination_class = CustomPageNumberPagination

    def get_permissions(self) -> list:
        """
        自定义权限：管理员可管理部门，普通用户只能查看
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['department_name', 'department_code']
    ordering_fields = ['department_code', 'department_name']
    ordering = ['department_code']
    lookup_field = 'department_code'

    @extend_schema(
        operation_id='department_employees_list',
        summary='获取部门员工列表',
        description='获取指定部门下的所有员工列表，支持按状态筛选',
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='员工状态筛选（可选）：active-在职, left-离职, retirement-退休',
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                description='成功获取员工列表',
                examples=[
                    OpenApiExample(
                        '成功响应示例',
                        value={
                            'code': 200,
                            'msg': '操作成功',
                            'data': {
                                'department': {
                                    'department_code': 'D001',
                                    'department_name': '技术部',
                                    'department_information': '张三',
                                    'parent_code': None,
                                    'level': 0,
                                    'sort_order': 0
                                },
                                'employees_count': 15,
                                'employees': [
                                    {
                                        'employee_jobcode': 'E001',
                                        'employee_name': '李四',
                                        'employee_status': 'active',
                                        'employee_department': 'D001',
                                        'employee_phone': '13800138000',
                                        'employee_location': '北京',
                                        'employee_description': '',
                                        'sort_order': 0
                                    }
                                ]
                            }
                        }
                    )
                ]
            ),
            404: OpenApiResponse(description='部门不存在'),
        },
        tags=['部门管理'],
    )
    @action(detail=True, methods=['get'], url_path='employees')
    def employees(self, request, department_code: str = None) -> Response:
        """
        获取指定部门下的所有员工（支持状态筛选）
        
        【AGENTS 规范 - P1-11】使用 EmployeeSelector 替代直接 ORM 调用
        【AGENTS 规范 - 契约驱动】响应格式匹配前端 API 契约
        
        Query Parameters:
            status: 员工状态筛选（可选）
                - active: 在职员工
                - left: 离职员工
                - retirement: 退休员工
        
        Returns:
            {
                "code": 200,
                "msg": "操作成功",
                "data": {
                    "department": {...},
                    "employees_count": 10,
                    "employees": [...]
                }
            }
        """
        try:
            # 获取部门实例（DRF 会根据 lookup_field 自动处理 404）
            department: Department = self.get_object()
            
            # 【AGENTS 规范 - P1-11】使用 Selector 获取员工列表
            employees = EmployeeSelector.get_employees_by_department_instance(department)
            
            # 应用状态筛选
            status_filter: str | None = request.query_params.get('status')
            if status_filter:
                # 验证状态值有效性
                valid_statuses: list[str] = ['active', 'left', 'retirement']
                if status_filter not in valid_statuses:
                    return error_response(
                        message=f'无效的状态值: {status_filter}，有效值为: {", ".join(valid_statuses)}',
                        status_code=status.HTTP_400_BAD_REQUEST
                    )
                employees = employees.filter(employee_status=status_filter)
            
            # 序列化员工数据
            serializer = EmployeeSerializer(employees, many=True)
            
            # 返回统一格式响应
            return success_response(
                data={
                    'department': DepartmentSerializer(department).data,
                    'employees_count': employees.count(),
                    'employees': serializer.data
                },
                message='查询成功'
            )
            
        except Exception as e:
            return error_response(message=str(e))

    # ==================== 部门树形结构相关接口 ====================

    @extend_schema(
        operation_id='department_tree',
        summary='获取部门树',
        description='返回完整的部门树形结构，包含子部门和员工数量统计',
        responses={
            200: OpenApiResponse(
                description='部门树',
                examples=[
                    OpenApiExample(
                        '部门树示例',
                        value={
                            'code': 200,
                            'msg': '操作成功',
                            'data': [
                                {
                                    'department_code': 'D001',
                                    'department_name': '总公司',
                                    'level': 0,
                                    'children': [
                                        {
                                            'department_code': 'D002',
                                            'department_name': '技术部',
                                            'level': 1,
                                            'children': [],
                                            'employee_count': 10
                                        }
                                    ],
                                    'employee_count': 5
                                }
                            ]
                        }
                    )
                ]
            )
        },
        tags=['部门管理'],
    )
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """
        获取部门树形结构

        返回完整的部门树，从根部门开始递归构建。
        每个节点包含：
        - 部门基本信息
        - children: 子部门列表
        - employee_count: 当前部门员工数量
        """
        try:
            tree = DepartmentSelector.build_department_tree()
            return success_response(data=tree)
        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        operation_id='department_children',
        summary='获取子部门',
        description='获取指定部门的直接子部门列表',
        responses={
            200: OpenApiResponse(description='子部门列表'),
            404: OpenApiResponse(description='部门不存在'),
        },
        tags=['部门管理'],
    )
    @action(detail=True, methods=['get'])
    def children(self, request, department_code=None):
        """
        获取指定部门的直接子部门

        Args:
            department_code: 部门编码

        Returns:
            子部门列表，包含员工数量统计
        """
        try:
            department = self.get_object()
            children = DepartmentSelector.get_children(department_code)

            # 构建返回数据
            data = []
            for child in children:
                data.append({
                    'department_code': child.department_code,
                    'department_name': child.department_name,
                    'department_information': child.department_information,
                    'parent_code': child.parent_code,
                    'level': child.level,
                    'sort_order': child.sort_order,
                    'employee_count': child.get_employee_count(),
                })

            return success_response(data={
                'parent': DepartmentSerializer(department).data,
                'children_count': len(data),
                'children': data
            })
        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        operation_id='department_path',
        summary='获取部门路径（面包屑导航）',
        description='获取从根部门到指定部门的完整路径，用于面包屑导航',
        responses={
            200: OpenApiResponse(
                description='部门路径',
                examples=[
                    OpenApiExample(
                        '部门路径示例',
                        value={
                            'code': 200,
                            'msg': '操作成功',
                            'data': {
                                'path': [
                                    {'department_code': 'D001', 'department_name': '总公司', 'level': 0},
                                    {'department_code': 'D002', 'department_name': '技术部', 'level': 1},
                                    {'department_code': 'D005', 'department_name': '前端组', 'level': 2}
                                ]
                            }
                        }
                    )
                ]
            ),
            404: OpenApiResponse(description='部门不存在'),
        },
        tags=['部门管理'],
    )
    @action(detail=True, methods=['get'])
    def path(self, request, department_code=None):
        """
        获取部门路径（面包屑导航）

        【AGENTS 规范 - P3-31】调用 DepartmentSelector.get_department_path()
        获取从根部门到当前部门的完整路径，供前端面包屑导航使用。

        Args:
            department_code: 部门编码

        Returns:
            path: 部门路径列表，从根部门到当前部门
        """
        try:
            department = self.get_object()
            # 【AGENTS 规范 - P3-31】使用 Selector 获取部门路径
            path_departments = DepartmentSelector.get_department_path(department_code)

            path_data = [
                {
                    'department_code': dept.department_code,
                    'department_name': dept.department_name,
                    'department_information': dept.department_information,
                    'parent_code': dept.parent_code,
                    'level': dept.level,
                }
                for dept in path_departments
            ]

            return success_response(data={
                'current': DepartmentSerializer(department).data,
                'path': path_data,
                'depth': len(path_data),
            })
        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        operation_id='department_descendants',
        summary='获取所有后代部门',
        description='递归获取指定部门的所有后代部门（子部门、孙部门等）',
        responses={
            200: OpenApiResponse(
                description='后代部门列表',
                examples=[
                    OpenApiExample(
                        '后代部门示例',
                        value={
                            'code': 200,
                            'msg': '操作成功',
                            'data': {
                                'current': {'department_code': 'D002', 'department_name': '技术部'},
                                'descendants_count': 3,
                                'descendants': [
                                    {'department_code': 'D005', 'department_name': '前端组', 'level': 2},
                                    {'department_code': 'D006', 'department_name': '后端组', 'level': 2}
                                ]
                            }
                        }
                    )
                ]
            ),
            404: OpenApiResponse(description='部门不存在'),
        },
        tags=['部门管理'],
    )
    @action(detail=True, methods=['get'])
    def descendants(self, request, department_code=None):
        """
        获取所有后代部门

        【AGENTS 规范 - P3-32】调用 DepartmentSelector.get_all_descendants()
        递归获取指定部门的所有后代部门，供组织架构展示使用。

        Args:
            department_code: 部门编码

        Returns:
            descendants: 所有后代部门列表（含员工数量统计）
        """
        try:
            department = self.get_object()
            # 【AGENTS 规范 - P3-32】使用 Selector 获取所有后代部门
            descendant_departments = DepartmentSelector.get_all_descendants(department_code)

            descendants_data = [
                {
                    'department_code': dept.department_code,
                    'department_name': dept.department_name,
                    'department_information': dept.department_information,
                    'parent_code': dept.parent_code,
                    'level': dept.level,
                    'sort_order': dept.sort_order,
                    'employee_count': dept.get_employee_count(),
                }
                for dept in descendant_departments
            ]

            return success_response(data={
                'current': DepartmentSerializer(department).data,
                'descendants_count': len(descendants_data),
                'descendants': descendants_data,
            })
        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        operation_id='department_move',
        summary='移动部门',
        description='修改部门的父级关系，支持拖拽排序场景。'
                    '会自动验证循环引用和层级约束（最大6层）',
        request=DepartmentMoveSerializer,
        responses={
            200: OpenApiResponse(
                description='移动成功',
                examples=[
                    OpenApiExample(
                        '移动成功',
                        value={
                            'code': 200,
                            'msg': '部门移动成功',
                            'data': {
                                'department_code': 'D002',
                                'department_name': '技术部',
                                'parent_code': 'D001',
                                'level': 1
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description='参数错误或层级超限'),
            404: OpenApiResponse(description='部门不存在'),
        },
        tags=['部门管理'],
    )
    @action(detail=True, methods=['put'])
    def move(self, request, department_code=None):
        """
        移动部门到新的父部门下

        用于前端拖拽排序场景，支持：
        - 移动到其他部门下
        - 移动成为根部门（target_parent_code 为 null）

        自动验证：
        - 循环引用：不能移动到自己的子部门下
        - 层级约束：移动后不超过 6 层
        """
        try:
            department = self.get_object()

            # 验证请求数据
            serializer = DepartmentMoveSerializer(
                data=request.data,
                context={'department': department}
            )

            if not serializer.is_valid():
                return error_response(
                    message='参数验证失败',
                    errors=serializer.errors
                )

            # 执行移动操作
            target_parent_code = serializer.validated_data.get('target_parent_code')
            updated_department = DepartmentService.move_department(
                department_code=department_code,
                target_parent_code=target_parent_code
            )

            return success_response(
                data=DepartmentSerializer(updated_department).data,
                message='部门移动成功'
            )

        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        operation_id='department_batch_sort',
        summary='批量排序',
        description='批量更新部门的 sort_order 字段，支持前端拖拽排序',
        request=DepartmentBatchSortSerializer,
        responses={
            200: OpenApiResponse(
                description='排序成功',
                examples=[
                    OpenApiExample(
                        '排序成功',
                        value={
                            'code': 200,
                            'msg': '排序更新成功',
                            'data': {
                                'updated_count': 5
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description='参数验证失败'),
        },
        tags=['部门管理'],
    )
    @action(detail=False, methods=['put'])
    def sort(self, request):
        """
        批量更新部门排序

        用于前端拖拽排序后批量保存排序结果。

        请求格式：
        {
            "items": [
                {"department_code": "D001", "sort_order": 1},
                {"department_code": "D002", "sort_order": 2}
            ]
        }
        """
        try:
            serializer = DepartmentBatchSortSerializer(data=request.data)

            if not serializer.is_valid():
                return error_response(
                    message='参数验证失败',
                    errors=serializer.errors
                )

            # 执行批量更新
            items = serializer.validated_data['items']
            updated_count = DepartmentService.batch_update_sort_order(items)

            return success_response(
                data={'updated_count': updated_count},
                message='排序更新成功'
            )

        except Exception as e:
            return error_response(message=str(e))

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        """批量创建部门"""
        serializer = DepartmentBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = DepartmentService.batch_create_department(
            serializer.validated_data['items']
        )

        success_serializer = DepartmentSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量创建完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除部门"""
        serializer = DepartmentBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = DepartmentService.batch_delete_department(
            serializer.validated_data['ids']
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )


class EmployeeViewSet(LoggingMixin, ResponseWrapperMixin, viewsets.ModelViewSet):
    """
    员工管理视图集

    继承 ResponseWrapperMixin 自动处理统一的响应格式：
    - list: 分页/不分页均返回 {code, msg, data}
    - create: 返回 {code, msg, data}
    - retrieve: 返回 {code, msg, data}
    - update/partial_update: 返回 {code, msg, data}
    - destroy: 返回 {code, msg, data}

    自定义 action 中手动调用 success_response/error_response 保持统一格式

    【修复 S12】管理操作需要管理员权限，防止普通用户创建/修改/删除员工
    """
    queryset = Employee.objects.select_related('employee_department').all()
    serializer_class = EmployeeSerializer
    pagination_class = CustomPageNumberPagination

    def get_permissions(self) -> list:
        """
        自定义权限：管理员可管理员工，普通用户只能查看
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['employee_status', 'employee_department__department_code']
    search_fields = ['employee_name', 'employee_jobcode', 'employee_phone']
    ordering_fields = ['employee_jobcode', 'employee_name']
    ordering = ['employee_jobcode']
    lookup_field = 'employee_jobcode'

    # # 利用 GetSerializerClassMixin 选择序列化器,需要先继承 GetSerializerClassMixin
    # GetSerializerClassMixin 已在 mixins.py 中定义，且必须放到viewset.ModelViewSet前面
    # EmployeeViewSet(LoggingMixin, ResponseWrapperMixin,GetSerializerClassMixin,viewsets.ModelViewSet):
    # serializer_action_classes = {
    #     'create': EmployeeCreateSerializer,
    #     'update': EmployeeUpdateSerializer,
    #     'partial_update': EmployeeUpdateSerializer,
    #     'retrieve': EmployeeDetailSerializer,
    # }
    def get_serializer_class(self):
        """根据不同的操作选择不同的序列化器"""
        if self.action == 'create':
            return EmployeeCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return EmployeeUpdateSerializer
        elif self.action == 'retrieve':
            return EmployeeDetailSerializer
        return EmployeeSerializer

    # ---------- 自定义动作 ----------
    @action(detail=False, methods=['get'], url_path='employees/(?P<employee_jobcode>[^/.]+)')
    def get_employee_by_jobcode(self, request, employee_jobcode=None):
        """根据工号查询员工（统一格式）"""
        try:
            employee = get_object_or_404(self.queryset, employee_jobcode=employee_jobcode)
            serializer = EmployeeDetailSerializer(employee)
            return success_response(data=serializer.data)
        except Exception as e:
            return error_response(message=str(e))

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        """批量创建员工"""
        serializer = EmployeeBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EmployeeService.batch_create_employee(
            serializer.validated_data['items']
        )

        success_serializer = EmployeeDetailSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量创建完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        """批量删除员工"""
        serializer = EmployeeBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EmployeeService.batch_delete_employee(
            serializer.validated_data['ids']
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(name='name', type=OpenApiTypes.STR,
                             location=OpenApiParameter.PATH, description='员工名称', required=True),
            OpenApiParameter(name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='page_size', type=OpenApiTypes.INT,
                             location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: EmployeeDetailSerializer(many=True)}
    )
    # @action(detail=False, methods=['get'], url_path='search_by_name/(?P<name>[^/.]+)',
    #         permission_classes=[permissions.IsAuthenticated])
    # def search_by_name(self, request, name=None):
    #     """根据姓名搜索员工（统一格式）"""
    #     try:
    #         if not name:
    #             return error_response(message='请提供姓名查询参数')

    #         queryset = self.queryset.filter(employee_name__icontains=name).distinct()

    #         page = self.paginate_queryset(queryset)
    #         if page is not None:
    #             serializer = self.get_serializer(page, many=True)
    #             # 分页器内部已包装为统一格式
    #             return self.get_paginated_response(serializer.data)

    #         serializer = self.get_serializer(queryset, many=True)
    #         return success_response(data={
    #             'count': len(serializer.data),
    #             'results': serializer.data
    #         })
    #     except Exception as e:
    #         return error_response(message=str(e))

    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        """获取员工统计信息（统一格式）"""
        try:
            # 【AGENTS 规范 - P1-10】统计逻辑迁移到 EmployeeSelector.get_employee_statistics()
            stats = EmployeeSelector.get_employee_statistics()
            return success_response(data=stats)
        except Exception as e:
            return error_response(message=str(e))

    # 显式指定 url_path 后，后端实际路径以 url_path 值为准。
    # @action 装饰器未指定 url_path，会默认使用方法名 active_employees
    @action(detail=False, methods=['get'], url_path='active_employees')
    def active_employees(self, request):
        """获取所有在职员工列表（统一格式）"""
        try:
            # 【AGENTS 规范 - P1-10】使用 EmployeeSelector.get_active_employees() 替代直接 ORM 调用
            queryset = EmployeeSelector.get_active_employees()

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return success_response(data={
                'count': len(serializer.data),
                'results': serializer.data
            })
        except Exception as e:
            return error_response(message=str(e))

    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        """更改员工状态（统一格式）"""
        try:
            employee = self.get_object()
            new_status = request.data.get('status')

            if not new_status:
                return error_response(message='请提供要更改的状态值')

            # 【AGENTS 规范 - P1-10】状态变更逻辑迁移到 EmployeeService.change_employee_status()
            employee = EmployeeService.change_employee_status(employee, new_status)

            serializer = EmployeeDetailSerializer(employee)
            return success_response(data={
                'message': f'员工状态已更改为: {dict(Employee.EMPLOYEE_STATUS_CHOICES)[new_status]}',
                'employee': serializer.data
            })
        except Exception as e:
            return error_response(message=str(e))

    @extend_schema(
        summary='全局模糊搜索员工',
        description=(
            "在员工姓名、工号、手机号、部门名称等关键字段中进行不区分大小写的模糊搜索。\n"
            "✅ 支持中文/英文/数字混合搜索 | ✅ 自动去重 | ✅ 分页返回"),
        parameters=[
            OpenApiParameter(name='keyword', type=OpenApiTypes.STR,
                             location=OpenApiParameter.QUERY, description='搜索关键词', required=True),
            OpenApiParameter(name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='page_size', type=OpenApiTypes.INT,
                             location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: EmployeeSerializer(many=True), 400: OpenApiResponse(description="参数错误")}
    )
    @action(detail=False, methods=['get'], url_path='search',
            permission_classes=[permissions.IsAuthenticated])
    def global_search(self, request):
        """
        全局模糊搜索员工（统一格式）

        【AGENTS 规范 - P3-29】搜索逻辑（含状态别名映射）已迁移到
        EmployeeSelector.search_employees()，视图层仅负责调用 Selector 和分页。
        """
        try:
            keyword = request.query_params.get('keyword', '').strip()
            if not keyword:
                return error_response(message='请提供搜索关键词')

            # 【AGENTS 规范 - P3-29】使用 EmployeeSelector 替代视图层手写 Q 条件
            queryset = EmployeeSelector.search_employees(keyword)

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return success_response(data={
                'count': len(serializer.data),
                'results': serializer.data
            })
        except Exception as e:
            return error_response(message=str(e))

    # 【AGENTS 规范 - P3-44】启用 create() 方法，调用 EmployeeService.create_employee()
    # 实现工号唯一性校验，避免视图层直接 serializer.save() 跳过业务校验
    def create(self, request, *args, **kwargs):
        """
        创建员工

        【AGENTS 规范 - P3-44】通过 EmployeeService.create_employee() 创建，
        Service 层负责工号唯一性校验（抛出 ValidationError），
        视图层仅负责序列化验证和响应格式化。
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # 【AGENTS 规范 - P3-44】调用 Service 层创建，包含工号唯一性校验
            employee = EmployeeService.create_employee(serializer.validated_data)

            return success_response(
                data=EmployeeDetailSerializer(employee).data,
                message='员工创建成功',
                status_code=status.HTTP_201_CREATED
            )
        except Exception as e:
            return error_response(message=str(e))

    @action(detail=False, methods=['put'], url_path='sort',permission_classes=[permissions.IsAuthenticated])
    def batch_sort(self, request):
        """
        批量更新员工排序字段

        【AGENTS 规范 - P3-45】批量更新逻辑已迁移到 EmployeeSelector.batch_update_sort()，
        批量更新员工排序（前端传入列表，每个元素包含 employee_jobcode 和 sort_order）
        视图层仅负责调用 Selector 和返回成功响应。
        """
        try:
            serializer = EmployeeSortSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)

            # 【AGENTS 规范 - P3-45】调用 Selector 批量更新
            updated_employees = EmployeeSelector.batch_update_sort(serializer.validated_data)
            # 返回更新后的员工数据（可选）
            response_serializer = self.get_serializer(updated_employees, many=True)
            return success_response(
                data=serializer.data,
                message='员工排序更新成功',
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return error_response(message=str(e))

    # @action(detail=False, methods=['get'], url_path='employees/(?P<employee_jobcode>[^/.]+)')
    # def get_employee_by_jobcode(self, request, employee_jobcode=None):
    #     """
    #     根据员工工号查询员工详情
    #     接口地址：GET /api/users/employees/{employee_jobcode}
    #     """
    #     employee = get_object_or_404(
    #         self.queryset,
    #         employee_jobcode=employee_jobcode
    #     )
    #     serializer = EmployeeDetailSerializer(employee)
    #     return success_response(data=serializer.data)

    # @extend_schema(
    #     parameters=[
    #         OpenApiParameter(
    #             name='name',
    #             type=OpenApiTypes.STR,
    #             location=OpenApiParameter.PATH,
    #             description='员工名称（用于模糊搜索）',
    #             required=True,
    #         ),
    #         OpenApiParameter(
    #             name='page', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    #             description='页码'
    #         ),
    #         OpenApiParameter(
    #             name='page_size', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY,
    #             description='每页数量（最大100）', default=20
    #         ),
    #     ],
    #     responses={200: EmployeeDetailSerializer(many=True)}
    # )
    # @action(detail=False, methods=['get'], url_path='search_by_name/(?P<name>[^/.]+)', permission_classes=[permissions.IsAuthenticated])
    # def search_by_name(self, request, name=None):
    #     """根据姓名搜索匹配的员工"""
    #     if not name:
    #         return error_response(message='请提供姓名查询参数')

    #     queryset = self.queryset.filter(
    #         Q(employee_name__icontains=name)
    #     ).distinct()

    #     page = self.paginate_queryset(queryset)
    #     if page is not None:
    #         serializer = self.get_serializer(page, many=True)
    #         return self.get_paginated_response(serializer.data)

    #     serializer = self.get_serializer(queryset, many=True)
    #     return success_response(data={
    #         'count': len(serializer.data),
    #         'results': serializer.data
    #     })

    # @action(detail=False, methods=['get'])
    # def statistics(self, request):
    #     """获取员工统计信息"""
    #     total_employees = self.queryset.count()
    #     active_employees = self.queryset.filter(employee_status='active').count()

    #     status_stats = {}
    #     for choice in Employee.EMPLOYEE_STATUS_CHOICES:
    #         status_code = choice[0]
    #         status_name = choice[1]
    #         count = self.queryset.filter(employee_status=status_code).count()
    #         status_stats[status_code] = {
    #             'name': status_name,
    #             'count': count
    #         }

    #     department_stats = {}
    #     departments = Department.objects.all()
    #     for dept in departments:
    #         count = self.queryset.filter(employee_department=dept).count()
    #         department_stats[dept.department_name] = count

    #     return success_response(data={
    #         'total_employees': total_employees,
    #         'active_employees': active_employees,
    #         'by_status': status_stats,
    #         'by_department': department_stats
    #     })

    # @action(detail=False, methods=['get'])
    # def active_employees(self, request):
    #     """获取所有在职员工列表"""
    #     queryset = self.queryset.filter(employee_status='active')
    #     page = self.paginate_queryset(queryset)
    #     if page is not None:
    #         serializer = self.get_serializer(page, many=True)
    #         return self.get_paginated_response(serializer.data)
    #     serializer = self.get_serializer(queryset, many=True)
    #     return success_response(data={
    #         'count': len(serializer.data),
    #         'results': serializer.data
    #     })

    # @action(detail=True, methods=['post'])
    # def change_status(self, request, pk=None):
    #     """更改员工状态"""
    #     employee = self.get_object()
    #     new_status = request.data.get('status')

    #     if new_status not in dict(Employee.EMPLOYEE_STATUS_CHOICES):
    #         return error_response(message='无效的员工状态')

    #     employee.employee_status = new_status
    #     employee.save()

    #     serializer = EmployeeDetailSerializer(employee)
    #     return success_response(data={
    #         'message': f'员工状态已更改为: {dict(Employee.EMPLOYEE_STATUS_CHOICES)[new_status]}',
    #         'employee': serializer.data
    #     })

    # @extend_schema(
    #     summary='全局模糊搜索员工',
    #     description=(
    #         "在员工姓名、工号、手机号、部门名称等关键字段中进行不区分大小写的模糊搜索。\n"
    #         "✅ 支持中文/英文/数字混合搜索 | ✅ 自动去重 | ✅ 分页返回"),
    #     parameters=[
    #         OpenApiParameter(
    #             name='keyword',
    #             type=OpenApiTypes.STR,
    #             location=OpenApiParameter.QUERY,
    #             description='搜索关键词（必填，至少2个字符）',
    #             required=True,
    #         ),
    #         OpenApiParameter(
    #             name='page',
    #             type=OpenApiTypes.INT,
    #             location=OpenApiParameter.QUERY,
    #             description='页码(默认1)'
    #         ),
    #         OpenApiParameter(
    #             name='page_size',
    #             type=OpenApiTypes.INT,
    #             location=OpenApiParameter.QUERY,
    #             description='每页数量（最大500）',
    #             default=20,
    #         ),
    #     ],
    #     responses={200: OpenApiResponse(
    #         description="搜索成功",
    #         response=EmployeeSerializer(many=True)
    #     ),
    #         400: OpenApiResponse(description="参数错误")}
    # )
    # @action(detail=False, methods=['get'], url_path='search', permission_classes=[permissions.IsAuthenticated])
    # def global_search(self, request):
    #     """
    #     全局模糊搜索员工
    #     接口: GET /api/users/search?keyword=关键词
    #     """
    #     keyword = request.query_params.get('keyword', '').strip()

    #     if not keyword:
    #         return error_response(message='请提供搜索关键词')

    #     search_conditions = Q()

    #     text_fields = [
    #         'employee_name',
    #         'employee_jobcode',
    #         'employee_phone',
    #         'employee_description'
    #     ]
    #     for field in text_fields:
    #         search_conditions |= Q(**{f'{field}__icontains': keyword})

    #     search_conditions |= Q(
    #         employee_department__department_name__icontains=keyword
    #     )

    #     search_conditions |= Q(employee_status__icontains=keyword)

    #     status_mapping = {
    #         'active': ['在职', '活动', '激活', '活跃', '在职员工'],
    #         'left': ['离职', '离开', '已离职'],
    #         'retirement': ['退休', '已退休'],
    #         'dismissed': ['辞退', '开除', '解雇'],
    #         'other': ['其他', '其它', '未分类'],
    #     }

    #     matched_codes = set()
    #     for code, aliases in status_mapping.items():
    #         for alias in aliases:
    #             if alias in keyword:
    #                 matched_codes.add(code)
    #                 break

    #     if matched_codes:
    #         search_conditions |= Q(employee_status__in=list(matched_codes))

    #     queryset = (
    #         self.get_queryset()
    #         .select_related('employee_department')
    #         .filter(search_conditions)
    #         .distinct()
    #     )

    #     page = self.paginate_queryset(queryset)
    #     if page is not None:
    #         serializer = self.get_serializer(page, many=True)
    #         return self.get_paginated_response(serializer.data)

    #     serializer = self.get_serializer(queryset, many=True)
    #     return success_response(data={
    #         'count': len(serializer.data),
    #         'results': serializer.data
    #     })
