"""
未登记资产管理服务层

该模块提供未登记资产的核心业务逻辑，封装所有写操作：
- 创建未登记资产申请
- 更新未登记资产信息
- 审批并处理未登记资产
- 删除未登记资产

【AGENTS 规范 - Service 层】
- 事务安全：所有写操作使用 @transaction.atomic
- 状态校验：操作前验证状态是否允许
- 审计留痕：关键操作记录操作日志
- 跨应用调用：方法内部延迟导入依赖

【业务流程】
1. 创建申请：用户发现不在账资产，提交申请
2. 审批处理：管理员审批，选择处理方式
   - S1: create_and_recycle / create_and_damaged / reject
   - S2: supplement_and_recycle / reject
   - S3: correct_and_recycle / reject
3. 结果追踪：处理完成后填充 result_* 字段

【跨应用依赖】
- assetmanagement.Asset: 创建资产记录
- assetmanagement.RecycleAsset: 创建回收记录
- assetmanagement.DamagedAsset: 创建待报废记录
- assetmanagement.OutAsset: 补建出库记录（S2场景）
- assetmanagement.state_machine.AssetFSM: 状态转换
- assetmanagement.audit.AuditLogger: 审计日志
"""

import secrets
import string
from typing import Dict, Any, Optional
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import AppValidationError

from .models import UnregisteredAsset
from .selectors import UnregisteredAssetSelector


# ==========================================
# 字段白名单：允许更新的字段
# ==========================================
UNREGISTERED_UPDATE_ALLOWED_FIELDS = frozenset([
    'asset_name',
    'asset_brand',
    'asset_specification',
    'asset_type_code',
    'estimated_value',
    'discovery_location',
    'target_storage_code',
    'handle_description',
    'attachments',
])


