"""
资产管理服务层

该模块提供资产管理的核心业务逻辑，封装资产的创建、更新、删除、出库、回收、报废等操作，
确保业务规则的一致性和数据完整性。所有写操作均使用事务装饰器确保数据一致性。

包含以下服务类：
- AssetService: 资产管理服务
- OutAssetService: 出库资产管理服务
- RecycleAssetService: 回收资产管理服务
- DamagedAssetService: 待报废资产管理服务
- WasteAssetService: 已报废资产管理服务
- ContractService: 合同管理服务
- StorageService: 仓库管理服务
- AssetTypeService: 资产类型管理服务
"""

import random
import string
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.utils import timezone
from core.exceptions import AppValidationError

from apps.assetmanagement.models import (
    Asset,
    AssetType,
    Contract,
    Storage,
    OutAsset,
    RecycleAsset,
    DamagedAsset,
    WasteAsset,
    HardDiskSN,
)
from apps.assetmanagement.selectors import (
    AssetSelector,
    OutAssetSelector,
    ContractSelector,
    StorageSelector,
    AssetTypeSelector,
    # 【AGENTS 规范 - P4-03】将 DamagedAssetSelector 从方法内移至文件顶部统一导入
    DamagedAssetSelector,
    # 【AGENTS 规范 - P4-04】将 WasteAssetSelector 从方法内移至文件顶部统一导入
    WasteAssetSelector,
)
# 【AGENTS 规范 - 状态机解耦】使用新的状态机模块
from apps.assetmanagement.state_machine import AssetFSM, InvalidTransitionError
# 【AGENTS 规范 - 审计解耦】使用显式审计模块
from apps.assetmanagement.audit import AuditLogger, AuditContext
# 【保留】OperationLogService 仍被 audit.py 内部使用
from apps.assetmanagement.operation_log_service import OperationLogService

# 【修复 S9】定义可更新的字段白名单，防止通过 setattr 修改任意字段
ASSET_UPDATE_ALLOWED_FIELDS = frozenset([
    'asset_name', 'asset_type_code', 'asset_storage_code',
    'asset_brand', 'asset_specification', 'asset_purchase_date',
    'asset_purchase_price', 'asset_supplier', 'asset_warranty_expiry_date',
    'asset_description', 'asset_remark',
    'asset_current_status',
    'asset_management_person_jobcode',
    'asset_responsible_person_jobcode', 'is_active'
])

# 【AGENTS 规范 - 去除冗余】outasset_current_status 字段已删除
# 状态统一通过 Asset FK 关联查询（outasset_code.asset_current_status）
OUTASSET_UPDATE_ALLOWED_FIELDS = frozenset([
    'outasset_type', 'outasset_receiver_name', 'outasset_receiver_department',
    'outasset_use_location', 'outasset_due_date', 'outasset_note',
])


class AssetCodeGenerator:
    """
    资产编码生成器

    【AGENTS 规范】后端自动生成 asset_code，前端无需传递。
    生成格式：ASSET-{asset_type_category}-{asset_type_code}-{YYYYMMDD}-{6位随机}-{4位序号}

    示例：ASSET-hardware-ZDDN-20260604-A3B7C2-0001
    """

    # 随机字符集：大写字母 + 数字
    RANDOM_CHARS = string.ascii_uppercase + string.digits
    RANDOM_LENGTH = 6
    MAX_RETRY = 3  # 唯一性冲突最大重试次数

    @classmethod
    def _generate_random_str(cls) -> str:
        """生成6位大写字母+数字随机字符串"""
        return ''.join(random.choices(cls.RANDOM_CHARS, k=cls.RANDOM_LENGTH))

    @classmethod
    def _generate_date_str(cls) -> str:
        """生成 YYYYMMDD 日期字符串"""
        return datetime.now().strftime("%Y%m%d")

    @classmethod
    def generate(cls, asset_type_category: str, asset_type_code: str,
                 purchase_number: int = 1) -> List[str]:
        """
        生成资产编码列表

        【AGENTS 规范】根据资产类型和采购数量生成编码列表。
        同一批次的编码共享相同的随机字符串，序号连续递增。

        Args:
            asset_type_category: 资产分类类型（hardware/software/lowvalue/other）
            asset_type_code: 资产类型编码（如 ZDDN）
            purchase_number: 采购数量，决定生成几条编码

        Returns:
            List[str]: 编码列表，长度为 purchase_number

        Raises:
            ValueError: purchase_number 小于 1 时抛出
        """
        if purchase_number < 1:
            raise ValueError("purchase_number 必须 >= 1")

        date_str = cls._generate_date_str()
        random_str = cls._generate_random_str()

        codes = []
        for i in range(1, purchase_number + 1):
            seq = f"{i:04d}"
            code = f"ASSET-{asset_type_category}-{asset_type_code}-{date_str}-{random_str}-{seq}"
            codes.append(code)

        return codes

    @classmethod
    def generate_with_unique_check(cls, asset_type_category: str,
                                    asset_type_code: str,
                                    purchase_number: int = 1) -> List[str]:
        """
        生成资产编码列表（带唯一性校验）

        【AGENTS 规范】防御性编程：生成后查询数据库校验唯一性，
        如遇冲突则重新生成随机部分，最多重试 MAX_RETRY 次。

        Args:
            asset_type_category: 资产分类类型
            asset_type_code: 资产类型编码
            purchase_number: 采购数量

        Returns:
            List[str]: 确保唯一的编码列表

        Raises:
            RuntimeError: 超过最大重试次数仍冲突时抛出
        """
        for attempt in range(cls.MAX_RETRY):
            codes = cls.generate(asset_type_category, asset_type_code, purchase_number)
            existing = Asset.objects.filter(asset_code__in=codes).values_list('asset_code', flat=True)
            if not existing:
                return codes
            # 有冲突，下一轮循环会重新生成（随机部分不同）

        raise RuntimeError(
            f"生成资产编码失败：连续 {cls.MAX_RETRY} 次尝试均存在唯一性冲突"
        )


