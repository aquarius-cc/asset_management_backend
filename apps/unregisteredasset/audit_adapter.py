"""
未登记资产审计适配器

该模块封装对 assetmanagement.operation_log_service.OperationLogService 的调用，
为 unregisteredasset 应用提供统一的审计日志记录接口。

【设计目的】
1. 解耦：unregisteredasset 不直接依赖 OperationLogService 的具体实现
2. 统一：提供语义化的方法名，统一日志格式
3. 扩展性：可在适配层添加额外的审计逻辑（如发送通知）

【AGENTS 规范 - 适配器模式】
- 单一职责：仅封装审计日志调用，不处理业务逻辑
- 延迟导入：方法内部导入 OperationLogService，避免模块级循环依赖
- 异常处理：捕获并记录日志异常，不影响主流程

【使用方式】
    from .audit_adapter import UnregisteredAssetAuditAdapter

    # 记录创建
    UnregisteredAssetAuditAdapter.log_create(unregistered, operator_jobcode)

    # 记录更新
    UnregisteredAssetAuditAdapter.log_update(unregistered, before_data, after_data, operator_jobcode)

    # 记录审批
    UnregisteredAssetAuditAdapter.log_approve(unregistered, handle_type, result, operator_jobcode)

    # 记录删除
    UnregisteredAssetAuditAdapter.log_delete(unregistered, operator_jobcode)
"""

import logging
from typing import TYPE_CHECKING, Any  # 【P1-34 修复】添加 TYPE_CHECKING 导入


if TYPE_CHECKING:
    from apps.unregisteredasset.models import UnregisteredAsset

# 获取日志记录器
logger = logging.getLogger(__name__)


class UnregisteredAssetAuditAdapter:
    """
    未登记资产审计适配器

    封装审计日志的创建，提供语义化的方法。
    所有方法均为静态方法，无需实例化。

    【方法列表】
    - log_create(): 记录创建操作
    - log_update(): 记录更新操作
    - log_approve(): 记录审批操作
    - log_delete(): 记录删除操作

    【异常处理】
    所有方法捕获异常并记录到日志，不向上抛出，确保不影响主业务流程。

    Example:
        >>> from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter
        >>>
        >>> # 记录创建
        >>> UnregisteredAssetAuditAdapter.log_create(unregistered, 'EMP001')
        >>>
        >>> # 记录审批
        >>> UnregisteredAssetAuditAdapter.log_approve(
        ...     unregistered,
        ...     'create_and_recycle',
        ...     {'asset_code': 'AST001'},
        ...     'ADMIN001'
        ... )
    """

    @staticmethod
    def log_create(unregistered: "UnregisteredAsset", operator_jobcode: str, operator_name: str | None = None) -> None:
        """
        记录未登记资产创建操作

        【调用链】
        此方法 → OperationLogService.log_operation()

        Args:
            unregistered: 未登记资产记录
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

        Example:
            >>> UnregisteredAssetAuditAdapter.log_create(unregistered, 'EMP001')
        """
        try:
            from apps.assetmanagement.services.operation_log_service import OperationLogService

            OperationLogService.log_operation(
                asset_code=unregistered.unregistered_code,
                operation_type="create",
                description=f"创建未登记资产: {unregistered.asset_name}",
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                after_data={
                    "unregistered_code": unregistered.unregistered_code,
                    "scenario_type": unregistered.scenario_type,
                    "asset_name": unregistered.asset_name,
                    "discovery_location": unregistered.discovery_location,
                },
            )
        except Exception as e:
            # 记录日志异常，不影响主流程
            logger.error(f"记录未登记资产创建日志失败: {e}", exc_info=True)

    @staticmethod
    def log_update(
        unregistered: "UnregisteredAsset",
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str,
        operator_name: str | None = None,
    ) -> None:
        """
        记录未登记资产更新操作

        【调用链】
        此方法 → OperationLogService.log_operation()

        Args:
            unregistered: 未登记资产记录
            before_data: 变更前数据
            after_data: 变更后数据
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

        Example:
            >>> UnregisteredAssetAuditAdapter.log_update(
            ...     unregistered,
            ...     {'asset_name': '旧名称'},
            ...     {'asset_name': '新名称'},
            ...     'EMP001'
            ... )
        """
        try:
            from apps.assetmanagement.services.operation_log_service import OperationLogService

            OperationLogService.log_operation(
                asset_code=unregistered.unregistered_code,
                operation_type="update",
                description=f"更新未登记资产: {unregistered.asset_name}",
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                before_data=before_data,
                after_data=after_data,
            )
        except Exception as e:
            logger.error(f"记录未登记资产更新日志失败: {e}", exc_info=True)

    @staticmethod
    def log_approve(
        unregistered: "UnregisteredAsset",
        handle_type: str,
        result: dict[str, Any],
        operator_jobcode: str,
        operator_name: str | None = None,
    ) -> None:
        """
        记录未登记资产审批操作

        【调用链】
        此方法 → OperationLogService.log_operation()

        Args:
            unregistered: 未登记资产记录
            handle_type: 处理方式
            result: 处理结果
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

        Example:
            >>> UnregisteredAssetAuditAdapter.log_approve(
            ...     unregistered,
            ...     'create_and_recycle',
            ...     {'asset_code': 'AST001'},
            ...     'ADMIN001'
            ... )
        """
        try:
            from apps.assetmanagement.services.operation_log_service import OperationLogService

            description = f"审批未登记资产: {handle_type}"
            if result.get("asset_code"):
                description += f", 创建资产: {result['asset_code']}"

            OperationLogService.log_operation(
                asset_code=result.get("asset_code", unregistered.unregistered_code),
                operation_type="approve",
                description=description,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                before_data={
                    "approval_status": "pending",
                    "unregistered_code": unregistered.unregistered_code,
                },
                after_data={
                    "approval_status": unregistered.approval_status,
                    "handle_type": handle_type,
                    "result": result,
                },
            )
        except Exception as e:
            logger.error(f"记录未登记资产审批日志失败: {e}", exc_info=True)

    @staticmethod
    def log_delete(unregistered: "UnregisteredAsset", operator_jobcode: str, operator_name: str | None = None) -> None:
        """
        记录未登记资产删除操作

        【调用链】
        此方法 → OperationLogService.log_operation()

        Args:
            unregistered: 未登记资产记录
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

        Example:
            >>> UnregisteredAssetAuditAdapter.log_delete(unregistered, 'EMP001')
        """
        try:
            from apps.assetmanagement.services.operation_log_service import OperationLogService

            OperationLogService.log_operation(
                asset_code=unregistered.unregistered_code,
                operation_type="delete",
                description=f"删除未登记资产: {unregistered.asset_name}",
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
                before_data={
                    "unregistered_code": unregistered.unregistered_code,
                    "asset_name": unregistered.asset_name,
                    "approval_status": unregistered.approval_status,
                },
            )
        except Exception as e:
            logger.error(f"记录未登记资产删除日志失败: {e}", exc_info=True)
