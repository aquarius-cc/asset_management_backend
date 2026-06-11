"""
资产操作日志服务

【AGENTS 规范 - 架构优化】
提供资产操作日志的记录和查询功能。

设计原则：
1. 所有资产状态变更必须通过此服务记录
2. 支持自动捕获变更前后数据
3. 提供便捷的查询接口

【易错点】
- 操作日志是只读的，创建后不可修改
- 必须在同一事务中创建日志和业务数据
"""

import logging
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.utils import timezone

from .models import AssetOperationLog, Asset

logger = logging.getLogger(__name__)


class OperationLogService:
    """
    资产操作日志服务
    
    封装操作日志的创建和查询逻辑，确保审计追踪完整性。
    """
    
    @classmethod
    @transaction.atomic
    def log_operation(
        cls,
        asset_code: str,
        operation_type: str,
        description: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
        related_record_code: Optional[str] = None,
        related_record_type: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产操作日志
        
        【重要】必须在数据库事务中调用此方法，确保业务数据和日志的一致性。
        
        Args:
            asset_code: 资产编码
            operation_type: 操作类型（create/update/delete/out/recycle/damaged/waste/approve/transfer）
            description: 操作描述
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            before_data: 变更前数据（JSON格式）
            after_data: 变更后数据（JSON格式）
            related_record_code: 关联记录编码
            related_record_type: 关联记录类型
            ip_address: 操作IP地址
            
        Returns:
            AssetOperationLog: 创建的操作日志记录
            
        Raises:
            ValueError: 参数验证失败
            
        Example:
            >>> OperationLogService.log_operation(
            ...     asset_code="ASSET001",
            ...     operation_type="out",
            ...     description="资产出库发放",
            ...     operator_jobcode="EMP001",
            ...     operator_name="张三",
            ...     after_data={"status": "in_use", "location": "办公室A"},
            ...     related_record_code="OUT-20250101-XXXX",
            ...     related_record_type="out",
            ... )
        """
        # 验证操作类型
        valid_types = [choice[0] for choice in AssetOperationLog.OPERATION_TYPE_CHOICES]
        if operation_type not in valid_types:
            raise ValueError(
                f"【易错点】无效的操作类型: {operation_type}. "
                f"必须是以下之一: {valid_types}"
            )
        
        # 【易错点】确保资产编码不为空
        if not asset_code:
            raise ValueError("资产编码不能为空")
        
        try:
            log = AssetOperationLog.objects.create(
                asset_code=asset_code,
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
                f"【OperationLogService】操作日志记录成功: "
                f"{asset_code} - {operation_type} - {operator_jobcode}"
            )
            return log
            
        except Exception as e:
            logger.error(f"【OperationLogService】记录操作日志失败: {e}")
            raise
    
    @classmethod
    def log_asset_create(
        cls,
        asset: Asset,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产创建操作
        
        Args:
            asset: 创建的资产对象
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        after_data = {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "asset_current_status": asset.asset_current_status,
            "asset_storage_code": str(asset.asset_storage_code) if asset.asset_storage_code else None,
        }
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="create",
            description=f"资产入库: {asset.asset_name}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            after_data=after_data,
        )
    
    @classmethod
    def log_asset_update(
        cls,
        asset: Asset,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产更新操作
        
        Args:
            asset: 更新的资产对象
            before_data: 变更前的数据
            after_data: 变更后的数据
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        # 识别变更的字段
        changed_fields = []
        for key, new_value in after_data.items():
            old_value = before_data.get(key)
            if old_value != new_value:
                changed_fields.append(key)
        
        description = f"资产信息更新: {', '.join(changed_fields)}" if changed_fields else "资产信息更新"
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="update",
            description=description,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
        )
    
    @classmethod
    def log_asset_delete(
        cls,
        asset_code: str,
        asset_name: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产删除操作（软删除）
        
        Args:
            asset_code: 资产编码
            asset_name: 资产名称
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        return cls.log_operation(
            asset_code=asset_code,
            operation_type="delete",
            description=f"资产删除(软删除): {asset_name}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
    
    @classmethod
    def log_asset_out(
        cls,
        asset: Asset,
        outasset_recordcode: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产出库操作
        
        Args:
            asset: 资产对象
            outasset_recordcode: 出库记录编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        before_data = {"asset_current_status": "in_store"}
        after_data = {"asset_current_status": "in_use"}
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="out",
            description=f"资产出库发放: {outasset_recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=outasset_recordcode,
            related_record_type="out",
        )
    
    @classmethod
    def log_asset_recycle(
        cls,
        asset: Asset,
        recycle_record_code: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产回收操作
        
        Args:
            asset: 资产对象
            recycle_record_code: 回收记录编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        before_data = {"asset_current_status": "in_use"}
        after_data = {"asset_current_status": "recycled_pending"}
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="recycle",
            description=f"资产回收: {recycle_record_code}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=recycle_record_code,
            related_record_type="recycle",
        )
    
    @classmethod
    def log_asset_damaged(
        cls,
        asset: Asset,
        damaged_record_code: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产待报废操作
        
        Args:
            asset: 资产对象
            damaged_record_code: 待报废记录编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        before_data = {"asset_current_status": asset.asset_current_status}
        after_data = {"asset_current_status": "damaged"}
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="damaged",
            description=f"提交报废申请: {damaged_record_code}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=damaged_record_code,
            related_record_type="damaged",
        )
    
    @classmethod
    def log_asset_waste(
        cls,
        asset: Asset,
        waste_record_code: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产报废完成操作
        
        Args:
            asset: 资产对象
            waste_record_code: 报废记录编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        before_data = {"asset_current_status": "damaged"}
        after_data = {"asset_current_status": "scrapped"}
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="waste",
            description=f"资产报废完成: {waste_record_code}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
            related_record_code=waste_record_code,
            related_record_type="waste",
        )
    
    @classmethod
    def log_asset_approve(
        cls,
        asset: Asset,
        approval_result: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
    ) -> AssetOperationLog:
        """
        记录资产审批操作
        
        Args:
            asset: 资产对象
            approval_result: 审批结果（approved/rejected）
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名
            
        Returns:
            AssetOperationLog: 创建的操作日志
        """
        result_display = "通过" if approval_result == "approved" else "拒绝"
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="approve",
            description=f"报废审批{result_display}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
    
    @classmethod
    def log_asset_transfer(
        cls,
        asset: Asset,
        from_storage: Optional[str],
        to_storage: Optional[str],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None,
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
        before_data = {"asset_storage_code": from_storage}
        after_data = {"asset_storage_code": to_storage}
        
        return cls.log_operation(
            asset_code=asset.asset_code,
            operation_type="transfer",
            description=f"资产转移: {from_storage} → {to_storage}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            before_data=before_data,
            after_data=after_data,
        )


class OperationLogQueryService:
    """
    操作日志查询服务
    
    提供只读查询接口，支持各种维度的操作日志查询。
    """
    
    @staticmethod
    def get_asset_history(asset_code: str) -> List[AssetOperationLog]:
        """
        获取指定资产的完整操作历史
        
        Args:
            asset_code: 资产编码
            
        Returns:
            List[AssetOperationLog]: 按时间倒序排列的操作记录
        """
        return list(
            AssetOperationLog.objects.filter(asset_code=asset_code)
            .order_by("-operation_time")
        )
    
    @staticmethod
    def get_recent_operations(days: int = 7) -> List[AssetOperationLog]:
        """
        获取最近N天的操作记录
        
        Args:
            days: 天数，默认7天
            
        Returns:
            List[AssetOperationLog]: 最近的操作记录
        """
        from datetime import timedelta
        start_time = timezone.now() - timedelta(days=days)
        return list(
            AssetOperationLog.objects.filter(operation_time__gte=start_time)
            .order_by("-operation_time")
        )
    
    @staticmethod
    def get_operations_by_type(operation_type: str) -> List[AssetOperationLog]:
        """
        按操作类型查询记录
        
        Args:
            operation_type: 操作类型代码
            
        Returns:
            List[AssetOperationLog]: 指定类型的操作记录
        """
        return list(
            AssetOperationLog.objects.filter(operation_type=operation_type)
            .order_by("-operation_time")
        )
    
    @staticmethod
    def get_user_operations(operator_jobcode: str) -> List[AssetOperationLog]:
        """
        获取指定用户的操作记录
        
        Args:
            operator_jobcode: 操作人工号
            
        Returns:
            List[AssetOperationLog]: 该用户的操作记录
        """
        return list(
            AssetOperationLog.objects.filter(operator_jobcode=operator_jobcode)
            .order_by("-operation_time")
        )
    
    @staticmethod
    def get_asset_status_timeline(asset_code: str) -> List[Dict[str, Any]]:
        """
        获取资产状态变更时间线
        
        Args:
            asset_code: 资产编码
            
        Returns:
            List[Dict]: 状态变更记录列表
        """
        logs = AssetOperationLog.objects.filter(
            asset_code=asset_code,
            operation_type__in=["create", "out", "recycle", "damaged", "waste", "approve"]
        ).order_by("operation_time")
        
        timeline = []
        for log in logs:
            timeline.append({
                "time": log.operation_time,
                "operation": log.get_operation_type_display(),
                "operator": log.operator_name or log.operator_jobcode,
                "description": log.description,
                "before_status": log.before_data.get("asset_current_status") if log.before_data else None,
                "after_status": log.after_data.get("asset_current_status") if log.after_data else None,
            })
        
        return timeline

    @staticmethod
    def get_operation_log_by_logging_id(logging_id: str) -> Optional[AssetOperationLog]:
        """
        根据 LoggingId 查询操作记录

        Args:
            logging_id: 日志记录唯一标识

        Returns:
            Optional[AssetOperationLog]: 操作记录实例或 None
        """
        try:
            return AssetOperationLog.objects.get(logging_id=logging_id)
        except AssetOperationLog.DoesNotExist:
            return None

    # 【AGENTS 规范 - P1-09】以下方法为 View 层查询逻辑下沉到 Service 层而新增

    @staticmethod
    def get_operation_log_by_pk(pk: int) -> Optional[AssetOperationLog]:
        """
        【AGENTS 规范 - P1-09】根据主键查询单条操作记录

        将 View 层的直接 ORM 查询下沉到 Service 层，
        View 仅负责参数解析和响应格式化。

        Args:
            pk: 操作记录主键ID

        Returns:
            Optional[AssetOperationLog]: 操作记录实例或 None
        """
        try:
            return AssetOperationLog.objects.get(pk=pk)
        except AssetOperationLog.DoesNotExist:
            return None

    @staticmethod
    def query_operation_logs(
        asset_code: Optional[str] = None,
        operation_type: Optional[str] = None,
        operator_jobcode: Optional[str] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
    ) -> List[AssetOperationLog]:
        """
        【AGENTS 规范 - P1-09】多条件组合查询操作记录

        将 View 层的 ORM 查询构建逻辑下沉到 Service 层，
        View 仅负责参数解析（含校验）和响应格式化。

        Args:
            asset_code: 资产编码（精确匹配）
            operation_type: 操作类型
            operator_jobcode: 操作人工号
            start_time: 起始时间（datetime 实例）
            end_time: 截止时间（datetime 实例）

        Returns:
            List[AssetOperationLog]: 按时间倒序排列的操作记录
        """
        from datetime import timedelta

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
