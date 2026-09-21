"""
资产操作日志服务

【AGENTS 规范 - 架构优化】
提供资产操作日志的记录和查询功能。

设计原则:
1. 所有资产状态变更必须通过此服务记录
2. 支持自动捕获变更前后数据
3. 提供便捷的查询接口

【易错点】
- 操作日志是只读的,创建后不可修改
- 必须在同一事务中创建日志和业务数据
"""

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.assetmanagement.models import Asset, AssetOperationLog
from apps.assetmanagement.selectors.operation_log_selector import OperationLogSelector


logger = logging.getLogger(__name__)


def _to_json_safe(value: Any) -> Any:
    """将审计快照值幂等归一化为 JSON 安全类型(写入收口,DR-1 唯一实现)。

    说明: Django JSONField 入库时无法序列化 date/Decimal/FK 实例等类型,
    此前由各调用方自行归一(如 asset_service._normalize),易遗漏致日志被
    AuditLogger._safe_log 静默吞掉。此处统一收口,对已归一值幂等无副作用。
    """
    if isinstance(value, dict):
        return {key: _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    if hasattr(value, "pk"):
        return str(getattr(value, "recordcode", value.pk))
    if isinstance(value, (Decimal, date, datetime, time, UUID)):
        return str(value)
    return value


def _validate_operation_params(operation_type: str, asset_code: str) -> None:
    """校验操作类型与资产编码(写入入口防呆)"""
    valid_types = [choice[0] for choice in AssetOperationLog.OPERATION_TYPE_CHOICES]
    if operation_type not in valid_types:
        raise ValueError(f"【易错点】无效的操作类型: {operation_type}. 必须是以下之一: {valid_types}")

    # 【易错点】确保资产编码不为空
    if not asset_code:
        raise ValueError("资产编码不能为空")


def _insert_operation_log(
    asset_code: str,
    operation_type: str,
    description: str,
    asset_name: str | None,
    asset_specification: str | None,
    operator_jobcode: str | None,
    operator_name: str | None,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
    related_record_code: str | None,
    related_record_type: str | None,
    ip_address: str | None,
) -> AssetOperationLog:
    """创建日志记录并输出成功日志(写入收口,失败原样重抛)"""
    try:
        log = AssetOperationLog.objects.create(
            asset_code=asset_code,
            asset_name=asset_name,
            asset_specification=asset_specification,
            operation_type=operation_type,
            description=description,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=related_record_code,
            related_record_type=related_record_type,
            ip_address=ip_address,
        )

        logger.info(
            f"【OperationLogService】操作日志记录成功: {asset_code} - {operation_type} - {operator_jobcode}"
        )
        return log

    except Exception as e:
        logger.error(f"【OperationLogService】记录操作日志失败: {e}")
        raise


class OperationLogService:
    """
    资产操作日志服务

    封装操作日志的创建和查询逻辑,确保审计追踪完整性。
    """

    @classmethod
    @transaction.atomic
    def log_operation(
        cls,
        asset_code: str,
        operation_type: str,
        description: str,
        asset_name: str | None = None,
        asset_specification: str | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        related_record_code: str | None = None,
        related_record_type: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产操作日志(须在数据库事务中调用,确保业务数据与日志一致性)。

        校验委托 `_validate_operation_params`,快照归一委托 `_to_json_safe`,
        落库委托 `_insert_operation_log`。参数语义同落库字段,见方法签名。
        """
        _validate_operation_params(operation_type, asset_code)

        # 审计快照写入前统一归一化为 JSON 安全类型(幂等,DR-1)
        before_data = _to_json_safe(before_data) if before_data else before_data
        after_data = _to_json_safe(after_data) if after_data else after_data

        return _insert_operation_log(
            asset_code=asset_code,
            operation_type=operation_type,
            description=description,
            asset_name=asset_name,
            asset_specification=asset_specification,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=related_record_code,
            related_record_type=related_record_type,
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_create(
        cls,
        asset: Asset,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产创建操作"""
        after_data = {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "asset_current_status": asset.asset_current_status,
            "asset_storage": str(asset.asset_storage_recordcode) if asset.asset_storage_recordcode else None,
        }

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.CREATE,
            description=f"资产入库: {asset.asset_name}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            after_data=after_data,
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_update(
        cls,
        asset: Asset,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产更新操作"""
        changed_fields = [key for key, new_value in after_data.items() if before_data.get(key) != new_value]
        description = f"资产信息更新: {', '.join(changed_fields)}" if changed_fields else "资产信息更新"

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.UPDATE,
            description=description,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_delete(
        cls,
        asset_code: str,
        asset_name: str,
        asset: Asset | None = None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产删除操作(软删除)"""
        before_data = None
        asset_specification = None
        if asset:
            before_data = {
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "asset_current_status": asset.asset_current_status,
                "asset_storage": str(asset.asset_storage_recordcode) if asset.asset_storage_recordcode else None,
            }
            asset_specification = asset.asset_specification

        return cls.log_operation(
            asset_code=asset_code,
            asset_name=asset_name,
            asset_specification=asset_specification,
            operation_type=AssetOperationLog.OperationType.DELETE,
            description=f"资产删除(软删除): {asset_name}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_out(
        cls,
        asset: Asset,
        recordcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产出库操作"""
        before_data = {"asset_current_status": Asset.AssetStatus.IN_STORE}
        after_data = {"asset_current_status": Asset.AssetStatus.IN_USE}

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.OUT,
            description=f"资产出库发放: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=recordcode,
            related_record_type="out",
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_recycle(
        cls,
        asset: Asset,
        recordcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产回收操作"""
        before_data = {"asset_current_status": Asset.AssetStatus.IN_USE}
        after_data = {"asset_current_status": Asset.AssetStatus.RECYCLED_PENDING}

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.RECYCLE,
            description=f"资产回收: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=recordcode,
            related_record_type="recycle",
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_damaged(
        cls,
        asset: Asset,
        damaged_record_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产待报废操作"""
        before_data = {"asset_current_status": asset.asset_current_status}
        after_data = {"asset_current_status": Asset.AssetStatus.DAMAGED}

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.DAMAGED,
            description=f"提交报废申请: {damaged_record_code}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=damaged_record_code,
            related_record_type="damaged",
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_waste(
        cls,
        asset: Asset,
        waste_record_code: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
        ip_address: str | None = None,
    ) -> AssetOperationLog:
        """记录资产报废完成操作"""
        before_data = {"asset_current_status": Asset.AssetStatus.DAMAGED}
        after_data = {"asset_current_status": Asset.AssetStatus.SCRAPPED}

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.WASTE,
            description=f"资产报废完成: {waste_record_code}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=waste_record_code,
            related_record_type="waste",
            ip_address=ip_address,
        )

    @classmethod
    def log_asset_approve(
        cls,
        asset: Asset,
        approval_result: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> AssetOperationLog:
        """
        记录资产审批操作

        Args:
            asset: 资产对象
            approval_result: 审批结果(approved/rejected)
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            AssetOperationLog: 创建的操作日志
        """
        result_display = "通过" if approval_result == "approved" else "拒绝"

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.APPROVE,
            description=f"报废审批{result_display}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

    @classmethod
    def log_asset_transfer(
        cls,
        asset: Asset,
        from_storage: str | None,
        to_storage: str | None,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> AssetOperationLog:
        """
        记录资产转移操作

        Args:
            asset: 资产对象
            from_storage: 原仓库
            to_storage: 目标仓库
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            AssetOperationLog: 创建的操作日志
        """
        before_data = {"asset_storage": from_storage}
        after_data = {"asset_storage": to_storage}

        return cls.log_operation(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type=AssetOperationLog.OperationType.TRANSFER,
            description=f"资产转移: {from_storage} → {to_storage}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
        )


class OperationLogQueryService:
    """
    操作日志查询服务

    提供只读查询接口,支持各种维度的操作日志查询。
    统一委托 OperationLogSelector 实现(BR-1/BR-3: 查询收敛至 Selector 层,Service 仅做转发)。
    """

    @staticmethod
    def get_asset_history(user: Any, asset_code: str) -> list[AssetOperationLog]:
        """获取指定资产的完整操作历史"""
        return OperationLogSelector.get_asset_history(user, asset_code)

    @staticmethod
    def get_recent_operations(user: Any, days: int = 7) -> list[AssetOperationLog]:
        """获取最近N天的操作记录"""
        return OperationLogSelector.get_recent_operations(user, days)

    @staticmethod
    def get_operations_by_type(operation_type: str) -> list[AssetOperationLog]:
        """按操作类型查询记录"""
        return OperationLogSelector.get_operations_by_type(operation_type)

    @staticmethod
    def get_user_operations(user: Any, operator_jobcode: str) -> list[AssetOperationLog]:
        """获取指定用户的操作记录"""
        return OperationLogSelector.get_user_operations(user, operator_jobcode)

    @staticmethod
    def get_asset_status_timeline(user: Any, asset_code: str) -> list[dict[str, Any]]:
        """获取资产状态变更时间线"""
        return OperationLogSelector.get_asset_status_timeline(user, asset_code)

    @staticmethod
    def get_operation_log_by_logging_id(user: Any, logging_id: str) -> AssetOperationLog | None:
        """根据 LoggingId 查询操作记录"""
        return OperationLogSelector.get_operation_log_by_logging_id(user, logging_id)

    # 【AGENTS 规范 - P1-09】以下方法为 View 层查询逻辑下沉到 Service 层而新增

    @staticmethod
    def get_operation_log_by_pk(user: Any, pk: int) -> AssetOperationLog | None:
        """【AGENTS 规范 - P1-09】根据主键查询单条操作记录"""
        return OperationLogSelector.get_operation_log_by_pk(user, pk)

    @staticmethod
    def query_operation_logs(
        user: Any,
        asset_code: str | None = None,
        operation_type: str | None = None,
        operator_jobcode: str | None = None,
        start_time: Any | None = None,
        end_time: Any | None = None,
    ) -> list[AssetOperationLog]:
        """【AGENTS 规范 - P1-09】多条件组合查询操作记录"""
        return OperationLogSelector.query_operation_logs(
            user,
            asset_code=asset_code,
            operation_type=operation_type,
            operator_jobcode=operator_jobcode,
            start_time=start_time,
            end_time=end_time,
        )
