"""
资产操作记录视图

【AGENTS 规范 - 架构优化】
提供只读的操作记录查询API。

设计原则:
1. 只读接口,不允许修改或删除操作记录
2. 支持多种查询维度(资产、时间、操作类型、操作人)
3. 统一响应格式(使用 CustomPageNumberPagination + success_response/error_response)
"""

from datetime import datetime, timedelta
from typing import Any

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema  # type: ignore[attr-defined]
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assetmanagement.models import AssetOperationLog
from apps.assetmanagement.serializers import AssetOperationLogSerializer
from apps.assetmanagement.services.operation_log_service import OperationLogQueryService
from core.mixins import ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from utils.response_utils import error_response, success_response


class AssetOperationLogListView(ResponseWrapperMixin, APIView):
    """
    资产操作记录列表查询API

    【只读接口】
    支持按资产编码、操作类型、时间范围、操作人查询操作记录。

    查询参数:
    - asset_code: 资产编码(精确匹配)
    - operation_type: 操作类型(create/update/delete/out/recycle/damaged/waste/approve/transfer)
    - operator_jobcode: 操作人工号
    - start_date: 开始日期(YYYY-MM-DD)
    - end_date: 结束日期(YYYY-MM-DD)
    - days: 最近N天(与日期范围互斥)
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="查询资产操作记录",
        description="查询资产全生命周期的操作记录,支持多种筛选条件",
        parameters=[
            OpenApiParameter(
                name="asset_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="资产编码(精确匹配)",
                required=False,
            ),
            OpenApiParameter(
                name="operation_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="操作类型",
                enum=["create", "update", "delete", "out", "recycle", "damaged", "waste", "approve", "transfer"],
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
            200: AssetOperationLogSerializer(many=True),
            400: {"description": "参数错误"},
        },
    )
    def get(self, request: Any) -> Response:
        """获取操作记录列表"""
        # 【AGENTS 规范 - P1-09】View 仅负责参数解析(含校验)和响应格式化,
        # 查询逻辑全部委托给 OperationLogQueryService。

        # 获取查询参数
        asset_code = request.query_params.get("asset_code")
        operation_type = request.query_params.get("operation_type")
        operator_jobcode = request.query_params.get("operator_jobcode")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        days = request.query_params.get("days")

        # 参数校验:操作类型合法性
        if operation_type:
            valid_types = [choice[0] for choice in AssetOperationLog.OPERATION_TYPE_CHOICES]
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
                    # 设置为当天的最后一秒
                    end_time = end_time.replace(hour=23, minute=59, second=59)
                except ValueError:
                    return error_response(message="end_date 格式错误,应为 YYYY-MM-DD")

        # 【AGENTS 规范 - P1-09】调用 Service 层执行查询,View 不直接操作 ORM
        logs = OperationLogQueryService.query_operation_logs(
            asset_code=asset_code,
            operation_type=operation_type,
            operator_jobcode=operator_jobcode,
            start_time=start_time,
            end_time=end_time,
        )

        # 使用 CustomPageNumberPagination 统一分页格式
        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AssetOperationLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AssetOperationLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class AssetOperationLogDetailView(ResponseWrapperMixin, APIView):
    """
    资产操作记录详情API

    【只读接口】
    获取单条操作记录的详细信息。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取操作记录详情",
        description="根据ID获取单条操作记录的详细信息",
        responses={
            200: AssetOperationLogSerializer,
            404: {"description": "记录不存在"},
        },
    )
    def get(self, request: Any, pk: int) -> Response:
        """获取单条操作记录"""
        # 【AGENTS 规范 - P1-09】调用 Service 层查询,View 不直接操作 ORM
        log = OperationLogQueryService.get_operation_log_by_pk(pk)

        if not log:
            return error_response(message=f"操作记录 {pk} 不存在", status_code=status.HTTP_404_NOT_FOUND)

        serializer = AssetOperationLogSerializer(log)
        return success_response(data=serializer.data)