class UnregisteredAssetService:
    """
    未登记资产管理服务

    提供未登记资产全生命周期管理的业务逻辑。
    所有方法均为静态方法，无需实例化。

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
    - InvalidTransitionError: 状态转换非法（来自 AssetFSM）

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
        ...     approver_jobcode='ADMIN001'
        ... )
    """

    # ===================================================================
    # 公共方法：创建、更新、审批、删除
    # ===================================================================

    @staticmethod
    @transaction.atomic
    def create(
        data: Dict[str, Any],
        operator_jobcode: str,
        operator_name: Optional[str] = None
    ) -> UnregisteredAsset:
        """
        创建未登记资产申请

        【AGENTS 规范 - 审计解耦】显式记录操作日志

        Args:
            data: 未登记资产数据，包含：
                - scenario_type: 场景类型（必填）
                - asset_name: 资产名称（必填）
                - discovery_date: 发现日期（必填）
                - discovery_location: 发现地点（必填）
                - asset_brand: 品牌（可选）
                - asset_specification: 规格（可选）
                - asset_type_code: 资产类型（可选）
                - estimated_value: 预估价值（可选）
                - related_asset_code: 关联资产（S2/S3必填）
                - target_storage_code: 目标仓库（可选）
                - attachments: 附件列表（可选）
            operator_jobcode: 操作人工号（发现人）
            operator_name: 操作人姓名（可选）

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
        scenario_type = data.get('scenario_type')
        if not scenario_type:
            raise AppValidationError(detail='场景类型不能为空')

        # S2/S3场景必须关联现有资产
        related_asset_code = data.get('related_asset_code')
        if scenario_type in ['s2_no_outasset', 's3_status_mismatch']:
            if not related_asset_code:
                raise AppValidationError(
                    detail=f'{scenario_type}场景必须关联现有资产'
                )

        # S1场景不应关联现有资产
        if scenario_type == 's1_no_record' and related_asset_code:
            raise AppValidationError(
                detail='S1场景不应关联现有资产'
            )

        # 设置发现人
        from apps.usermanagement.models import Employee
        try:
            discovery_person = Employee.objects.get(
                employee_jobcode=operator_jobcode
            )
        except Employee.DoesNotExist:
            raise AppValidationError(detail=f'发现人 {operator_jobcode} 不存在')

        data['discovery_person_jobcode'] = discovery_person

        # 创建记录
        unregistered = UnregisteredAsset.objects.create(**data)

        # 记录审计日志（延迟导入，异常捕获）
        try:
            from .audit_adapter import UnregisteredAssetAuditAdapter
            UnregisteredAssetAuditAdapter.log_create(
                unregistered=unregistered,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )
        except Exception:
            # 审计异常不影响主流程
            pass

        return unregistered

    @staticmethod
    @transaction.atomic
    def update(
        unregistered_code: str,
        update_data: Dict[str, Any],
        operator_jobcode: str,
        operator_name: Optional[str] = None
    ) -> UnregisteredAsset:
        """
        更新未登记资产信息

        【AGENTS 规范 - 字段白名单】只允许更新指定字段
        【业务规则】仅待审批状态的记录允许修改

        Args:
            unregistered_code: 未登记资产编码
            update_data: 更新数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

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
            raise AppValidationError(
                detail=f'未登记资产 {unregistered_code} 不存在'
            )

        # 校验状态
        if not unregistered.can_modify():
            raise AppValidationError(
                detail=f'当前状态 {unregistered.approval_status} 不允许修改'
            )

        # 记录变更前数据
        before_data = {}
        for key in update_data.keys():
            if key in UNREGISTERED_UPDATE_ALLOWED_FIELDS:
                value = getattr(unregistered, key)
                before_data[key] = str(value) if hasattr(value, 'pk') else value

        # 字段白名单过滤
        for key, value in update_data.items():
            if key in UNREGISTERED_UPDATE_ALLOWED_FIELDS:
                setattr(unregistered, key, value)
            else:
                raise AppValidationError(detail=f'不允许修改字段: {key}')

        unregistered.save()

        # 记录审计日志（延迟导入，异常捕获）
        try:
            from .audit_adapter import UnregisteredAssetAuditAdapter
            UnregisteredAssetAuditAdapter.log_update(
                unregistered=unregistered,
                before_data=before_data,
                after_data=update_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )
        except Exception:
            # 审计异常不影响主流程
            pass

        return unregistered

    @staticmethod
    @transaction.atomic
    def approve_and_handle(
        unregistered_code: str,
        handle_type: str,
        approver_jobcode: str,
        operator_name: Optional[str] = None,
        approval_remark: str = ''
    ) -> Dict[str, Any]:
        """
        审批并处理未登记资产

        【AGENTS 规范 - 状态机解耦】显式调用状态机适配器
        【AGENTS 规范 - 审计解耦】显式记录操作日志

        根据场景类型和处理方式执行不同的业务逻辑：
        - S1 + create_and_recycle: 创建资产 → 状态设为 recycled_pending → 创建回收记录
        - S1 + create_and_damaged: 创建资产 → 状态设为 damaged → 创建待报废记录
        - S2 + supplement_and_recycle: 补建出库记录 → 强制回收
        - S3 + correct_and_recycle: 强制回收
        - reject: 拒绝处理，仅更新审批状态

        Args:
            unregistered_code: 未登记资产编码
            handle_type: 处理方式（create_and_recycle/create_and_damaged/supplement_and_recycle/correct_and_recycle/reject）
            approver_jobcode: 审批人工号
            operator_name: 审批人姓名（可选）
            approval_remark: 审批备注（可选）

        Returns:
            Dict[str, Any]: 处理结果，包含：
                - action: 执行的操作类型
                - asset_code: 创建的资产编码（如适用）
                - recycle_id: 回收记录ID（如适用）
                - damaged_id: 待报废记录ID（如适用）

        Raises:
            AppValidationError: 状态不允许、处理方式不匹配或处理失败时抛出

        Example:
            >>> result = UnregisteredAssetService.approve_and_handle(
            ...     'UNR-20260526-ABC123',
            ...     handle_type='create_and_recycle',
            ...     approver_jobcode='ADMIN001'
            ... )
            >>> print(result)
            {'action': 'create_and_recycle', 'asset_code': 'AST-20260526-XXXXXX', 'recycle_id': 1}
        """
        # 获取记录
        unregistered = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not unregistered:
            raise AppValidationError(
                detail=f'未登记资产 {unregistered_code} 不存在'
            )

        # 校验审批状态
        if unregistered.approval_status != UnregisteredAsset.ApprovalStatus.PENDING:
            raise AppValidationError(
                detail=f'当前状态 {unregistered.approval_status} 不允许审批'
            )

        # 验证处理方式与场景匹配
        _validate_handle_type(unregistered.scenario_type, handle_type)

        # 设置审批信息
        from apps.usermanagement.models import Employee
        try:
            approver = Employee.objects.get(employee_jobcode=approver_jobcode)
        except Employee.DoesNotExist:
            raise AppValidationError(detail=f'审批人 {approver_jobcode} 不存在')

        unregistered.handle_type = handle_type
        unregistered.approver_jobcode = approver
        unregistered.approval_date = timezone.now().date()
        unregistered.approval_remark = approval_remark

        result = {}

        # 根据处理方式执行不同逻辑
        if handle_type == 'reject':
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.REJECTED
            result = {'action': 'reject'}

        elif handle_type == 'create_and_recycle':
            result = _handle_s1_create_and_recycle(unregistered, approver_jobcode)
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == 'create_and_damaged':
            result = _handle_s1_create_and_damaged(unregistered, approver_jobcode)
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == 'supplement_and_recycle':
            result = _handle_s2_supplement_and_recycle(unregistered, approver_jobcode)
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        elif handle_type == 'correct_and_recycle':
            result = _handle_s3_correct_and_recycle(unregistered, approver_jobcode)
            unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED

        unregistered.save()

        # 记录审计日志（延迟导入，异常捕获）
        try:
            from .audit_adapter import UnregisteredAssetAuditAdapter
            UnregisteredAssetAuditAdapter.log_approve(
                unregistered=unregistered,
                handle_type=handle_type,
                result=result,
                operator_jobcode=approver_jobcode,
                operator_name=operator_name
            )
        except Exception:
            # 审计异常不影响主流程
            pass

        return result

    @staticmethod
    @transaction.atomic
    def delete(
        unregistered_code: str,
        operator_jobcode: str,
        operator_name: Optional[str] = None
    ) -> None:
        """
        删除未登记资产（软删除）

        【业务规则】仅待审批状态的记录允许删除

        Args:
            unregistered_code: 未登记资产编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名（可选）

        Raises:
            AppValidationError: 记录不存在或状态不允许删除时抛出

        Example:
            >>> UnregisteredAssetService.delete(
            ...     'UNR-20260526-ABC123',
            ...     operator_jobcode='EMP001'
            ... )
        """
        unregistered = UnregisteredAssetSelector.get_by_code(unregistered_code)
        if not unregistered:
            raise AppValidationError(
                detail=f'未登记资产 {unregistered_code} 不存在'
            )

        if not unregistered.can_delete():
            raise AppValidationError(
                detail=f'当前状态 {unregistered.approval_status} 不允许删除'
            )

        # 记录审计日志（在删除前，延迟导入，异常捕获）
        try:
            from .audit_adapter import UnregisteredAssetAuditAdapter
            UnregisteredAssetAuditAdapter.log_delete(
                unregistered=unregistered,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )
        except Exception:
            # 审计异常不影响主流程
            pass

        # 执行软删除
        unregistered.delete()


