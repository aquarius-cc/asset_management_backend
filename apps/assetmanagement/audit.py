"""
操作审计模块

【AGENTS规范 - 显式审计机制】
替代Signal隐式调用,使用显式的上下文管理器和装饰器。

设计原则:
1. 显式调用 - 代码路径清晰可见
2. 简约实现 - 使用标准Python语法,无魔法
3. 事务安全 - 日志记录与业务逻辑在同一事务中
4. 容错设计 - 日志失败不影响主业务流程

使用方式:
    # 方式1: 显式调用
    AuditLogger.log_asset_create(asset, operator)

    # 方式2: 上下文管理器
    with AuditContext('update', asset_code) as ctx:
        asset.save()
        AuditLogger.log_asset_update(asset, before, after, operator)
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any

from django.utils import timezone

from apps.assetmanagement.models.operation_log import AssetOperationLog
from apps.assetmanagement.services.operation_log_service import OperationLogService
from core.request_context import get_current_ip


logger = logging.getLogger(__name__)


@dataclass
class AuditContext:
    """
    审计上下文

    【显式设计】通过with语句使用,日志时机一目了然。
    用于包裹需要记录审计信息的操作块。

    Example:
        with AuditContext('update', asset_code='A001', operator_jobcode='E001') as ctx:
            asset.save()
            AuditLogger.log_asset_update(asset, before, after, operator)
    """

    operation_type: str
    asset_code: str | None = None
    operator_jobcode: str | None = None
    operator_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # 【P2-33 修复】使用 timezone.now() 替代 datetime.now(),兼容 USE_TZ=True
    _start_time: datetime = field(default_factory=timezone.now)

    def __enter__(self) -> None:
        """进入上下文"""
        logger.debug(f"审计开始: {self.operation_type} | 资产: {self.asset_code}")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """退出上下文,记录结果"""
        # 【P2-33 修复】使用 timezone.now() 替代 datetime.now()
        duration = (timezone.now() - self._start_time).total_seconds()

        if exc_type is None:
            logger.info(
                f"审计成功: {self.operation_type} | "
                f"资产: {self.asset_code} | "
                f"操作人: {self.operator_name}({self.operator_jobcode}) | "
                f"耗时: {duration:.3f}s"
            )
        else:
            logger.warning(f"审计异常: {self.operation_type} | 异常: {exc_val} | 耗时: {duration:.3f}s", exc_info=True)
        return False  # 不吞掉异常


class AuditLogger:
    """
    操作日志记录器

    【显式依赖】Service直接调用,调用链清晰可见。
    所有日志方法都保证不抛出异常,不影响主业务流程。
    """

    @staticmethod
    def _safe_log(log_func: Callable, *args, **kwargs) -> bool:
        """
        安全执行日志记录

        【容错设计】日志记录失败不应影响主业务流程。
        """
        try:
            log_func(*args, **kwargs)
            return True
        except Exception as e:
            logger.error(f"日志记录失败: {e}", exc_info=True)
            return False

    @staticmethod
    def log_asset_create(
        asset,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """
        记录资产创建日志
        """
        return AuditLogger._safe_log(
            OperationLogService.log_asset_create,
            asset=asset,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_update(
        asset,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产更新日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_update,
            asset=asset,
            before_data=before_data,
            after_data=after_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_delete(
        asset_code: str,
        asset_name: str,
        asset=None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产删除日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_delete,
            asset_code=asset_code,
            asset_name=asset_name,
            asset=asset,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_state_change(
        asset,
        from_state: str,
        to_state: str,
        trigger: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录状态变更日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_operation,
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.STATE_CHANGE,
            description=f"状态从 {from_state} 变更为 {to_state} (触发: {trigger})",
            before_data={"asset_current_status": from_state},
            after_data={"asset_current_status": to_state},
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_out(
        asset,
        outrecordcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产出库日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_out,
            asset=asset,
            recordcode=outrecordcode,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_recycle(
        asset,
        recordcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产回收日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_recycle,
            asset=asset,
            recordcode=recordcode,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_damaged(
        asset,
        damaged_record_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产报废申请日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_damaged,
            asset=asset,
            damaged_record_code=damaged_record_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_asset_waste(
        asset,
        waste_record_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """记录资产报废完成日志"""
        return AuditLogger._safe_log(
            OperationLogService.log_asset_waste,
            asset=asset,
            waste_record_code=waste_record_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            ip_address=ip_address or get_current_ip(),
        )

    @staticmethod
    def log_operation(
        asset_code: str,
        asset_name: str,
        asset_specification: str | None = None,
        operation_type: str = "delete",
        description: str = "",
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> bool:
        """记录资产操作日志(通用方法)"""
        return AuditLogger._safe_log(
            OperationLogService.log_operation,
            asset_code=asset_code,
            asset_name=asset_name,
            asset_specification=asset_specification,
            operation_type=operation_type,
            description=description,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )


def audit_operation(operation_type: str):
    """
    操作审计装饰器(简化版)

    【适用场景】简单的CRUD操作,无需复杂的前后数据对比。

    【注意】复杂场景建议使用显式 AuditLogger 调用或 AuditContext。

    Example:
        @audit_operation('create')
        def create_asset(asset_data, operator_jobcode=None):
            return Asset.objects.create(**asset_data)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 提取操作人信息
            operator_jobcode = kwargs.get("operator_jobcode")
            operator_name = kwargs.get("operator_name")

            # 执行原方法
            result = func(*args, **kwargs)

            # 记录日志(失败不影响主流程)
            try:
                if operation_type == "create" and hasattr(result, "asset_code"):
                    AuditLogger.log_asset_create(
                        asset=result, operator_jobcode=operator_jobcode, operator_name=operator_name
                    )
                # 其他操作类型...
            except Exception as e:
                logger.error(f"审计装饰器记录失败: {e}")

            return result

        return wrapper

    return decorator