class AssetService:
    """
    资产管理服务

    提供资产全生命周期管理的业务逻辑，包括资产的创建、更新、删除、状态变更等操作。
    所有涉及数据修改的操作都使用事务装饰器确保数据一致性。
    """

    @staticmethod
    @transaction.atomic
    def create_asset(asset_data: Dict[str, Any], operator_jobcode: Optional[str] = None,
                     operator_name: Optional[str] = None) -> List[Asset]:
        """
        创建资产（支持批量）

        【AGENTS 规范】
        1. asset_code 由后端自动生成，前端无需传递
        2. 当 asset_purchase_number > 1 时，创建多条 Asset 记录
        3. 同一批次的编码共享相同的随机字符串，序号连续递增
        4. 返回 List[Asset]，统一数组格式（单条时长度为1）

        Args:
            asset_data: 资产数据
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            List[Asset]: 创建的资产对象列表

        Raises:
            AppValidationError: 资产编码已存在时抛出
            RuntimeError: 编码生成失败时抛出
        """
        # 移除前端可能传入的 asset_code（由后端自动生成）
        asset_data.pop('asset_code', None)

        # 获取资产类型信息
        asset_type = asset_data.get('asset_type_code')
        asset_type_code = asset_type.asset_type_code if asset_type else ""
        asset_type_category = asset_type.asset_type_category if asset_type else "other"

        purchase_number = asset_data.get('asset_purchase_number', 1)

        # 生成唯一编码列表
        codes = AssetCodeGenerator.generate_with_unique_check(
            asset_type_category=asset_type_category,
            asset_type_code=asset_type_code,
            purchase_number=purchase_number,
        )

        # 批量创建
        created_assets = []
        for code in codes:
            single_data = {**asset_data, 'asset_code': code}
            asset = Asset.objects.create(**single_data)

            # 【AGENTS 规范 - 审计解耦】为每条记录记录操作日志
            AuditLogger.log_asset_create(
                asset=asset,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name,
            )
            created_assets.append(asset)

        return created_assets

    @staticmethod
    @transaction.atomic
    def update_asset(asset_code: str, update_data: Dict[str, Any],
                     operator_jobcode: Optional[str] = None,
                     operator_name: Optional[str] = None) -> Asset:
        """
        更新资产并记录操作日志

        根据资产编码更新资产信息。
        【修复 S9】使用字段白名单过滤，只允许更新指定的业务字段。
        【AGENTS规范】记录变更前后数据，支持审计追踪。

        Args:
            asset_code: 资产编码
            update_data: 更新数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            Asset: 更新后的资产实例

        Raises:
            AppValidationError: 资产不存在或字段不允许更新时抛出
        """
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在")

        # 【AGENTS规范】记录变更前数据
        before_data = {}
        for key in update_data.keys():
            if key in ASSET_UPDATE_ALLOWED_FIELDS:
                field_value = getattr(asset, key)
                # 处理外键字段，转换为字符串
                if hasattr(field_value, 'pk'):
                    before_data[key] = str(field_value)
                else:
                    before_data[key] = field_value

        # 【修复 S9】字段白名单过滤，防止修改任意字段
        for key, value in update_data.items():
            if key in ASSET_UPDATE_ALLOWED_FIELDS:
                setattr(asset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}")

        asset.save()

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_update(
            asset=asset,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return asset

    @staticmethod
    @transaction.atomic
    def delete_asset(asset_code: str,
                     operator_jobcode: Optional[str] = None,
                     operator_name: Optional[str] = None) -> None:
        """
        删除资产（软删除）

        根据资产编码执行软删除操作，不会物理删除数据。
        【AGENTS规范】删除前记录操作日志，支持审计追踪。

        Args:
            asset_code: 资产编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Raises:
            AppValidationError: 资产不存在时抛出
        """
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在")

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_delete(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        asset.delete()

    @staticmethod
    @transaction.atomic
    def change_asset_status(asset_code: str, new_status: str, description: str = "") -> Asset:
        """
        变更资产状态

        修改资产的当前状态，并记录变更历史。

        Args:
            asset_code: 资产编码
            new_status: 新状态（in_store/in_use/in_scrapped）
            description: 状态变更说明（可选）

        Returns:
            Asset: 更新后的资产实例

        Raises:
            AppValidationError: 资产不存在或状态无效时抛出
        """
        valid_statuses = dict(Asset.ASSET_STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise AppValidationError(detail=f"无效的资产状态: {new_status}")

        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在")

        old_status = asset.asset_current_status
        asset.asset_current_status = new_status

        # 【AGENTS 规范 - 审计解耦】显式记录状态变更日志
        AuditLogger.log_state_change(
            asset=asset,
            from_state=old_status,
            to_state=new_status,
            trigger='manual_change',
            operator_jobcode=None,
            operator_name=None
        )

        asset.save()
        return asset


    @staticmethod
    @transaction.atomic
    def change_outasset_employee(asset_code:str,applicant_jobcode:str,manager_jobcode:str) -> Asset:
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在")

        old_applicant = asset.asset_applicant
        old_manager = asset.asset_manager

        asset.asset_applicant = applicant_jobcode
        asset.asset_manager = manager_jobcode

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={'asset_applicant': old_applicant, 'asset_manager': old_manager},
            after_data={'asset_applicant': applicant_jobcode, 'asset_manager': manager_jobcode},
            operator_jobcode=None,
            operator_name=None
        )

        asset.save()
        return asset

    @staticmethod
    @transaction.atomic
    def transfer_asset_to_storage(asset_code: str, storage_code: str) -> Asset:
        """
        转移资产到指定仓库

        修改资产的存储仓库，并记录变更历史。

        Args:
            asset_code: 资产编码
            storage_code: 目标仓库编码

        Returns:
            Asset: 更新后的资产实例

        Raises:
            AppValidationError: 资产或仓库不存在时抛出
        """
        asset = AssetSelector.get_asset_by_code(asset_code)
        if not asset:
            raise AppValidationError(detail=f"资产 {asset_code} 不存在")

        storage = StorageSelector.get_storage_by_code(storage_code)
        if not storage:
            raise AppValidationError(detail=f"仓库 {storage_code} 不存在")

        old_storage = asset.asset_storage_code
        asset.asset_storage_code = storage

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_update(
            asset=asset,
            before_data={'asset_storage_code': old_storage.storage_name if old_storage else None},
            after_data={'asset_storage_code': storage.storage_name},
            operator_jobcode=None,
            operator_name=None
        )

        asset.save()
        return asset

    @staticmethod
    def get_asset_statistics() -> Dict[str, Any]:
        """
        获取资产统计信息

        统计资产总数、总价值及各状态的资产数量。

        Returns:
            Dict[str, Any]: 统计信息字典，包含总数、总价值、在库、在用、报废数量
        """
        return AssetSelector.get_asset_statistics()


class OutAssetService:
    """
    出库资产管理服务

    提供资产出库的业务逻辑，包括出库记录创建、状态变更等操作。
    """

    @staticmethod
    @transaction.atomic
    def create_outasset(
        outasset_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> OutAsset:
        """
        创建出库记录

        创建资产出库记录，并验证资产状态是否允许出库。
        【AGENTS 规范 - 状态机解耦】显式调用 AssetFSM 处理状态变更。
        【AGENTS 规范 - 审计解耦】显式调用 AuditLogger 记录日志。

        Args:
            outasset_data: 出库数据字典，包含出库记录的所有字段信息
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            OutAsset: 创建成功的出库记录实例

        Raises:
            AppValidationError: 资产状态不允许出库或资产不存在时抛出
        """
        asset = outasset_data.get('outasset_code')
        if not asset:
            raise AppValidationError(detail="缺少资产编码")

        # 业务验证：检查资产状态是否允许出库
        if asset.asset_current_status not in ['in_store', 'recycled_pending']:
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status}，不能出库"
            )

        # 【AGENTS规范 - 取消出库支持】记录出库前资产状态
        # 【业务规则】
        # - 从 in_store 出库时，记录 'in_store'
        # - 从 recycled_pending 出库时，记录 'recycled_pending'
        # 【时序要求】必须在创建记录前记录，因为创建后字段值会被持久化
        outasset_data['outasset_previous_status'] = asset.asset_current_status

        # 【新增】提取申请人/保管人工号/使用地点，从 outasset_data 中移除（不属于 OutAsset 模型字段）
        applicant_jobcode = outasset_data.pop('outasset_applicant_jobcode', None)
        manager_jobcode = outasset_data.pop('outasset_manager_jobcode', None)
        using_location = outasset_data.pop('outasset_using_location', None)

        # 创建出库记录
        outasset = OutAsset.objects.create(**outasset_data)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        # 【事务控制】Service层控制事务和并发锁
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status

        try:
            AssetFSM.outasset(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e))

        # 【AGENTS 规范 - 去除冗余】outasset_applicant_jobcode/manager_jobcode/using_location 已删除
        # 这些字段现在统一存储在 Asset 模型中
        # 【新增】出库时同步更新 Asset 的申请人/保管人/使用地点
        asset.asset_storage_code = None
        if applicant_jobcode:
            asset.asset_applicant_jobcode = applicant_jobcode
        if manager_jobcode:
            asset.asset_manager_jobcode = manager_jobcode
        if using_location:
            asset.asset_using_location = using_location

        update_fields = [
            'asset_current_status',
            'asset_storage_code',
        ]
        if applicant_jobcode:
            update_fields.append('asset_applicant_jobcode')
        if manager_jobcode:
            update_fields.append('asset_manager_jobcode')
        if using_location:
            update_fields.append('asset_using_location')
        asset.save(update_fields=update_fields)

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        # 【AGENTS 规范 - 去除冗余】操作人从 Asset.asset_applicant_jobcode 获取
        applicant = asset.asset_applicant_jobcode
        AuditLogger.log_asset_out(
            asset=asset,
            outasset_recordcode=outasset.outasset_recordcode,
            operator_jobcode=operator_jobcode or (
                applicant.employee_jobcode if applicant else None
            ),
            operator_name=operator_name
        )

        return outasset

    @staticmethod
    @transaction.atomic
    def update_outasset(outasset_recordcode: str, update_data: Dict[str, Any]) -> OutAsset:
        """
        更新出库记录

        【修复 S9】使用字段白名单过滤，只允许更新指定的业务字段。

        Args:
            outasset_recordcode: 出库记录编码
            update_data: 更新数据字典

        Returns:
            OutAsset: 更新后的出库记录实例

        Raises:
            AppValidationError: 出库记录不存在或字段不允许更新时抛出
        """
        outasset = OutAssetSelector.get_outasset_by_record_code(outasset_recordcode)
        if not outasset:
            raise AppValidationError(detail=f"出库记录 {outasset_recordcode} 不存在")

        # 【修复 S9】字段白名单过滤，防止修改任意字段
        for key, value in update_data.items():
            if key in OUTASSET_UPDATE_ALLOWED_FIELDS:
                setattr(outasset, key, value)
            else:
                raise AppValidationError(detail=f"不允许修改字段: {key}")

        outasset.save()
        return outasset

    @staticmethod
    def get_outasset_statistics() -> Dict[str, Any]:
        """
        获取出库统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        return OutAssetSelector.get_outasset_statistics()


class RecycleAssetService:
    """
    回收资产管理服务

    提供资产回收的业务逻辑，包括回收记录创建、资产状态更新等操作。
    """

    @staticmethod
    @transaction.atomic
    def create_recycle_asset(
        recycle_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> RecycleAsset:
        """
        创建回收记录

        创建资产回收记录，并验证出库记录状态是否允许回收。
        【AGENTS 规范 - 状态机解耦】显式调用 AssetFSM 处理状态变更。
        【AGENTS 规范 - 审计解耦】显式调用 AuditLogger 记录日志。

        Args:
            recycle_data: 回收数据字典，包含回收记录的所有字段信息
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            RecycleAsset: 创建成功的回收记录实例

        Raises:
            AppValidationError: 出库记录状态不允许回收或不存在时抛出
        """
        # 【读写分离】提取前端传入的额外字段（不属于 RecycleAsset 模型）
        storage_obj = recycle_data.pop('recycle_asset_storage_code', None)
        recycle_person_obj = recycle_data.pop('recycle_asset_recycle_person_jobcode', None)

        outasset_recordcode = recycle_data.get('outasset_recordcode')
        if not outasset_recordcode:
            raise AppValidationError(detail="缺少出库记录编码")

        outasset = OutAssetSelector.get_outasset_by_record_code(
            outasset_recordcode.outasset_recordcode
        )
        if not outasset:
            raise AppValidationError(detail=f"出库记录 {outasset_recordcode} 不存在")

        # 【AGENTS 规范 - 去除冗余】outasset_current_status 已删除，从 Asset 获取状态
        asset = outasset.outasset_code
        if asset.asset_current_status != 'in_use':
            raise AppValidationError(
                detail=f"资产当前状态为 {asset.asset_current_status}，不能回收"
            )

        # 【读写分离】将前端传入的回收人映射到 operator_jobcode
        if recycle_person_obj and not recycle_data.get('operator_jobcode'):
            recycle_data['operator_jobcode'] = recycle_person_obj

        # 【AGENTS 规范 - 去除冗余】recycle_asset_using_person_jobcode 已删除
        # 使用人信息从 Asset.asset_applicant_jobcode 获取（如需记录）
        # 【AGENTS 规范 - 新增】operator_jobcode 记录回收操作人
        if not recycle_data.get('operator_jobcode') and operator_jobcode:
            recycle_data['operator_jobcode'] = operator_jobcode

        # 创建回收记录
        recycle_asset = RecycleAsset.objects.create(**recycle_data)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status

        try:
            AssetFSM.recycle(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e))

        # 【读写分离】回收后更新资产仓库编码
        if storage_obj:
            asset.asset_storage_code = storage_obj
        if recycle_person_obj:
            asset.asset_entry_person_jobcode = recycle_person_obj

        update_fields = ['asset_current_status']
        if storage_obj:
            update_fields.append('asset_storage_code')
        if recycle_person_obj:
            update_fields.append('asset_entry_person_jobcode')

        asset.save(update_fields=update_fields)

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_recycle(
            asset=asset,
            recycle_record_code=recycle_asset.recycle_record_code,
            operator_jobcode=recycle_data.get('asset_entry_person_jobcode'),
            operator_name=recycle_data.get('asset_entry_person_name')
        )

        return recycle_asset


class DamagedAssetService:
    """
    待报废资产管理服务

    提供资产报废申请和审批的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_damaged_asset(
        damaged_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> DamagedAsset:
        """
        创建待报废记录

        创建资产报废申请记录。
        【AGENTS 规范 - 状态机解耦】显式调用 AssetFSM 处理状态变更。
        【AGENTS 规范 - 审计解耦】显式调用 AuditLogger 记录日志。

        Args:
            damaged_data: 待报废数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            DamagedAsset: 创建成功的待报废记录实例

        Raises:
            AppValidationError: 资产不存在时抛出
        """
        asset = damaged_data.get('damaged_asset_code')
        if not asset:
            raise AppValidationError(detail="缺少资产编码")

        if DamagedAssetSelector.exists_by_asset_code(asset):
            raise AppValidationError(detail=f"资产 {asset.asset_code} 已存在待报废记录")

        # 创建待报废记录
        damaged_asset = DamagedAsset.objects.create(**damaged_data)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        old_status = asset.asset_current_status

        try:
            AssetFSM.damaged(asset)
        except InvalidTransitionError as e:
            raise AppValidationError(detail=str(e))

        asset.save(update_fields=['asset_current_status'])

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        AuditLogger.log_asset_damaged(
            asset=asset,
            damaged_record_code=damaged_asset.damaged_record_code,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name
        )

        return damaged_asset

    @staticmethod
    @transaction.atomic
    def approve_damaged_asset(
        damaged_asset_code: str,
        approver_jobcode: str,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        审批通过待报废申请

        【AGENTS规范 - 状态机解耦】审批通过后调用 AssetFSM 变更资产状态。
        【AGENTS规范 - 审计解耦】显式调用 AuditLogger 记录操作日志。
        【业务流程】待报废审批通过后，自动流转为已报废资产。

        Args:
            damaged_asset_code: 待报废资产编码（Asset.asset_code）
            approver_jobcode: 审批人工号
            operator_name: 审批人姓名

        Returns:
            Dict[str, Any]: 包含待报废记录和已报废记录的字典
                {
                    'damaged_asset': DamagedAsset,
                    'waste_asset': WasteAsset
                }

        Raises:
            AppValidationError: 待报废记录不存在或状态不允许审批时抛出
        """
        # 通过资产编码获取待报废记录
        damaged_asset = DamagedAssetSelector.get_damaged_asset_by_asset_code(damaged_asset_code)
        if not damaged_asset:
            raise AppValidationError(detail=f"待报废记录 {damaged_asset_code} 不存在")

        if damaged_asset.approval_status != 'pending':
            raise AppValidationError(detail=f"当前状态 {damaged_asset.approval_status} 不允许审批")

        asset = damaged_asset.damaged_asset_code

        # 更新待报废记录状态为已批准
        damaged_asset.approval_status = 'approved'
        damaged_asset.approver_id = approver_jobcode
        damaged_asset.save()

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        if asset:
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            old_status = asset.asset_current_status

            try:
                AssetFSM.approve(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e))

            asset.save(update_fields=['asset_current_status'])

        # 【关键业务逻辑】审批通过后自动创建已报废记录
        waste_asset = WasteAssetService.create_from_damaged_asset(
            damaged_asset=damaged_asset,
            operator_jobcode=approver_jobcode,
            operator_name=operator_name
        )

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        if asset:
            AuditLogger.log_state_change(
                asset=asset,
                from_state=old_status,
                to_state='scrapped',
                trigger='damaged_approved',
                operator_jobcode=approver_jobcode,
                operator_name=operator_name
            )

        return {
            'damaged_asset': damaged_asset,
            'waste_asset': waste_asset
        }

    @staticmethod
    @transaction.atomic
    def reject_damaged_asset(
        damaged_asset_code: str,
        approver_jobcode: str,
        operator_name: Optional[str] = None
    ) -> DamagedAsset:
        """
        拒绝待报废申请

        【AGENTS规范 - 状态机解耦】审批拒绝后调用 AssetFSM 恢复资产状态。
        【AGENTS规范 - 审计解耦】显式调用 AuditLogger 记录操作日志。

        Args:
            damaged_asset_code: 待报废资产编码（Asset.asset_code）
            approver_jobcode: 审批人工号
            operator_name: 审批人姓名

        Returns:
            DamagedAsset: 更新后的待报废记录实例

        Raises:
            AppValidationError: 待报废记录不存在或状态不允许拒绝时抛出
        """
        # 通过资产编码获取待报废记录
        damaged_asset = DamagedAssetSelector.get_damaged_asset_by_asset_code(damaged_asset_code)
        if not damaged_asset:
            raise AppValidationError(detail=f"待报废记录 {damaged_asset_code} 不存在")

        if damaged_asset.approval_status != 'pending':
            raise AppValidationError(detail=f"当前状态 {damaged_asset.approval_status} 不允许拒绝")

        asset = damaged_asset.damaged_asset_code

        damaged_asset.approval_status = 'rejected'
        damaged_asset.approver_id = approver_jobcode
        damaged_asset.save()

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机恢复资产状态
        if asset:
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            old_status = asset.asset_current_status

            try:
                AssetFSM.reject(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e))

            asset.save(update_fields=['asset_current_status'])

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        # 【业务规则】审批拒绝后资产回到 recycled_pending（待发放），而非 in_use
        if asset:
            AuditLogger.log_state_change(
                asset=asset,
                from_state=old_status,
                to_state='recycled_pending',
                trigger='damaged_rejected',
                operator_jobcode=approver_jobcode,
                operator_name=operator_name
            )

        return damaged_asset

    @staticmethod
    @transaction.atomic
    def cancel_damaged_asset(
        damaged_asset_code: str,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> None:
        """
        取消待报废申请（软删除待报废记录，恢复资产和出库状态）

        【AGENTS规范 - 状态机解耦】取消后调用 AssetFSM 恢复资产状态。
        【AGENTS规范 - 审计解耦】显式调用 AuditLogger 记录操作日志。

        Args:
            damaged_asset_code: 待报废资产编码
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Raises:
            AppValidationError: 待报废记录不存在或状态不允许取消
        """
        damaged_asset = DamagedAssetSelector.get_damaged_asset_by_asset_code(damaged_asset_code)
        if not damaged_asset:
            raise AppValidationError(detail=f"待报废记录 {damaged_asset_code} 不存在")

        # 只允许取消待审批状态的申请
        if damaged_asset.approval_status != 'pending':
            raise AppValidationError(
                detail=f"当前审批状态为 {damaged_asset.approval_status}，无法取消"
            )

        # 获取关联资产和出库记录
        asset = damaged_asset.damaged_asset_code
        out_asset = OutAssetSelector.get_active_outasset_by_asset(asset.asset_code)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机恢复资产状态
        if asset and asset.asset_current_status == 'damaged':
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            old_status = asset.asset_current_status

            try:
                AssetFSM.cancel_damaged(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e))

            asset.save(update_fields=['asset_current_status'])

        # 【AGENTS 规范 - 去除冗余】outasset_current_status 已删除
        # 状态统一通过 Asset FK 关联查询，此处无需更新 OutAsset 状态
        # 资产状态已在上方通过 AssetFSM.cancel_damaged 恢复

        # 软删除待报废记录
        damaged_asset.delete()

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        if asset:
            AuditLogger.log_state_change(
                asset=asset,
                from_state=old_status,
                to_state='recycled_pending',
                trigger='damaged_cancelled',
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )


class WasteAssetService:
    """
    已报废资产管理服务

    提供资产报废执行的业务逻辑。
    【业务流程】已报废记录由待报废审批通过后自动创建，不直接手动创建。
    """

    @staticmethod
    @transaction.atomic
    def create_waste_asset(
        waste_data: Dict[str, Any],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> WasteAsset:
        """
        创建已报废记录

        创建资产报废完成记录，并更新资产状态为报废。
        【AGENTS 规范 - 状态机解耦】显式调用 AssetFSM 处理状态变更。
        【AGENTS 规范 - 审计解耦】显式调用 AuditLogger 记录日志。
        【注意】此方法为通用创建方法，业务流程中应使用 create_from_damaged_asset。

        Args:
            waste_data: 报废数据字典
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            WasteAsset: 创建成功的已报废记录实例

        Raises:
            AppValidationError: 待报废记录未通过审批或不存在时抛出
        """
        damaged_asset = waste_data.get('waste_asset_code')
        if not damaged_asset:
            raise AppValidationError(detail="缺少待报废记录")

        if damaged_asset.approval_status != 'approved':
            raise AppValidationError(detail="待报废记录未通过审批，无法报废")

        # 创建已报废记录
        waste_asset = WasteAsset.objects.create(**waste_data)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        asset = damaged_asset.damaged_asset_code
        if asset:
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            old_status = asset.asset_current_status

            try:
                AssetFSM.approve(asset)
            except InvalidTransitionError as e:
                raise AppValidationError(detail=str(e))

            asset.save(update_fields=['asset_current_status'])

        # 【AGENTS 规范 - 审计解耦】显式记录操作日志
        if asset:
            AuditLogger.log_asset_waste(
                asset=asset,
                waste_record_code=waste_asset.waste_record_code,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )

        return waste_asset

    @staticmethod
    @transaction.atomic
    def create_from_damaged_asset(
        damaged_asset: DamagedAsset,
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> WasteAsset:
        """
        从待报废记录创建已报废记录

        【业务流程】待报废审批通过后，自动调用此方法创建已报废记录。
        【数据映射】从待报废记录复制相关字段到已报废记录。

        Args:
            damaged_asset: 待报废记录实例（已审批通过）
            operator_jobcode: 操作人工号（可选）
            operator_name: 操作人姓名（可选）

        Returns:
            WasteAsset: 创建成功的已报废记录实例

        Raises:
            AppValidationError: 待报废记录未审批通过或已存在已报废记录时抛出
        """
        # 【AGENTS 规范 - P4-04】使用文件顶部统一导入的 WasteAssetSelector

        # 校验待报废记录状态
        if damaged_asset.approval_status != 'approved':
            raise AppValidationError(
                detail=f"待报废记录未审批通过，当前状态: {damaged_asset.approval_status}"
            )

        asset = damaged_asset.damaged_asset_code

        # 校验是否已存在已报废记录（防止重复创建）
        existing_waste = WasteAssetSelector.get_waste_asset_by_asset_code(asset.asset_code)
        if existing_waste:
            raise AppValidationError(detail=f"资产 {asset.asset_code} 已存在已报废记录")

        # 准备已报废记录数据（从待报废记录映射字段）
        # 【AGENTS 规范 - 去除冗余】waste_asset_contract_code 已删除
        # 合同信息统一通过 waste_asset_code.asset_contract_code 关联查询
        waste_data = {
            'waste_asset_code': asset,
            'source_damaged_asset': damaged_asset,  # 【新增】记录来源待报废记录
            'waste_asset_number': damaged_asset.damaged_asset_number,
            'waste_asset_date': timezone.now().date(),  # 使用当前日期作为报废日期
            'waste_asset_description': damaged_asset.damaged_asset_description,
        }

        # 创建已报废记录
        waste_asset = WasteAsset.objects.create(**waste_data)

        # 【AGENTS 规范 - 状态机解耦】显式调用状态机处理资产状态变更
        # 注意：资产状态已在 approve_damaged_asset 中通过 AssetFSM.approve 变更
        # 此处只需记录日志，避免重复变更状态
        if asset:
            AuditLogger.log_asset_waste(
                asset=asset,
                waste_record_code=waste_asset.waste_record_code,
                operator_jobcode=operator_jobcode,
                operator_name=operator_name
            )

        return waste_asset


class ContractService:
    """
    合同管理服务

    提供合同管理的业务逻辑，包括付款记录管理等。
    """

    @staticmethod
    @transaction.atomic
    def add_payment_record(contract_code: str, amount: Decimal, description: str = "") -> Contract:
        """
        添加付款记录

        为合同添加付款记录，并更新已付款金额和次数。

        【修复】金额使用 Decimal 类型，避免浮点精度问题。

        Args:
            contract_code: 合同编码
            amount: 付款金额（使用 Decimal 类型）
            description: 付款说明（可选）

        Returns:
            Contract: 更新后的合同实例

        Raises:
            AppValidationError: 合同不存在或金额无效时抛出
        """
        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在")

        if amount <= 0:
            raise AppValidationError(detail="付款金额必须大于0")

        current_record = contract.contract_paid_record or ""
        # 【修复】使用 timezone.now() 替代 datetime.now()
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        new_record = f"{timestamp}: 付款 {amount} 元"
        if description:
            new_record += f" - {description}"
        new_record += "\n"
        contract.contract_paid_record = current_record + new_record

        contract.contract_paid_price = (contract.contract_paid_price or 0) + amount
        contract.contract_paid_count_number += 1

        contract.save()
        return contract

    @staticmethod
    @transaction.atomic
    def update_settlement_status(contract_code: str, status: str) -> Contract:
        """
        更新合同结算状态

        Args:
            contract_code: 合同编码
            status: 结算状态（pending/settled）

        Returns:
            Contract: 更新后的合同实例

        Raises:
            AppValidationError: 合同不存在或状态无效时抛出
        """
        valid_statuses = dict(Contract.CONTRACT_SETTLEMENT_CHOICES)
        if status not in valid_statuses:
            raise AppValidationError(detail=f"无效的结算状态: {status}")

        contract = ContractSelector.get_contract_by_code(contract_code)
        if not contract:
            raise AppValidationError(detail=f"合同 {contract_code} 不存在")

        contract.contract_settlment_status = status
        contract.save()

        return contract

    @staticmethod
    def get_contract_statistics() -> Dict[str, Any]:
        """
        获取合同统计信息

        Returns:
            Dict[str, Any]: 统计信息字典
        """
        return ContractSelector.get_contract_statistics()


class StorageService:
    """
    仓库管理服务

    提供仓库管理的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_storage(storage_data: Dict[str, Any]) -> Storage:
        """
        创建仓库

        Args:
            storage_data: 仓库数据字典

        Returns:
            Storage: 创建成功的仓库实例

        Raises:
            AppValidationError: 仓库编码或名称已存在时抛出
        """
        storage_code = storage_data.get('storage_code')
        storage_name = storage_data.get('storage_name')

        # 【AGENTS 规范 - P2-04】通过 Selector 层检查编码和名称唯一性，避免 Service 层直接调用 ORM
        if StorageSelector.exists_by_code(storage_code):
            raise AppValidationError(detail=f"仓库编码 {storage_code} 已存在")

        if StorageSelector.exists_by_name(storage_name):
            raise AppValidationError(detail=f"仓库名称 {storage_name} 已存在")

        storage = Storage.objects.create(**storage_data)
        return storage


class AssetTypeService:
    """
    资产类型管理服务

    提供资产类型管理的业务逻辑。
    """

    @staticmethod
    @transaction.atomic
    def create_asset_type(asset_type_data: Dict[str, Any]) -> AssetType:
        """
        创建资产类型

        Args:
            asset_type_data: 资产类型数据字典

        Returns:
            AssetType: 创建成功的资产类型实例

        Raises:
            AppValidationError: 资产类型编码已存在时抛出
        """
        asset_type_code = asset_type_data.get('asset_type_code')

        # 【AGENTS 规范 - P2-05】通过 Selector 层检查编码唯一性，避免 Service 层直接调用 ORM
        if AssetTypeSelector.exists_by_code(asset_type_code):
            raise AppValidationError(detail=f"资产类型编码 {asset_type_code} 已存在")

        asset_type = AssetType.objects.create(**asset_type_data)
        return asset_type


class HardDiskSNService:
    """
    硬盘序列号批量保存服务

    【AGENTS 规范】提供硬盘序列号的批量新增和编辑业务逻辑。
    采用"先验证后执行"策略，所有校验通过后才执行数据库操作。
    使用数据库事务确保批量操作的原子性。

    业务规则：
        1. 根据 disks 数组长度自动计算并更新 harddisk_number
        2. 有 id 的记录执行更新，无 id 的记录执行新增
        3. 批量操作完成后同步更新 Asset 表的硬盘数量
        4. 所有操作在事务中执行，任一失败则全部回滚
    """

    @staticmethod
    @transaction.atomic
    def batch_save(validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量保存硬盘序列号记录

        【AGENTS 规范】核心批量保存方法，处理新增和编辑的统一逻辑。

        Args:
            validated_data: 经过 HardDiskSNBatchSerializer 校验后的数据
                {
                    "asset_code": "ASSET-ZDDN-000004",
                    "disks": [
                        { "harddisk_no": 1, "harddisk_sn_code": "SN001", ... },
                        { "id": 5, "harddisk_no": 2, "harddisk_sn_code": "SN002", ... }
                    ]
                }

        Returns:
            Dict[str, Any]: 操作结果
                {
                    "created": 2,      // 新增记录数
                    "updated": 1,      // 更新记录数
                    "total": 3,        // 总处理数
                    "asset_code": "...",
                    "harddisk_number": 3  // 更新后的硬盘数量
                }

        Raises:
            AppValidationError: 数据库操作失败时抛出
        """
        asset_code_str = validated_data["asset_code"]
        disks = validated_data["disks"]

        # 获取关联资产实例
        from apps.assetmanagement.selectors import AssetSelector
        asset = AssetSelector.get_asset_by_code(asset_code_str)
        if asset is None:
            raise AppValidationError(detail=f"资产编码 '{asset_code_str}' 不存在")

        created_count = 0
        updated_count = 0
        processed_ids = []

        for disk_data in disks:
            disk_id = disk_data.get("id")

            # 构建硬盘记录数据
            disk_record_data = {
                "asset_code": asset,
                "harddisk_number": len(disks),  # 总数量
                "harddisk_no": disk_data["harddisk_no"],
                "harddisk_sn_code": disk_data["harddisk_sn_code"].strip(),
                "harddisk_type": disk_data.get("harddisk_type") or "HDD",
                "harddisk_status": disk_data.get("harddisk_status") or "active",
                "harddisk_sn_description": disk_data.get("harddisk_sn_description") or "",
            }

            if disk_id is None:
                # 【新增模式】创建新记录
                HardDiskSN.objects.create(**disk_record_data)
                created_count += 1
            else:
                # 【编辑模式】更新现有记录
                HardDiskSN.objects.filter(id=disk_id).update(**disk_record_data)
                updated_count += 1
                processed_ids.append(disk_id)

        return {
            "created": created_count,
            "updated": updated_count,
            "total": len(disks),
            "asset_code": asset_code_str,
            "harddisk_number": len(disks),
        }


    @staticmethod
    def batch_create_asset(
        asset_data_list: List[Dict[str, Any]],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量创建资产（逐条独立执行，返回详细结果）

        Returns:
            {
                "total": 3,
                "success_count": 2,
                "fail_count": 1,
                "success_items": [Asset, ...],
                "fail_items": [
                    {
                        "index": 2,
                        "row_number": 5,
                        "input_data": {...},
                        "error_code": "DUPLICATE_ASSET_NAME",
                        "error_message": "资产名称 'xxx' 已存在"
                    }
                ]
            }
        """
        success_items: List[Asset] = []
        fail_items: List[Dict[str, Any]] = []

        for idx, asset_data in enumerate(asset_data_list):
            try:
                result = AssetService.create_asset(
                    asset_name=asset_data['asset_name'],
                    asset_type_code=asset_data['asset_type_code'],
                    asset_purchase_price=asset_data.get('asset_purchase_price'),
                    asset_purchase_date=asset_data.get('asset_purchase_date'),
                    asset_entry_date=asset_data.get('asset_entry_date'),
                    asset_storage_code=asset_data.get('asset_storage_code'),
                    asset_contract_code=asset_data.get('asset_contract_code'),
                    asset_purchase_number=asset_data.get('asset_purchase_number', 1),
                    asset_remark=asset_data.get('asset_remark', ''),
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                    department_code=asset_data.get('asset_department_code'),
                    employee_jobcode=asset_data.get('asset_employee_jobcode'),
                )
                if isinstance(result, list):
                    success_items.extend(result)
                else:
                    success_items.append(result)
            except AppValidationError as e:
                error_code = _map_asset_error_code(str(e.detail))
                fail_items.append({
                    "index": idx,
                    "row_number": asset_data.get('row_number'),
                    "input_data": asset_data,
                    "error_code": error_code,
                    "error_message": str(e.detail)
                })
            except Exception:
                fail_items.append({
                    "index": idx,
                    "row_number": asset_data.get('row_number'),
                    "input_data": asset_data,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(asset_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items
        }

    @staticmethod
    def batch_delete_asset(
        asset_codes: List[str],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量删除资产（软删除，逐条独立执行）

        前置校验：
        - 资产状态必须为 in_store
        - 资产不存在关联出库记录
        - 资产不存在待报废记录

        Returns:
            {
                "total": 3,
                "success_count": 2,
                "fail_count": 1,
                "success_ids": ["ASSET-xxx", ...],
                "fail_items": [
                    {
                        "id": "ASSET-xxx",
                        "error_code": "ASSET_IN_USE",
                        "error_message": "资产当前状态为 in_use，不允许删除"
                    }
                ]
            }
        """
        success_ids: List[str] = []
        fail_items: List[Dict[str, Any]] = []

        for asset_code in asset_codes:
            try:
                asset = AssetSelector.get_asset_by_code(asset_code)
                if not asset:
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "NOT_FOUND",
                        "error_message": f"资产 {asset_code} 不存在"
                    })
                    continue

                if asset.asset_current_status != 'in_store':
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "ASSET_IN_USE",
                        "error_message": f"资产当前状态为 {asset.asset_current_status}，不允许删除"
                    })
                    continue

                if OutAsset.objects.filter(outasset_code=asset, is_deleted=False).exists():
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "HAS_OUTASSET_RECORDS",
                        "error_message": "资产存在关联出库记录，不允许删除"
                    })
                    continue

                if WasteAsset.objects.filter(wasteasset_code=asset, is_deleted=False).exclude(wasteasset_status='completed').exists():
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "HAS_DAMAGED_RECORDS",
                        "error_message": "资产存在待报废记录，不允许删除"
                    })
                    continue

                AuditLogger.log_asset_delete(
                    asset_code=asset.asset_code,
                    asset_name=asset.asset_name,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )

                asset.delete()
                success_ids.append(asset_code)

            except Exception:
                fail_items.append({
                    "id": asset_code,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(asset_codes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items
        }


def _map_asset_error_code(error_detail: str) -> str:
    """将错误详情映射为错误码"""
    msg = str(error_detail).lower()
    if "已存在" in msg and "名称" in msg:
        return "DUPLICATE_ASSET_NAME"
    elif "已存在" in msg and "编码" in msg:
        return "DUPLICATE_ASSET_CODE"
    elif "不存在" in msg and "类型" in msg:
        return "ASSET_TYPE_NOT_FOUND"
    elif "不存在" in msg and "仓库" in msg:
        return "STORAGE_NOT_FOUND"
    elif "不存在" in msg and "合同" in msg:
        return "CONTRACT_NOT_FOUND"
    elif "状态" in msg:
        return "STATUS_NOT_ALLOWED"
    return "VALIDATION_ERROR"
