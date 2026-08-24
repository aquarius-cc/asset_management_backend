"""
未登记资产管理服务层

该模块提供未登记资产的核心业务逻辑,封装所有写操作:
- 创建未登记资产申请
- 更新未登记资产信息
- 审批并处理未登记资产
- 删除未登记资产

【AGENTS 规范 - Service 层】
- 事务安全:所有写操作使用 @transaction.atomic
- 状态校验:操作前验证状态是否允许
- 审计留痕:关键操作记录操作日志
- 跨应用调用:方法内部延迟导入依赖

【业务流程】
1. 创建申请:用户发现不在账资产,提交申请
2. 审批处理:管理员审批,选择处理方式
   - S1: create_and_recycle / create_and_damaged / reject
   - S2: supplement_and_recycle / reject
   - S3: correct_and_recycle / reject
3. 结果追踪:处理完成后填充 result_* 字段

【跨应用依赖】
- assetmanagement.Asset: 创建资产记录
- assetmanagement.RecycleAsset: 创建回收记录
- assetmanagement.DamagedAsset: 创建待报废记录
- assetmanagement.OutAsset: 补建出库记录(S2场景)
- assetmanagement.state_machine.AssetFSM: 状态转换
- assetmanagement.audit.AuditLogger: 审计日志
"""

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.unregisteredasset.handlers import (
    _handle_s1_create_and_damaged,
    _handle_s1_create_and_recycle,
    _handle_s2_supplement_and_recycle,
    _handle_s3_correct_and_recycle,
    _validate_handle_type,
)
from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.selectors import UnregisteredAssetSelector
from core.exceptions import AppValidationError


logger = logging.getLogger(__name__)


# ==========================================
# 字段白名单:允许更新的字段
# ==========================================
UNREGISTERED_UPDATE_ALLOWED_FIELDS = frozenset(
    [
        "asset_name",
        "asset_brand",
        "asset_specification",
        "unregistered_asset_type",
        "estimated_value",
        "discovery_location",
        "unregistered_asset_storage",
        "handle_description",
        "attachments",
    ]
)


