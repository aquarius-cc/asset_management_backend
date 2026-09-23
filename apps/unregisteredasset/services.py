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
from core.constants import MAX_BATCH_SIZE
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


def _validate_create_scenario(data: dict[str, Any]) -> None:
    """校验创建场景类型契约: S2/S3 必关联现有资产, S1 禁关联"""
    scenario_type = data.get("scenario_type")
    if not scenario_type:
        raise AppValidationError(detail="场景类型不能为空")

    related_asset = data.get("related_asset")
    if scenario_type in ["s2_no_outasset", "s3_status_mismatch"]:
        if not related_asset:
            raise AppValidationError(detail=f"{scenario_type}场景必须关联现有资产")

    if scenario_type == "s1_no_record" and related_asset:
        raise AppValidationError(detail="S1场景不应关联现有资产")


def _safe_call_audit(operation: str, *args: Any, **kwargs: Any) -> None:
    """安全调用审计适配器(延迟导入,异常捕获,失败不影响主流程)"""
    try:
        from apps.unregisteredasset.audit_adapter import UnregisteredAssetAuditAdapter

        getattr(UnregisteredAssetAuditAdapter, f"log_{operation}")(*args, **kwargs)
    except Exception as e:
        # 【P2-10 修复】审计异常记录日志便于排查,但不影响主流程
        logger.warning(f"审计日志记录失败({operation}): {e}", exc_info=True)


def _log_create_audit(unregistered: UnregisteredAsset, operator_jobcode: str, operator_name: str | None = None) -> None:
    """记录创建审计日志(委托 _safe_call_audit)"""
    _safe_call_audit(
        "create", unregistered=unregistered, operator_jobcode=operator_jobcode, operator_name=operator_name
    )


def _apply_whitelist_edits(unregistered: UnregisteredAsset, update_data: dict[str, Any]) -> None:
    """字段白名单过滤: 非白名单字段直接抛错"""
    for key, value in update_data.items():
        if key in UNREGISTERED_UPDATE_ALLOWED_FIELDS:
            setattr(unregistered, key, value)
        else:
            raise AppValidationError(detail=f"不允许修改字段: {key}")


def _log_update_audit(
    unregistered: UnregisteredAsset,
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    operator_jobcode: str,
    operator_name: str | None = None,
) -> None:
    """记录更新审计日志(委托 _safe_call_audit)"""
    _safe_call_audit(
        "update",
        unregistered=unregistered,
        before_data=before_data,
        after_data=after_data,
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
    )


def _prepare_approval(
    unregistered_code: str, handle_type: str, approver: str, approval_remark: str
) -> tuple[UnregisteredAsset, Any]:
    """审批前置: 行锁获取+状态校验+类型匹配+审批人解析+字段设置"""
    unregistered = UnregisteredAssetSelector.get_by_code_for_update(unregistered_code)
    if not unregistered:
        raise AppValidationError(detail=f"未登记资产 {unregistered_code} 不存在")

    if unregistered.approval_status != UnregisteredAsset.ApprovalStatus.PENDING:
        raise AppValidationError(detail=f"当前状态 {unregistered.approval_status} 不允许审批")

    _validate_handle_type(unregistered.scenario_type, handle_type)

    from apps.usermanagement.selectors import EmployeeSelector

    approver_employee = EmployeeSelector.get_employee_by_jobcode(approver)
    if not approver_employee:
        raise AppValidationError(detail=f"审批人 {approver} 不存在")

    unregistered.handle_type = handle_type
    unregistered.approver = approver_employee
    unregistered.approval_date = timezone.now().date()
    unregistered.approval_remark = approval_remark

    return unregistered, approver_employee


def _execute_handle(unregistered: UnregisteredAsset, handle_type: str, approver_employee: Any) -> dict[str, Any]:
    """处理方式五分支派发: reject 不设 APPROVED, 其余设 APPROVED 后 save"""
    result: dict[str, Any] = {}
    if handle_type == "reject":
        unregistered.approval_status = UnregisteredAsset.ApprovalStatus.REJECTED
        result = {"action": "reject"}
    elif handle_type == "create_and_recycle":
        result = _handle_s1_create_and_recycle(unregistered, approver_employee)
        unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED
    elif handle_type == "create_and_damaged":
        result = _handle_s1_create_and_damaged(unregistered, approver_employee)
        unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED
    elif handle_type == "supplement_and_recycle":
        result = _handle_s2_supplement_and_recycle(unregistered, approver_employee)
        unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED
    elif handle_type == "correct_and_recycle":
        result = _handle_s3_correct_and_recycle(unregistered, approver_employee)
        unregistered.approval_status = UnregisteredAsset.ApprovalStatus.APPROVED
    unregistered.save()
    return result