# ===================================================================
# 内部辅助函数
# ===================================================================

def _validate_handle_type(scenario_type: str, handle_type: str) -> None:
    """
    验证处理方式与场景类型匹配

    Args:
        scenario_type: 场景类型
        handle_type: 处理方式

    Raises:
        AppValidationError: 不匹配时抛出
    """
    valid_mapping = {
        's1_no_record': [
            'create_and_recycle',
            'create_and_damaged',
            'reject'
        ],
        's2_no_outasset': [
            'supplement_and_recycle',
            'reject'
        ],
        's3_status_mismatch': [
            'correct_and_recycle',
            'reject'
        ],
    }

    valid_types = valid_mapping.get(scenario_type, [])
    if handle_type not in valid_types:
        raise AppValidationError(
            detail=f'场景 {scenario_type} 不支持处理方式 {handle_type}，'
            f'有效选项: {", ".join(valid_types)}'
        )


def _generate_asset_code() -> str:
    """
    生成唯一资产编码

    Returns:
        str: 格式为 AST-YYYYMMDD-XXXXXX 的唯一编码
    """
    prefix = 'AST'
    date_str = timezone.now().strftime('%Y%m%d')
    random_suffix = ''.join(
        secrets.choice(string.digits)
        for _ in range(6)
    )
    return f'{prefix}-{date_str}-{random_suffix}'


