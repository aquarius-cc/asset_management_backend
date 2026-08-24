"""
通用审计日志查询视图

【AGENTS 规范 - 架构优化】
提供只读的通用审计日志查询 API,与 AssetOperationLog 结构一致。
支持按应用标识、操作类型、操作人、时间范围等维度查询。

设计原则:
1. 只读接口,不允许修改或删除审计记录
2. 统一响应格式(使用 CustomPageNumberPagination + success_response/error_response)
3. 查询逻辑委托给 AuditLogQueryService,View 仅负责参数解析和响应格式化
"""

from datetime import datetime, timedelta
from typing import Any

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema  # type: ignore[attr-defined]
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit_query_service import AuditLogQueryService
from core.mixins import ResponseWrapperMixin
from core.models_audit import AuditLog
from core.pagination import CustomPageNumberPagination
from utils.response_utils import error_response, success_response


class AuditLogSerializer:
    """审计日志序列化器"""

    def __init__(self, instance: Any, many: bool = False) -> None:
        self.instance = instance
        self.many = many

    @property
    def data(self) -> list[dict[Any, Any]] | dict[Any, Any]:
        if self.many:
            return [self._serialize(log) for log in self.instance]
        return self._serialize(self.instance)

    @staticmethod
    def _serialize(log: AuditLog) -> dict[str, Any]:
        return {
            "pk": log.pk,
            "record_code": log.record_code,
            "app_label": log.app_label,
            "operation_type": log.operation_type,
            "operation_type_display": log.get_operation_type_display(),  # type: ignore[attr-defined]
            "logging_id": log.logging_id,
            "operation_time": log.operation_time.isoformat() if log.operation_time else None,
            "operator_jobcode": log.operator_jobcode,
            "operator_name": log.operator_name,
            "before_data": log.before_data,
            "after_data": log.after_data,
            "description": log.description,
            "ip_address": log.ip_address,
        }