class UnregisteredAssetService:
    """
    未登记资产管理服务

    提供未登记资产全生命周期管理的业务逻辑。
    所有方法均为静态方法,无需实例化。

    【核心方法】
    - create(): 创建未登记资产申请
    - update(): 更新未登记资产信息
    - approve_and_handle(): 审批并处理
    - delete(): 删除未登记资产

    【处理方式】
    - _handle_s1_create_and_recycle(): S1场景创建并回收
    - _handle_s1_create_and_damaged(): S1场景创建并待报废
    - _handle_s2_supplement_and_recycle(): S2场景补建并回收
    - _handle_s3_correct_and_recycle(): S3场景修正并回收

    【异常类型】
    - AppValidationError: 业务校验失败
    - InvalidTransitionError: 状态转换非法(来自 AssetFSM)

    Example:
        >>> from apps.unregisteredasset.services import UnregisteredAssetService
        >>>
        >>> # 创建申请
        >>> asset = UnregisteredAssetService.create({
        ...     'scenario_type': 's1_no_record',
        ...     'asset_name': '笔记本',
        ...     'discovery_date': '2026-05-26',
        ...     'discovery_location': '会议室A',
        ... }, operator_jobcode='EMP001')
        >>>
        >>> # 审批处理
        >>> result = UnregisteredAssetService.approve_and_handle(
        ...     unregistered_code='UNR-20260526-ABC123',
        ...     handle_type='create_and_recycle',
        ...     approver='ADMIN001'
        ... )
    """

    # ===================================================================
    # 公共方法:创建、更新、审批、删除
    # ===================================================================

    @staticmethod
    @transaction.atomic
    def create(data: dict[str, Any], operator_jobcode: str, operator_name: str | None = None) -> UnregisteredAsset:
        """
        创建未登记资产申请

        【AGENTS 规范 - 审计解耦】显式记录操作日志

        Args:
            data: 未登记资产数据,包含:
                - scenario_type: 场景类型(必填)
                - asset_name: 资产名称(必填)
                - discovery_date: 发现日期(必填)
                - discovery_location: 发现地点(必填)
                - asset_brand: 品牌(可选)
                - asset_specification: 规格(可选)
                - unregistered_asset_type: 资产类型(可选)
                - estimated_value: 预估价值(可选)
                - related_asset: 关联资产(S2/S3必填)
                - unregistered_asset_storage: 目标仓库(可选)
                - attachments: 附件列表(可选)
            operator_jobcode: 操作人工号(发现人)
            operator_name: 操作人姓名(可选)

        Returns:
            UnregisteredAsset: 创建的未登记资产记录

        Raises:
            AppValidationError: 参数校验失败时抛出

        Example:
            >>> asset = UnregisteredAssetService.create({
            ...     'scenario_type': 's1_no_record',
            ...     'asset_name': '笔记本',
            ...     'discovery_date': '2026-05-26',
            ...     'discovery_location': '会议室A',
            ... }, operator_jobcode='EMP001')
        """
        # 参数校验
        scenario_type = data.get("scenario_type")
        if not scenario_type:
            raise AppValidationError(detail="场景类型不能为空")

        # S2/S3场景必须关联现有资产
        related_asset = data.get("related_asset")
        if scenario_type in ["s2_no_outasset", "s3_status_mismatch"]:
            if not related_asset:
                raise AppValidationError(detail=f"{scenario_type}场景必须关联现有资产")

        # S1场景不应关联现有资产
        if scenario_type == "s1_no_record" and related_asset:
            raise AppValidationError(detail="S1场景不应关联现有资产")

        # 设置发现人
        from apps.usermanagement.selectors import EmployeeSelector

        discovery_person = EmployeeSelector.get_employee_by_jobcode(operator_jobcode)
        if not discovery_person:
            raise AppValidationError(detail=f"发现人 {operator_jobcode} 不存在")

        data["discovery_person"] = discovery_person

        # 创建记录
        unregistered = UnregisteredAsset.objects.create(**data)

        # 记录审计日志(延迟导入,异常捕获)
        try:
            from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

            UnregisteredAssetAuditAdapter.log_create(
                unregistered=unregistered, operator_jobcode=operator_jobcode, operator_name=operator_name
            )
        except Exception as e:
            # 【P2-10 修复】审计异常记录日志便于排查,但不影响主流程
            logger.warning(f"审计日志记录失败(create): {e}", exc_info=True)

        return unregistered  # type: ignore[no-any-return]

    @staticmethod
    @transaction.atomic
    def update(
        unregistered_code: str, update_data: dict[str, Any], operator_jobcode: str, operator_name: str | None = None
    ) -> UnregisteredAsset:
        """
        更新未登记资产信息

        【AGENTS 规范 - 字段白名单】只允许更新指定字段
        【业务规则】仅待审批状态的记录允许修改

        Args:
            unregistered_code: 未登记资产编码
            update_data: 更新数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名(可选)

        Returns:
            UnregisteredAsset: 更新后的记录

        Raises:
            AppValidationError: 记录不存在、状态不允许或字段不合法时抛出

        Example:
            >>> updated = UnregisteredAssetService.update(
            ...     'UNR-20260526-ABC123',
            ...     {'asset_name': '新名称'},
            ...     operator_jobcode='EMP001'
            ... )
        """
        # 获取记录
        unregistered = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not unregistered:
            raise AppValidationError(detail=f"未登记资产 {unregistered_code} 不存在")

        # 校验状态
        if not unregistered.can_modify():
            raise AppValidationError(detail=f"当前状态 {unregistered.approval_status} 不允许修改")

        # 记录变更前数据
        before_data = {}
        for key in update_data.keys():
            if key in UNREGISTERED_UPDATE_ALLOWED_FIELDS:
                value = getattr(unregistered, key)
                before_data[key] = str(value) if hasattr(value, "pk") else value

        # 字段白名单过滤
        for key, value in update_data.items():
            if key in UNREGISTERED_UPDATE_ALLOWED_FIELDS:
                setattr(unregistered, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}")

        unregistered.save()

        # 记录审计日志(延迟导入,异常捕获)
        try:
            from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

            UnregisteredAssetAuditAdapter.log_update(
                unregistered=unregistered,
                before_data=before_data,
                after_data=update_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
        except Exception as e:
            # 【P2-10 修复】审计异常记录日志便于排查,但不影响主流程
            logger.warning(f"审计日志记录失败(update): {e}", exc_info=True)

        return unregistered

    @staticmethod
    @transaction.atomic
    def approve_and_handle(
        unregistered_code: str,
        handle_type: str,
        approver: str,
        operator_name: str | None = None,
        approval_remark: str = "",
    ) -> dict[str, Any]:
        """
        审批并处理未登记资产

        【AGENTS 规范 - 状态机解耦】显式调用状态机适配器
        【AGENTS 规范 - 审计解耦】显式记录操作日志

        根据场景类型和处理方式执行不同的业务逻辑:
        - S1 + create_and_recycle: 创建资产 → 状态设为 recycled_pending → 创建回收记录
        - S1 + create_and_damaged: 创建资产 → 状态设为 damaged → 创建待报废记录
        - S2 + supplement_and_recycle: 补建出库记录 → 强制回收
        - S3 + correct_and_recycle: 强制回收
        - reject: 拒绝处理,仅更新审批状态

        Args:
            unregistered_code: 未登记资产编码
            handle_type: 处理方式
                - create_and_recycle: 创建并回收
                - create_and_damaged: 创建并报废
                - supplement_and_recycle: 补建并回收
                - correct_and_recycle: 修正并回收
                - reject: 拒绝
            approver: 审批人工号
            operator_name: 审批人姓名(可选)
            approval_remark: 审批备注(可选)

        Returns:
            Dict[str, Any]: 处理结果,包含:
                - action: 执行的操作类型
                - asset_code: 创建的资产编码(如适用)
                - recycle_id: 回收记录ID(如适用)
                - damaged_id: 待报废记录ID(如适用)

        Raises:
            AppValidationError: 状态不允许、处理方式不匹配或处理失败时抛出

        Example:
            >>> result = UnregisteredAssetService.approve_and_handle(
            ...     'UNR-20260526-ABC123',
            ...     handle_type='create_and_recycle',
            ...     approver='ADMIN001'
            ... )
            >>> print(result)
            {'action': 'create_and_recycle', 'asset_code': 'AST-20260526-XXXXXX', 'recycle_id': 1}
        """
        # 获取记录(行级锁,防止并发审批竞态)
        unregistered = UnregisteredAssetSelector.get_by_code_for_update(unregistered_code)
        if not unregistered:
            raise AppValidationError(detail=f"未登记资产 {unregistered_code} 不存在")

        # 校验审批状态
        if unregistered.approval_status != UnregisteredAsset.ApprovalStatus.PENDING:
            raise AppValidationError(detail=f"当前状态 {unregistered.approval_status} 不允许审批")

        # 验证处理方式与场景匹配
        _validate_handle_type(unregistered.scenario_type, handle_type)

        # 设置审批信息
        from apps.usermanagement.selectors import EmployeeSelector

        approver_employee = EmployeeSelector.get_employee_by_jobcode(approver)
        if not approver_employee:
            raise AppValidationError(detail=f"审批人 {approver} 不存在")

        unregistered.handle_type = handle_type
        unregistered.approver = approver_employee
        unregistered.approval_date = timezone.now().date()
        unregistered.approval_remark = approval_remark

        result = {}

        # 根据处理方式执行不同逻辑
        if handle_type == "reject":
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.REJECTED
            result = {"action": "reject"}

        elif handle_type == "create_and_recycle":
            result = _handle_s1_create_and_recycle(unregistered, approver_employee)  # type: ignore[arg-type]
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == "create_and_damaged":
            result = _handle_s1_create_and_damaged(unregistered, approver_employee)  # type: ignore[arg-type]
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == "supplement_and_recycle":
            result = _handle_s2_supplement_and_recycle(unregistered, approver_employee)  # type: ignore[arg-type]
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == "correct_and_recycle":
            result = _handle_s3_correct_and_recycle(unregistered, approver_employee)  # type: ignore[arg-type]
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        unregistered.save()

        # 记录审计日志(延迟导入,异常捕获)
        try:
            from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

            UnregisteredAssetAuditAdapter.log_approve(
                unregistered=unregistered,
                handle_type=handle_type,
                result=result,
                operator_jobcode=approver_employee,  # type: ignore[arg-type]
                operator_name=operator_name,
            )
        except Exception as e:
            # 【P2-10 修复】审计异常记录日志便于排查,但不影响主流程
            logger.warning(f"审计日志记录失败(approve): {e}", exc_info=True)

        return result

    @staticmethod
    @transaction.atomic
    def delete(unregistered_code: str, operator_jobcode: str, operator_name: str | None = None) -> None:
        """
        删除未登记资产(软删除)

        【业务规则】仅待审批状态的记录允许删除

        Args:
            unregistered_code: 未登记资产编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名(可选)

        Raises:
            AppValidationError: 记录不存在或状态不允许删除时抛出

        Example:
            >>> UnregisteredAssetService.delete(
            ...     'UNR-20260526-ABC123',
            ...     operator_jobcode='EMP001'
            ... )
        """
        unregistered = UnregisteredAssetSelector.get_by_code_for_update(unregistered_code)
        if not unregistered:
            raise AppValidationError(detail=f"未登记资产 {unregistered_code} 不存在")

        if not unregistered.can_delete():
            raise AppValidationError(detail=f"当前状态 {unregistered.approval_status} 不允许删除")

        # 记录审计日志(在删除前,延迟导入,异常捕获)
        try:
            from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

            UnregisteredAssetAuditAdapter.log_delete(
                unregistered=unregistered, operator_jobcode=operator_jobcode, operator_name=operator_name
            )
        except Exception as e:
            # 【P2-10 修复】审计异常记录日志便于排查,但不影响主流程
            logger.warning(f"审计日志记录失败(delete): {e}", exc_info=True)

        # 执行软删除
        unregistered.delete()