def _handle_s1_create_and_recycle(
    unregistered: UnregisteredAsset,
    operator_jobcode: str
) -> Dict[str, Any]:
    """
    S1场景：创建资产并回收入库

    步骤：
    1. 创建 Asset 记录（状态默认为 in_store）
    2. 使用状态机适配器设置状态为 recycled_pending
    3. 创建 RecycleAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, RecycleAsset
    from .state_machine_adapter import UnregisteredAssetStateAdapter

    # 1. 创建资产
    asset_data = {
        'asset_code': _generate_asset_code(),
        'asset_name': unregistered.asset_name,
        'asset_brand': unregistered.asset_brand,
        'asset_specification': unregistered.asset_specification,
        'asset_type_code': unregistered.asset_type_code,
        'asset_purchase_price': unregistered.estimated_value or Decimal('0'),
        'asset_purchase_date': unregistered.discovery_date,
        'asset_entry_date': timezone.now().date(),
        'asset_storage_code': unregistered.target_storage_code,
    }
    asset = Asset.objects.create(**asset_data)

    # 2. 使用状态机适配器设置状态
    UnregisteredAssetStateAdapter.create_and_recycle(asset)
    asset.save(update_fields=['asset_current_status'])

    # 3. 创建回收记录
    recycle_data = {
        'recycle_asset_code': asset,
        'recycle_asset_number': 1,
        'recycle_asset_storage_code': unregistered.target_storage_code,
        'recycle_asset_recycle_person_jobcode_id': operator_jobcode,
        'recycle_asset_date': timezone.now().date(),
        'recycle_asset_description': f'不在账资产回收，来源: {unregistered.unregistered_code}',
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    # 4. 更新关联
    unregistered.result_asset_code = asset
    unregistered.result_recycle_code = recycle_asset

    return {
        'action': 'create_and_recycle',
        'asset_code': asset.asset_code,
        'recycle_id': recycle_asset.id,
        # 【AGENTS 规范 - 业务唯一编码】返回回收记录编码供前端使用
        'recycle_record_code': recycle_asset.recycle_record_code,
    }


def _handle_s1_create_and_damaged(
    unregistered: UnregisteredAsset,
    operator_jobcode: str
) -> Dict[str, Any]:
    """
    S1场景：创建资产并进入待报废

    步骤：
    1. 创建 Asset 记录
    2. 使用状态机适配器设置状态为 damaged
    3. 创建 DamagedAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import Asset, DamagedAsset
    from .state_machine_adapter import UnregisteredAssetStateAdapter

    # 1. 创建资产
    asset_data = {
        'asset_code': _generate_asset_code(),
        'asset_name': unregistered.asset_name,
        'asset_brand': unregistered.asset_brand,
        'asset_specification': unregistered.asset_specification,
        'asset_type_code': unregistered.asset_type_code,
        'asset_purchase_price': unregistered.estimated_value or Decimal('0'),
        'asset_purchase_date': unregistered.discovery_date,
        'asset_entry_date': timezone.now().date(),
        'asset_storage_code': unregistered.target_storage_code,
    }
    asset = Asset.objects.create(**asset_data)

    # 2. 使用状态机适配器设置状态
    UnregisteredAssetStateAdapter.create_and_damaged(asset)
    asset.save(update_fields=['asset_current_status'])

    # 3. 创建待报废记录
    damaged_data = {
        'damaged_asset_code': asset,
        'damaged_asset_number': 1,
        'damaged_asset_storage_code': unregistered.target_storage_code,
        'damaged_date': timezone.now().date(),
        'approval_status': 'pending',
        'damaged_asset_description': f'不在账资产待报废，来源: {unregistered.unregistered_code}',
    }
    damaged_asset = DamagedAsset.objects.create(**damaged_data)

    # 4. 更新关联
    unregistered.result_asset_code = asset
    unregistered.result_damaged_code = damaged_asset

    return {
        'action': 'create_and_damaged',
        'asset_code': asset.asset_code,
        'damaged_id': damaged_asset.id,
    }