def _log_approve_audit(
    unregistered: UnregisteredAsset,
    handle_type: str,
    result: dict[str, Any],
    approver_employee: Any,
    operator_name: str | None = None,
) -> None:
    """记录审批审计日志(委托 _safe_call_audit)"""
    _safe_call_audit(
        "approve",
        unregistered=unregistered,
        handle_type=handle_type,
        result=result,
        operator_jobcode=approver_employee,
        operator_name=operator_name,
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
    def create(
        data: dict[str, Any],
        operator_jobcode: str,
        operator_name: str | None = None,
        discovery_person_jobcode: str | None = None,
    ) -> UnregisteredAsset:
        """创建未登记资产申请

        场景契约见 `_validate_create_scenario`, 审批人解析见 `_log_create_audit`。

        Args:
            data: 未登记资产数据,包含 scenario_type 等字段
            operator_jobcode: 操作人工号(当前操作人,写入审计日志, 语义5 与发现人解耦)
            operator_name: 操作人姓名(可选)
            discovery_person_jobcode: 发现人工号(可选,默认=操作人;代录白名单
                (仅 system_admin 可传非本人)在 View 层校验,Service 不重复实现 DR-1)

        Raises:
            AppValidationError: 参数校验失败或发现人工号不存在时抛出
        """
        _validate_create_scenario(data)

        # 设置发现人(代录时为目标工号,否则=操作人)
        from apps.usermanagement.selectors import EmployeeSelector

        target_jobcode = discovery_person_jobcode or operator_jobcode
        discovery_person = EmployeeSelector.get_employee_by_jobcode(target_jobcode)
        if not discovery_person:
            raise AppValidationError(detail=f"发现人 {target_jobcode} 不存在")

        data["discovery_person"] = discovery_person

        # 创建记录
        unregistered = UnregisteredAsset.objects.create(**data)

        # 记录审计日志(延迟导入,异常捕获) — operator 恒为当前操作人
        _log_create_audit(unregistered, operator_jobcode, operator_name)

        return unregistered  # type: ignore[no-any-return]

    @staticmethod
    def batch_create_unregistered(
        data_list: list[dict[str, Any]], operator_jobcode: str, operator_name: str | None = None
    ) -> dict[str, Any]:
        """批量创建未登记资产申请

        【D-1 收敛】视图层手写循环(views.batch_create)下沉至 Service,
        复用 BatchOperationMixin.batch_execute。条目级序列化校验
        (is_valid(raise_exception=True))在驱动函数内执行, DRF ValidationError
        由 batch_execute 的 VALIDATION_ERROR 分支捕获为 fail_item。

        Args:
            data_list: 待创建的数据条目列表
            operator_jobcode: 操作人工号(当前操作人;批量条目不支持代录,
                发现人恒=操作人, CreateSerializer 不含 discovery_person 字段)
            operator_name: 操作人姓名(可选)

        Returns:
            dict: batch_execute 统一结果(total/success_count/fail_count/
                success_items/fail_items)
        """
        from apps.unregisteredasset.serializers import UnregisteredAssetCreateSerializer
        from core.batch_mixins import BatchOperationMixin

        def _create_item(idx: int, item: dict[str, Any]) -> UnregisteredAsset:
            serializer = UnregisteredAssetCreateSerializer(data=item)
            serializer.is_valid(raise_exception=True)
            return UnregisteredAssetService.create(
                data=serializer.validated_data,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        result = BatchOperationMixin.batch_execute(
            items=data_list,
            process_fn=_create_item,
            max_batch_size=MAX_BATCH_SIZE,
            use_transaction=False,
        )
        # 【契约锁定】本端点 fail_items 契约与迁移前手写版一致(快照测试逐键锁定):
        # 剔除 batch_execute 为其他消费方生成的 row_number 键, 保持
        # {index, error_code, error_message, input_data} 原结构。仅在本方法内
        # 生效, 不影响其他 10 个 batch_execute 消费方。
        for fail_item in result["fail_items"]:
            fail_item.pop("row_number", None)
        return result

    @staticmethod
    @transaction.atomic
    def update(
        unregistered_code: str, update_data: dict[str, Any], operator_jobcode: str, operator_name: str | None = None
    ) -> UnregisteredAsset:
        """更新未登记资产信息(仅待审批,白名单字段)

        Args:
            unregistered_code: 未登记资产编码
            update_data: 更新数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名(可选)

        Raises:
            AppValidationError: 记录不存在、状态不允许或字段不合法时抛出
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
        _apply_whitelist_edits(unregistered, update_data)

        unregistered.save()

        # 记录审计日志(延迟导入,异常捕获)
        _log_update_audit(unregistered, before_data, update_data, operator_jobcode, operator_name)

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
        """审批并处理未登记资产(状态机/审计解耦)

        处理分支: create_and_recycle / create_and_damaged(创建并回收/报废),
        supplement_and_recycle(补建出库并回收), correct_and_recycle(修正并回收),
        reject(仅拒批不设 APPROVED)。

        Args:
            unregistered_code: 未登记资产编码
            handle_type: 处理方式
            approver: 审批人工号
            operator_name: 审批人姓名(可选)
            approval_remark: 审批备注(可选)

        Returns:
            Dict[str, Any]: 处理结果(含 action/asset_code/recycle_id/damaged_id)

        Raises:
            AppValidationError: 状态不允许、处理方式不匹配或处理失败时抛出
        """
        unregistered, approver_employee = _prepare_approval(unregistered_code, handle_type, approver, approval_remark)
        result = _execute_handle(unregistered, handle_type, approver_employee)

        # 记录审计日志(延迟导入,异常捕获)
        _log_approve_audit(unregistered, handle_type, result, approver_employee, operator_name)

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
        _safe_call_audit(
            "delete", unregistered=unregistered, operator_jobcode=operator_jobcode, operator_name=operator_name
        )

        # 执行软删除
        unregistered.delete()

    @staticmethod
    def batch_delete_unregistered(
        ids: list[str], operator_jobcode: str, operator_name: str | None = None, user: Any = None
    ) -> dict[str, Any]:
        """批量删除未登记资产(软删除,仅待审批)

        【分层收敛】视图层手写循环(views.batch_delete)下沉至 Service,复用
        BatchOperationMixin.batch_delete_execute 逐条事务包裹。单条失败以
        AppValidationError(error_code) 抛出,由框架映射为 NOT_FOUND /
        STATUS_NOT_ALLOWED / VALIDATION_ERROR / INTERNAL_ERROR 结构。

        【B14 行级】传入 user 时逐条按行级隔离过滤:越权条目与不存在条目
        同构返回 NOT_FOUND(4.5 语义4: 不泄露存在性),无权限条目跳过删除。

        Args:
            ids: 待删除编码列表
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名(可选)
            user: 请求用户(HTTP 上下文必传,视图 mixin 经 batch_delete_passes_user
                注入);仅 Service 直调(无 HTTP 上下文,如单测)时不传,保持无 scope 行为

        Returns:
            dict: batch_delete_execute 统一结果(total/success_count/fail_count/
                success_ids/fail_items)
        """
        from core.batch_mixins import BatchOperationMixin

        def _delete_item(item_id: str) -> None:
            if user is not None:
                instance = (
                    UnregisteredAssetSelector.get_queryset_for_user(user).filter(unregistered_code=item_id).first()
                )
            else:
                instance = UnregisteredAssetSelector.get_by_code(item_id)
            if not instance:
                raise AppValidationError(detail=f"未登记资产 {item_id} 不存在", error_code="NOT_FOUND")
            if not instance.can_delete():
                raise AppValidationError(
                    detail=f"当前审批状态为 {instance.approval_status},不允许删除",
                    error_code="STATUS_NOT_ALLOWED",
                )
            UnregisteredAssetService.delete(
                unregistered_code=item_id,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )

        return BatchOperationMixin.batch_delete_execute(ids=ids, process_fn=_delete_item, max_batch_size=MAX_BATCH_SIZE)