class AssetHistoryView(ResponseWrapperMixin, APIView):
    """
    资产操作历史API

    【只读接口】
    获取指定资产的完整操作历史时间线。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取资产操作历史",
        description="获取指定资产的完整操作历史时间线",
        parameters=[
            OpenApiParameter(
                name="asset_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="资产编码",
                required=True,
            ),
        ],
        responses={
            200: AssetOperationLogSerializer(many=True),
            404: {"description": "资产不存在或没有操作记录"},
        },
    )
    def get(self, request: Any, asset_code: str) -> Response:
        """获取资产操作历史"""

        # 使用服务层查询
        logs = OperationLogQueryService.get_asset_history(asset_code)

        if not logs:
            return error_response(message=f"资产 {asset_code} 没有操作记录", status_code=status.HTTP_404_NOT_FOUND)

        # 使用 CustomPageNumberPagination 统一分页格式
        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AssetOperationLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AssetOperationLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class AssetOperationLogByLoggingIdView(ResponseWrapperMixin, APIView):
    """
    通过 LoggingId 查询操作记录详情 API

    【只读接口】
    根据 LoggingId 获取单条操作记录的详细信息。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="通过 LoggingId 查询操作记录",
        description="根据 LoggingId 获取单条操作记录的详细信息",
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
            200: AssetOperationLogSerializer,
            404: {"description": "记录不存在"},
        },
    )
    def get(self, request: Any, logging_id: str) -> Response:
        """通过 LoggingId 获取操作记录"""
        log = OperationLogQueryService.get_operation_log_by_logging_id(logging_id)

        if not log:
            return error_response(message=f"操作记录 {logging_id} 不存在", status_code=status.HTTP_404_NOT_FOUND)

        serializer = AssetOperationLogSerializer(log)
        return success_response(data=serializer.data)


class AssetStatusTimelineView(ResponseWrapperMixin, APIView):
    """
    资产状态变更时间线API

    【只读接口】
    获取指定资产的状态变更时间线,便于追踪资产流转过程。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取资产状态变更时间线",
        description="获取指定资产的状态变更历史,包含每次状态变更的详细信息",
        parameters=[
            OpenApiParameter(
                name="asset_code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="资产编码",
                required=True,
            ),
        ],
        responses={
            200: {"description": "状态变更时间线"},
            404: {"description": "资产不存在或没有状态变更记录"},
        },
    )
    def get(self, request: Any, asset_code: str) -> Response:
        """获取资产状态变更时间线"""

        timeline = OperationLogQueryService.get_asset_status_timeline(asset_code)

        if not timeline:
            return error_response(message=f"资产 {asset_code} 没有状态变更记录", status_code=status.HTTP_404_NOT_FOUND)

        return success_response(data=timeline)


class RecentOperationsView(ResponseWrapperMixin, APIView):
    """
    最近操作记录API

    【只读接口】
    获取最近N天的操作记录,用于监控和审计。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取最近操作记录",
        description="获取最近N天的操作记录,默认7天",
        parameters=[
            OpenApiParameter(
                name="days",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="最近N天,默认7天",
                default=7,
                required=False,
            ),
        ],
        responses={
            200: AssetOperationLogSerializer(many=True),
        },
    )
    def get(self, request: Any) -> Response:
        """获取最近操作记录"""

        days = request.query_params.get("days", "7")

        try:
            days_int = int(days)
            if days_int < 1 or days_int > 365:
                return error_response(message="days 参数必须在 1-365 之间")
        except ValueError:
            return error_response(message="days 参数必须是整数")

        # 使用服务层查询
        logs = OperationLogQueryService.get_recent_operations(days_int)

        # 使用 CustomPageNumberPagination 统一分页格式
        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AssetOperationLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AssetOperationLogSerializer(logs, many=True)
        return success_response(data=serializer.data)


class UserOperationsView(ResponseWrapperMixin, APIView):
    """
    用户操作记录API

    【只读接口】
    获取指定用户的操作记录,用于审计和操作追踪。
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="获取用户操作记录",
        description="获取指定用户的所有操作记录",
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
            200: AssetOperationLogSerializer(many=True),
            404: {"description": "该用户没有操作记录"},
        },
    )
    def get(self, request: Any, operator_jobcode: str) -> Response:
        """获取用户操作记录"""

        # 使用服务层查询
        logs = OperationLogQueryService.get_user_operations(operator_jobcode)

        if not logs:
            return error_response(
                message=f"用户 {operator_jobcode} 没有操作记录", status_code=status.HTTP_404_NOT_FOUND
            )

        # 使用 CustomPageNumberPagination 统一分页格式
        paginator = CustomPageNumberPagination()
        page = paginator.paginate_queryset(logs, request)

        if page is not None:
            serializer = AssetOperationLogSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)  # type: ignore[no-any-return]

        serializer = AssetOperationLogSerializer(logs, many=True)
        return success_response(data=serializer.data)
