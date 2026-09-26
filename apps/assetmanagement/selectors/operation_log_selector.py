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

from django.db.models import QuerySet
from django.utils import timezone

from apps.assetmanagement.models import Asset, AssetOperationLog
from core.department_scope import build_asset_owned_department_q, get_department_codes_for_user


class OperationLogSelector:
    """操作日志查询选择器"""

    @staticmethod
    def _scope_by_user(queryset: QuerySet[AssetOperationLog], user: Any) -> QuerySet[AssetOperationLog]:
        """RBAC 行级过滤:按用户部门范围过滤操作日志

        AssetOperationLog.asset_code 为 CharField(非 FK),不能直接复用
        get_asset_linked_queryset_for_user(该函数按 asset_recordcode FK 过滤),
        故经 Asset 三路径归属子查询过滤。归属判定与资产查询单一事实来源一致
        (build_asset_owned_department_q / get_department_codes_for_user)。

        get_department_codes_for_user 语义:
        - None: 无限制(system_admin / auditor / superuser / 无 Employee)
        - 空列表: 无权限(部门级角色但无部门),返回空集
        """
        codes = get_department_codes_for_user(user)
        if codes is None:
            return queryset
        if not codes:
            return queryset.none()
        scoped_asset_codes = Asset.objects.filter(build_asset_owned_department_q(codes)).values("asset_code")
        return queryset.filter(asset_code__in=scoped_asset_codes)

    @staticmethod
    def get_asset_history(user: Any, asset_code: str) -> list[AssetOperationLog]:
        """获取指定资产的完整操作历史"""
        queryset = AssetOperationLog.objects.filter(asset_code=asset_code)
        return list(OperationLogSelector._scope_by_user(queryset, user).order_by("-operation_time"))

    @staticmethod
    def get_recent_operations(user: Any, days: int = 7) -> list[AssetOperationLog]:
        """获取最近 N 天的操作记录"""
        start_time = timezone.now() - timedelta(days=days)
        queryset = AssetOperationLog.objects.filter(operation_time__gte=start_time)
        return list(OperationLogSelector._scope_by_user(queryset, user).order_by("-operation_time"))

    @staticmethod
    def get_operations_by_type(operation_type: str) -> list[AssetOperationLog]:
        """按操作类型查询记录"""
        return list(AssetOperationLog.objects.filter(operation_type=operation_type).order_by("-operation_time"))

    @staticmethod
    def get_user_operations(user: Any, operator_jobcode: str) -> list[AssetOperationLog]:
        """获取指定用户的操作记录"""
        queryset = AssetOperationLog.objects.filter(operator_jobcode=operator_jobcode)
        return list(OperationLogSelector._scope_by_user(queryset, user).order_by("-operation_time"))

    @staticmethod
    def get_asset_status_timeline(user: Any, asset_code: str) -> list[dict[str, Any]]:
        """获取资产状态变更时间线"""
        logs = OperationLogSelector._scope_by_user(
            AssetOperationLog.objects.filter(
                asset_code=asset_code,
                operation_type__in=["create", "out", "recycle", "damaged", "waste", "approve"],
            ),
            user,
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
    def get_operation_log_by_logging_id(user: Any, logging_id: str) -> AssetOperationLog | None:
        """根据 LoggingId 查询单条操作记录"""
        queryset = OperationLogSelector._scope_by_user(AssetOperationLog.objects.filter(logging_id=logging_id), user)
        try:
            return queryset.get()
        except AssetOperationLog.DoesNotExist:
            return None

    @staticmethod
    def get_operation_log_by_pk(user: Any, pk: int) -> AssetOperationLog | None:
        """根据主键查询单条操作记录"""
        queryset = OperationLogSelector._scope_by_user(AssetOperationLog.objects.filter(pk=pk), user)
        try:
            return queryset.get()
        except AssetOperationLog.DoesNotExist:
            return None

    @staticmethod
    def build_operation_logs_queryset(
        user: Any,
        asset_code: str | None = None,
        operation_type: str | None = None,
        operator_jobcode: str | None = None,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> QuerySet[AssetOperationLog]:
        """构建操作日志 queryset（**未物化**），供列表分页与流式导出复用。

        【安全 - 不可省略 user】本方法内**强制**套用 :meth:`_scope_by_user`，
        因此不存在"传入裸 queryset 即可跨部门读取"的路径。行级过滤是
        导出链路的硬约束：漏掉即等同 P1-3 级数据泄露。

        Args:
            user: 请求用户，驱动 ``_scope_by_user`` 的三态判定
                （None 不限 / 空列表零行 / 部门列表过滤）。
            其余参数语义同 :meth:`query_operation_logs`。

        Returns:
            按 ``-operation_time`` 排序、已按用户部门范围过滤的惰性 queryset。
        """
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

        return OperationLogSelector._scope_by_user(queryset, user).order_by("-operation_time")

    @staticmethod
    def query_operation_logs(
        user: Any,
        asset_code: str | None = None,
        operation_type: str | None = None,
        operator_jobcode: str | None = None,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> list[AssetOperationLog]:
        """多条件组合查询操作记录（物化为 list）"""
        return list(
            OperationLogSelector.build_operation_logs_queryset(
                user,
                asset_code=asset_code,
                operation_type=operation_type,
                operator_jobcode=operator_jobcode,
                start_time=start_time,
                end_time=end_time,
            )
        )
