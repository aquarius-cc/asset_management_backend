"""
操作日志查询选择器 - 提供 AssetOperationLog 的只读查询接口,支持多种维度查询。

Class:
  - OperationLogSelector: 操作日志查询选择器
    - get_asset_history: 获取指定资产的完整操作历史
    - get_recent_operations: 获取最近 N 天的操作记录
    - get_operations_by_type: 按操作类型查询记录
    - get_user_operations: 获取指定用户的操作记录
    - get_asset_status_timeline: 获取资产状态变更时间线
    - get_operation_log_by_logging_id / get_operation_log_by_pk: 按ID精确查询
    - query_operation_logs: 多条件组合查询

调用链:
  本模块被 -> OperationLogService, AssetOperationLogListView 等视图调用
  本模块依赖 -> AssetOperationLog(models)
"""

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.assetmanagement.models import AssetOperationLog


class OperationLogSelector:
    """操作日志查询选择器"""

    @staticmethod
    def get_asset_history(asset_code: str) -> list[AssetOperationLog]:
        """获取指定资产的完整操作历史"""
        return list(AssetOperationLog.objects.filter(asset_code=asset_code).order_by("-operation_time"))

    @staticmethod
    def get_recent_operations(days: int = 7) -> list[AssetOperationLog]:
        """获取最近 N 天的操作记录"""
        start_time = timezone.now() - timedelta(days=days)
        return list(AssetOperationLog.objects.filter(operation_time__gte=start_time).order_by("-operation_time"))

    @staticmethod
    def get_operations_by_type(operation_type: str) -> list[AssetOperationLog]:
        """按操作类型查询记录"""
        return list(AssetOperationLog.objects.filter(operation_type=operation_type).order_by("-operation_time"))

    @staticmethod
    def get_user_operations(operator_jobcode: str) -> list[AssetOperationLog]:
        """获取指定用户的操作记录"""
        return list(AssetOperationLog.objects.filter(operator_jobcode=operator_jobcode).order_by("-operation_time"))

    @staticmethod
    def get_asset_status_timeline(asset_code: str) -> list[dict[str, Any]]:
        """获取资产状态变更时间线"""
        logs = AssetOperationLog.objects.filter(
            asset_code=asset_code,
            operation_type__in=["create", "out", "recycle", "damaged", "waste", "approve"],
        ).order_by("operation_time")

        return [
            {
                "time": log.operation_time,
                "operation": log.get_operation_type_display(),
                "operator": log.operator_name or log.operator_jobcode,
                "description": log.description,
                "before_status": log.before_data.get("asset_current_status") if log.before_data else None,
                "after_status": log.after_data.get("asset_current_status") if log.after_data else None,
            }
            for log in logs
        ]

    @staticmethod
    def get_operation_log_by_logging_id(logging_id: str) -> AssetOperationLog | None:
        """根据 LoggingId 查询单条操作记录"""
        try:
            return AssetOperationLog.objects.get(logging_id=logging_id)
        except AssetOperationLog.DoesNotExist:
            return None

    @staticmethod
    def get_operation_log_by_pk(pk: int) -> AssetOperationLog | None:
        """根据主键查询单条操作记录"""
        try:
            return AssetOperationLog.objects.get(pk=pk)
        except AssetOperationLog.DoesNotExist:
            return None

    @staticmethod
    def query_operation_logs(
        asset_code: str | None = None,
        operation_type: str | None = None,
        operator_jobcode: str | None = None,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> list[AssetOperationLog]:
        """多条件组合查询操作记录"""
        queryset = AssetOperationLog.objects.all()

        if asset_code:
            queryset = queryset.filter(asset_code=asset_code)
        if operation_type:
            queryset = queryset.filter(operation_type=operation_type)
        if operator_jobcode:
            queryset = queryset.filter(operator_jobcode=operator_jobcode)
        if start_time:
            queryset = queryset.filter(operation_time__gte=start_time)
        if end_time:
            queryset = queryset.filter(operation_time__lte=end_time)

        return list(queryset.order_by("-operation_time"))