def _handle_s2_supplement_and_recycle(
    unregistered: UnregisteredAsset,
    operator_jobcode: str
) -> Dict[str, Any]:
    """
    S2场景：补建出库记录并回收

    步骤：
    1. 补建 OutAsset 记录
    2. 使用状态机适配器强制回收
    3. 创建 RecycleAsset 记录
    4. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import OutAsset, RecycleAsset
    from .state_machine_adapter import UnregisteredAssetStateAdapter

    asset = unregistered.related_asset_code
    if not asset:
        raise AppValidationError(detail='S2场景必须有关联资产')

    # 1. 补建出库记录
    outasset_data = {
        'outasset_code': asset,
        'outasset_number': 1,
        'outasset_manager_jobcode_id': operator_jobcode,
        'outasset_using_location': unregistered.discovery_location,
        'outasset_date': unregistered.discovery_date,
        'outasset_type': 'receive',
        'outasset_current_status': 'in_use',
        'outasset_description': f'补建出库记录，来源: {unregistered.unregistered_code}',
    }
    outasset = OutAsset.objects.create(**outasset_data)

    # 2. 强制回收（使用 select_for_update 加锁）
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    UnregisteredAssetStateAdapter.force_recycle(asset)
    asset.asset_storage_code = unregistered.target_storage_code
    asset.save(update_fields=['asset_current_status', 'asset_storage_code'])

    # 3. 创建回收记录
    recycle_data = {
        'outasset_recordcode': outasset,
        'recycle_asset_code': asset,
        'recycle_asset_number': 1,
        'recycle_asset_storage_code': unregistered.target_storage_code,
        'recycle_asset_recycle_person_jobcode_id': operator_jobcode,
        'recycle_asset_date': timezone.now().date(),
        'recycle_asset_description': f'不在账资产回收（补建出库），来源: {unregistered.unregistered_code}',
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    # 4. 更新关联
    unregistered.result_asset_code = asset
    unregistered.result_recycle_code = recycle_asset

    return {
        'action': 'supplement_and_recycle',
        'asset_code': asset.asset_code,
        'outasset_code': outasset.outasset_recordcode,
        'recycle_id': recycle_asset.id,
        # 【AGENTS 规范 - 业务唯一编码】返回回收记录编码供前端使用
        'recycle_record_code': recycle_asset.recycle_record_code,
    }


def _handle_s3_correct_and_recycle(
    unregistered: UnregisteredAsset,
    operator_jobcode: str
) -> Dict[str, Any]:
    """
    S3场景：修正状态并回收

    步骤：
    1. 强制回收（使用状态机适配器）
    2. 创建 RecycleAsset 记录
    3. 更新关联关系

    Args:
        unregistered: 未登记资产记录
        operator_jobcode: 操作人工号

    Returns:
        Dict[str, Any]: 处理结果
    """
    from apps.assetmanagement.models import RecycleAsset
    from .state_machine_adapter import UnregisteredAssetStateAdapter

    asset = unregistered.related_asset_code
    if not asset:
        raise AppValidationError(detail='S3场景必须有关联资产')

    # 1. 强制回收（使用 select_for_update 加锁）
    asset = Asset.objects.select_for_update().get(pk=asset.pk)
    old_status = asset.asset_current_status

    UnregisteredAssetStateAdapter.force_recycle(asset)
    asset.asset_storage_code = unregistered.target_storage_code
    asset.save(update_fields=['asset_current_status', 'asset_storage_code'])

    # 2. 创建回收记录
    recycle_data = {
        'recycle_asset_code': asset,
        'recycle_asset_number': 1,
        'recycle_asset_storage_code': unregistered.target_storage_code,
        'recycle_asset_recycle_person_jobcode_id': operator_jobcode,
        'recycle_asset_date': timezone.now().date(),
        'recycle_asset_description': f'不在账资产回收（状态修正 {old_status}→recycled_pending），来源: {unregistered.unregistered_code}',
    }
    recycle_asset = RecycleAsset.objects.create(**recycle_data)

    # 3. 更新关联
    unregistered.result_asset_code = asset
    unregistered.result_recycle_code = recycle_asset

    return {
        'action': 'correct_and_recycle',
        'asset_code': asset.asset_code,
        'old_status': old_status,
        'recycle_id': recycle_asset.id,
        # 【AGENTS 规范 - 业务唯一编码】返回回收记录编码供前端使用
        'recycle_record_code': recycle_asset.recycle_record_code,
    }


# ===================================================================
# 审计日志说明
# ===================================================================
# 所有审计日志通过 audit_adapter 模块记录
# 导入路径: from .audit_adapter import UnregisteredAssetAuditAdapter
# 
# 支持的操作类型：
# - log_create(): 记录创建操作
# - log_update(): 记录更新操作  
# - log_approve(): 记录审批操作
# - log_delete(): 记录删除操作
#
# 注意：Service 层使用延迟导入 + try/except 包裹，确保审计异常不影响主流程