class AuditLogListView(ResponseWrapperMixin, APIView):
    """
    通用审计日志列表查询 API

    【只读接口】
    支持按应用标识、操作类型、操作人、记录编码、时间范围查询审计记录。

    查询参数:
    - app_label: 应用标识(department / employee / authuser)
    - operation_type: 操作类型(create / update / delete / approve / login / logout / permission_change / state_change)
    - operator_jobcode: 操作人工号
    - record_code: 被操作记录编码(精确匹配)
    - start_date: 开始日期(YYYY-MM-DD)
    - end_date: 结束日期(YYYY-MM-DD)
    - days: 最近 N 天(与日期范围互斥)
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="查询通用审计日志",
        description="查询通用审计日志列表,支持多种筛选条件",
        parameters=[
            OpenApiParameter(
                name="app_label",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="应用标识(department / employee / authuser)",
                required=False,
            ),
            OpenApiParameter(
                name="operation_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="操作类型",
                enum=["create", "update", "delete", "approve", "login", "logout", "permission_change", "state_change"],
                required=False,
            ),
            OpenApiParameter(
                name="operator_jobcode",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="操作人工号",
                required=False,
            ),
            OpenApiParameter(
                name="record_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="被操作记录编码(精确匹配)",
                required=False,
            ),
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="开始日期(YYYY-MM-DD)",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="结束日期(YYYY-MM-DD)",
                required=False,
            ),
            OpenApiParameter(
                name="days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="最近N天(与日期范围互斥)",
                required=False,
            ),
        ],
        responses={
            200: {"description": "审计日志列表"},
            400: {"description": "参数错误"},
        },
    )
    def get(self, request: Any) -> Response:
        """获取审计日志列表"""
        app_label = request.query_params.get("app_label")
        operation_type = request.query_params.get("operation_type")
        operator_jobcode = request.query_params.get("operator_jobcode")
        record_code = request.query_params.get("record_code")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        days = request.query_params.get("days")

        # 参数校验:操作类型合法性
        if operation_type:
            valid_types = [choice[0] for choice in AuditLog.OPERATION_TYPE_CHOICES]
            if operation_type not in valid_types:
                return error_response(message=f"无效的操作类型: {operation_type}. 必须是以下之一: {valid_types}")

        # 参数校验与转换:时间条件
        start_time = None
        end_time = None

        if days:
            try:
                days_int = int(days)
                start_time = datetime.now() - timedelta(days=days_int)
            except ValueError:
                return error_response(message="days 参数必须是整数")
        else:
            if start_date:
                try:
                    start_time = datetime.strptime(start_date, "%Y-%m-%d")
                except ValueError:
                    return error_response(message="start_date 格式错误,应为 YYYY-MM-DD")

            if end_date:
                try:
                    end_time = datetime.strptime(end_date, "%Y-%m-%d")
                    end_time = end_time.replace(hour=23, minute=59, second=59)
                except ValueError:
                    return error_response(message="end_date 格式错误,应为 YYYY-MM-DD")

        # 【AGENTS 规范 - P1-09】调用 Service 层执行查询
        logs = AuditLogQueryService.query_logs(
            app_label=app_label,
            operation_type=operation_type,
            operator_jobcode=operator_jobcode,
            record_code=record_code,
            start_time=start_time,
            end_time=end_time,
        )

        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AuditLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AuditLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class AuditLogDetailView(ResponseWrapperMixin, APIView):
    """
    通用审计日志详情 API

    【只读接口】
    获取单条审计记录的详细信息。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取审计日志详情",
        description="根据 ID 获取单条审计记录的详细信息",
        responses={
            200: {"description": "审计记录详情"},
            404: {"description": "记录不存在"},
        },
    )
    def get(self, request: Any, pk: int) -> Response:
        """获取单条审计记录"""
        log = AuditLogQueryService.get_by_pk(pk)

        if not log:
            return error_response(
                message=f"审计记录 {pk} 不存在",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AuditLogSerializer(log)
        return success_response(data=serializer.data)


class AuditLogByLoggingIdView(ResponseWrapperMixin, APIView):
    """
    通过 logging_id 查询审计记录详情 API

    【只读接口】
    根据 logging_id 获取单条审计记录的详细信息。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="通过 logging_id 查询审计日志",
        description="根据 logging_id 获取单条审计记录的详细信息",
        parameters=[
            OpenApiParameter(
                name="logging_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="日志记录唯一标识",
                required=True,
            ),
        ],
        responses={
            200: {"description": "审计记录详情"},
            404: {"description": "记录不存在"},
        },
    )
    def get(self, request: Any, logging_id: str) -> Response:
        """通过 logging_id 获取审计记录"""
        log = AuditLogQueryService.get_by_logging_id(logging_id)

        if not log:
            return error_response(
                message=f"审计记录 {logging_id} 不存在",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AuditLogSerializer(log)
        return success_response(data=serializer.data)


class RecentAuditLogsView(ResponseWrapperMixin, APIView):
    """
    最近审计日志 API

    【只读接口】
    获取最近 N 天的审计日志,用于监控和审计。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取最近审计日志",
        description="获取最近 N 天的审计日志,默认 7 天",
        parameters=[
            OpenApiParameter(
                name="days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="最近 N 天,默认 7 天",
                default=7,
                required=False,
            ),
        ],
        responses={
            200: {"description": "审计日志列表"},
        },
    )
    def get(self, request: Any) -> Response:
        """获取最近审计日志"""
        days = request.query_params.get("days", "7")

        try:
            days_int = int(days)
            if days_int < 1 or days_int > 365:
                return error_response(message="days 参数必须在 1-365 之间")
        except ValueError:
            return error_response(message="days 参数必须是整数")

        logs = AuditLogQueryService.get_recent_logs(days_int)

        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AuditLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AuditLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class AuditLogsByAppLabelView(ResponseWrapperMixin, APIView):
    """
    按应用标识查询审计日志 API

    【只读接口】
    获取指定应用的所有审计日志。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="按应用标识查询审计日志",
        description="获取指定应用的所有审计日志",
        parameters=[
            OpenApiParameter(
                name="app_label",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="应用标识(department / employee / authuser)",
                required=True,
            ),
        ],
        responses={
            200: {"description": "审计日志列表"},
            404: {"description": "该应用没有审计记录"},
        },
    )
    def get(self, request: Any, app_label: str) -> Response:
        """获取指定应用的审计日志"""
        logs = AuditLogQueryService.get_logs_by_app_label(app_label)

        if not logs:
            return error_response(
                message=f"应用 {app_label} 没有审计记录",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AuditLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AuditLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class AuditLogsByOperatorView(ResponseWrapperMixin, APIView):
    """
    按操作人查询审计日志 API

    【只读接口】
    获取指定操作人的所有审计日志。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="按操作人查询审计日志",
        description="获取指定操作人的所有审计日志",
        parameters=[
            OpenApiParameter(
                name="operator_jobcode",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="操作人工号",
                required=True,
            ),
        ],
        responses={
            200: {"description": "审计日志列表"},
            404: {"description": "该操作人没有审计记录"},
        },
    )
    def get(self, request: Any, operator_jobcode: str) -> Response:
        """获取指定操作人的审计日志"""
        logs = AuditLogQueryService.get_logs_by_operator(operator_jobcode)

        if not logs:
            return error_response(
                message=f"操作人 {operator_jobcode} 没有审计记录",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AuditLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AuditLogSerializer(logs, many=True)
        return success_response(data=serializer.data)
