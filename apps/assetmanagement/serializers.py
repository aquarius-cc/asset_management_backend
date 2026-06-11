"""
资产管理序列化器模块

该模块提供资产管理系统所有模型的序列化器，用于API数据的序列化和反序列化。
所有序列化器遵循DRF最佳实践，支持完整的CRUD操作和数据验证。

包含以下序列化器：
- 基础序列化器：Storage, AssetType, Contract
- 资产序列化器：Asset, AssetDetail, AssetCreate
- 流转序列化器：OutAsset, OutAssetDetail, RecycleAsset, DamagedAsset, WasteAsset
- 辅助序列化器：HardDiskSN, CombinedAsset, DashboardStat
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from rest_framework import serializers

from apps.usermanagement.models import Department, Employee
from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    AssetType,
    Contract,
    DamagedAsset,
    HardDiskSN,
    OutAsset,
    RecycleAsset,
    Storage,
    WasteAsset,
)
# 【AGENTS 规范 - 跨应用解耦】使用接口契约替代直接导入
# from apps.usermanagement.models import Employee  # 已废弃：通过 EmployeeProvider 解耦
# from apps.usermanagement.serializers import EmployeeSerializer  # 已废弃：通过 EmployeeProvider 解耦
from apps.assetmanagement.interfaces import (
    get_employee_queryset,
    get_employee_serializer_class,
)
# 【AGENTS 规范 - P2-11/P2-12】导入 Selector，避免 Serializer 层直接 ORM 调用
from apps.assetmanagement.selectors import (
    AssetSelector,
    ContractSelector,
    StorageSelector,
    AssetTypeSelector,
)

if TYPE_CHECKING:
    from django.db.models import Model


# ========== 基础序列化器 ==========


class StorageSerializer(serializers.ModelSerializer[Storage]):
    """
    仓库序列化器

    用于仓库信息的序列化和反序列化操作。
    支持仓库的创建、更新、查询等完整CRUD操作。

    字段说明：
        - storage_code: 仓库编码（唯一标识）
        - storage_name: 仓库名称
        - storage_address: 仓库地址
        - storage_type: 仓库类型（新货/回收/待报废）
        - storage_description: 仓库描述
    """

    class Meta:
        model: Type[Storage] = Storage
        # 【修复 H3】显式列出字段，排除内部字段（is_deleted, created_at, updated_at）
        fields = [
            'storage_code', 'storage_name', 'storage_address',
            'storage_type', 'storage_description', 'is_active'
        ]


class AssetTypeSerializer(serializers.ModelSerializer[AssetType]):
    """
    资产类型序列化器

    用于资产类型信息的序列化和反序列化操作。
    支持资产分类的创建、更新、查询等操作。

    字段说明：
        - asset_type_code: 资产类型编码
        - asset_type_name: 资产类型名称
        - asset_classification: 资产分类（硬件/软件/其他）
    """

    class Meta:
        model: Type[AssetType] = AssetType
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'asset_type_code', 'asset_type_secondary','asset_type_primary','asset_type_description',
            'asset_type_category', 'is_active'
        ]


class ContractSerializer(serializers.ModelSerializer[Contract]):
    """
    合同序列化器

    用于合同信息的序列化和反序列化操作。
    支持合同的创建、更新、查询等操作。

    字段说明：
        - contract_code: 合同编码
        - contract_name: 合同名称
        - contract_type: 合同类型
        - contract_price: 合同金额
        - contract_supplier: 供应商
    """

    class Meta:
        model: Type[Contract] = Contract
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'contract_code', 'contract_name', 'contract_type',
            'contract_price', 'contract_supplier', 'contract_signing_date',
            'contract_warranty_period', 'contract_settlment_status',
            'contract_settlment_price', 'contract_paid_count_number',
            'contract_paid_price', 'contract_paid_record', 'is_active'
        ]


class ContractDetailSerializer(serializers.ModelSerializer[Contract]):
    """
    合同详细信息序列化器

    用于合同详细信息的序列化，包含完整的合同信息。
    主要用于查询接口，返回合同的完整详情。

    字段说明：
        同ContractSerializer，用于详情展示
    """

    class Meta:
        model: Type[Contract] = Contract
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'contract_code', 'contract_name', 'contract_type',
            'contract_price', 'contract_supplier', 'contract_signing_date',
            'contract_warranty_period', 'contract_settlment_status',
            'contract_settlment_price', 'contract_paid_count_number',
            'contract_paid_price', 'contract_paid_record', 'is_active'
        ]


# ========== 资产序列化器 ==========


class AssetSerializer(serializers.ModelSerializer[Asset]):
    """
    资产序列化器

    用于资产信息的序列化和反序列化操作。
    包含关联字段的名称展示，便于前端显示。

    字段说明：
        基础字段：
            - asset_code: 资产编码（唯一标识）
            - asset_name: 资产名称
            - asset_brand: 资产品牌
            - asset_unit: 资产单位
            - asset_specification: 资产规格
            - asset_purchase_price: 采购价格
            - asset_status: 资产状态

        关联字段（只读展示）：
            - asset_type_name: 资产类型名称
            - contract_name: 合同名称
            - storage_name: 仓库名称
            - entry_person_name: 入库人姓名
            - applicant_name: 申请人姓名
            - manager_name: 管理人姓名
    """

    # 只读展示字段，通过关联对象的属性获取
    asset_type_name = serializers.CharField(
        source="asset_type_code.asset_type_secondary",
        read_only=True,
        help_text="资产类型名称"
    )
    contract_name = serializers.CharField(
        source="asset_contract_code.contract_name",
        read_only=True,
        help_text="合同名称"
    )
    storage_name = serializers.CharField(
        source="asset_storage_code.storage_name",
        read_only=True,
        help_text="仓库名称"
    )
    # 🔧 修复：Employee 模型字段已统一为 employee_name
    entry_person_name = serializers.CharField(
        source="asset_entry_person_jobcode.employee_name",
        read_only=True,
        help_text="入库人姓名"
    )
    applicant_name = serializers.CharField(
        source="asset_applicant_jobcode.employee_name",
        read_only=True,
        help_text="申请人姓名"
    )
    manager_name = serializers.CharField(
        source="asset_manager_jobcode.employee_name",
        read_only=True,
        help_text="管理人姓名"
    )

    class Meta:
        model: Type[Asset] = Asset
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'asset_code', 'asset_name', 'asset_brand', 'asset_unit',
            'asset_specification', 'asset_purchase_price', 'asset_purchase_date',
            'asset_warranty_period', 'asset_current_status',
            # 'sort_order',  # 【架构优化】新增排序字段
            'asset_description',  'asset_using_location',
            'asset_entry_date',
            'asset_type_code', 'asset_contract_code', 'asset_storage_code',
            'asset_entry_person_jobcode', 'asset_applicant_jobcode', 'asset_manager_jobcode',
            'asset_type_name', 'contract_name', 'storage_name',
            'entry_person_name', 'applicant_name', 'manager_name',
            'is_active'
        ]


class HardDiskSNSimpleSerializer(serializers.ModelSerializer[HardDiskSN]):
    """
    硬盘序列号简化序列化器（用于嵌套展示）

    用于 AssetDetailSerializer 嵌套展示，排除冗余字段，
    避免重复返回 asset_name、asset_type 等父级 Asset 已包含的信息。

    【AGENTS 规范】最小数据原则，只返回必要字段：
        - id: 唯一标识
        - harddisk_sn_code: 硬盘序列号（核心字段）
        - harddisk_no: 硬盘编号（标识第几块硬盘）
        - harddisk_type: 硬盘类型（HDD/SSD/NVMe）
        - harddisk_status: 硬盘状态（正常/维修/报废/丢失/损坏）
        - harddisk_sn_description: 硬盘描述信息
    """

    class Meta:
        model: Type[HardDiskSN] = HardDiskSN
        fields = [
            'id',
            'harddisk_sn_code',
            'harddisk_no',
            'harddisk_type',
            'harddisk_status',
            'harddisk_sn_description',
        ]


class AssetDetailSerializer(serializers.ModelSerializer[Asset]):
    """
    资产详细信息序列化器

    用于资产详细信息的序列化，包含嵌套的关联对象完整信息。
    主要用于详情查询接口，返回资产及其关联对象的完整数据。

    字段说明：
        基础字段：同AssetSerializer

        嵌套关联对象（只读）：
            - asset_type: 资产类型完整对象
            - asset_contract: 合同完整对象
            - asset_storage: 仓库完整对象
            - asset_entry_person: 入库人完整对象
            - asset_applicant: 申请人完整对象
            - asset_manager: 管理人完整对象
            - harddisk_sns: 关联硬盘序列号列表（新增）
    """

    asset_type = AssetTypeSerializer(
        source="asset_type_code",
        read_only=True,
        help_text="资产类型完整信息"
    )
    asset_contract = ContractSerializer(
        source="asset_contract_code",
        read_only=True,
        help_text="合同完整信息"
    )
    asset_storage = StorageSerializer(
        source="asset_storage_code",
        read_only=True,
        help_text="仓库完整信息"
    )
    # 【AGENTS 规范 - 跨应用解耦】使用接口契约获取员工序列化器
    asset_entry_person = get_employee_serializer_class()(
        source="asset_entry_person_jobcode",
        read_only=True,
        help_text="入库人完整信息"
    )
    asset_applicant = get_employee_serializer_class()(
        source="asset_applicant_jobcode",
        read_only=True,
        help_text="申请人完整信息"
    )
    asset_manager = get_employee_serializer_class()(
        source="asset_manager_jobcode",
        read_only=True,
        help_text="管理人完整信息"
    )
    # 【新增】关联硬盘序列号列表，使用简化序列化器避免数据冗余
    harddisk_sns = HardDiskSNSimpleSerializer(
        many=True,
        read_only=True,
        help_text="关联的硬盘序列号列表"
    )

    class Meta:
        model: Type[Asset] = Asset
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'asset_code', 'asset_name', 'asset_brand', 'asset_unit',
            'asset_specification', 'asset_purchase_price', 'asset_purchase_date',
            'asset_warranty_period', 'asset_current_status',
            # 'sort_order',  # 【架构优化】新增排序字段
            'asset_description',  'asset_using_location',
            'asset_entry_date',
            'asset_type', 'asset_contract', 'asset_storage',
            'asset_entry_person', 'asset_applicant', 'asset_manager',
            'harddisk_sns',  # 【新增】关联硬盘序列号列表
            'is_active'
        ]


# ========== 简化序列化器（用于关联对象验证） ==========


class ContractSimpleSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    合同简化序列化器

    用于接收和验证合同编码，避免嵌套对象的复杂验证。
    主要用于资产创建等需要关联合同的场景。

    字段说明：
        - contract_code: 合同编码（必填）
    """

    contract_code = serializers.CharField(
        required=True,
        help_text="合同编码"
    )


class StorageSimpleSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    仓库简化序列化器

    用于接收和验证仓库编码，避免嵌套对象的复杂验证。
    主要用于资产创建等需要关联仓库的场景。

    字段说明：
        - storage_code: 仓库编码（必填）
    """

    storage_code = serializers.CharField(
        required=True,
        help_text="仓库编码"
    )


class AssettypeSimpleSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    资产类型简化序列化器

    用于接收和验证资产类型编码，避免嵌套对象的复杂验证。
    主要用于资产创建等需要关联资产类型的场景。

    字段说明：
        - asset_type_code: 资产类型编码（必填）
    """

    asset_type_code = serializers.CharField(
        required=True,
        help_text="资产类型编码"
    )


# ========== 自定义字段 ==========


class CodeField(serializers.Field):
    """
    编码字段

    支持接收字符串或字典格式的数据，统一转换为字典格式。
    用于处理前端传递的关联对象编码。

    示例：
        输入: "Printer000001"
        输出: {"asset_code": "Printer000001"}

        输入: {"asset_code": "Printer000001"}
        输出: {"asset_code": "Printer000001"}
    """

    def __init__(self, code_key: str, **kwargs: Any) -> None:
        """
        初始化编码字段

        Args:
            code_key: 编码字段的键名，如 "asset_type_code"
            **kwargs: 父类初始化参数
        """
        self.code_key = code_key
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> Dict[str, Any]:
        """
        将输入数据转换为内部格式

        Args:
            data: 输入数据（字符串或字典）

        Returns:
            包含编码键值对的字典

        Raises:
            ValidationError: 数据格式不正确时抛出
        """
        if isinstance(data, str):
            return {self.code_key: data}
        elif isinstance(data, dict) and self.code_key in data:
            return data
        raise serializers.ValidationError(f"请传入字符串或包含 {self.code_key} 的字典")

    def to_representation(self, value: Any) -> Optional[str]:
        """
        将内部数据转换为输出格式

        Args:
            value: 模型对象或字典

        Returns:
            编码字符串或None
        """
        if hasattr(value, self.code_key):
            return getattr(value, self.code_key)
        elif isinstance(value, dict) and self.code_key in value:
            return value.get(self.code_key)
        return None


# ========== 资产创建序列化器 ==========


class AssetCreateSerializer(serializers.ModelSerializer[Asset]):
    """
    资产创建序列化器

    用于资产创建时的数据验证和处理。
    支持通过编码关联外部对象，自动查询并关联已存在的对象。

    字段说明：
        基础字段：
            - asset_code: 资产编码（必填，唯一）
            - asset_name: 资产名称（必填，唯一）
            - asset_purchase_price: 采购价格（必填）
            - asset_purchase_date: 购买日期（必填）
            - asset_entry_date: 入库日期（必填）

        关联字段（通过编码关联）：
            - asset_type_code: 资产类型编码
            - asset_contract_code: 合同编码（可选）
            - asset_storage_code: 仓库编码（可选）
            - asset_entry_person_jobcode: 入库人工号（可选）
            - asset_applicant_jobcode: 申请人工号（可选）
            - asset_manager_jobcode: 管理人工号（可选）

    使用场景：
        用于资产创建API，接收前端数据并创建资产记录。
    """

    # 【AGENTS 规范】asset_code 由后端自动生成，前端无需传递
    asset_code = serializers.CharField(
        max_length=64,
        read_only=True,
        help_text="资产编码（后端自动生成，格式：ASSET-{category}-{type_code}-{YYYYMMDD}-{random}-{seq}）"
    )
    # 通过 SlugRelatedField 接收编码，自动查询对应对象
    asset_type_code = serializers.SlugRelatedField(
        slug_field="asset_type_code",
        queryset=AssetType.objects.all(),
        help_text="资产类型编码"
    )
    asset_contract_code = serializers.SlugRelatedField(
        slug_field="contract_code",
        queryset=Contract.objects.all(),
        allow_null=True,
        required=True,
        help_text="合同编码（可选）"
    )
    asset_storage_code = serializers.SlugRelatedField(
        slug_field="storage_code",
        queryset=Storage.objects.all(),
        allow_null=True,
        required=True,
        help_text="仓库编码（可选）"
    )
    # 【AGENTS 规范 - 跨应用解耦】使用接口契约获取员工QuerySet
    asset_entry_person_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),  # 通过接口契约获取
        allow_null=True,
        required=False,
        help_text="入库人工号（可选）"
    )
    asset_applicant_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),  # 通过接口契约获取
        allow_null=True,
        required=False,
        help_text="申请人工号（可选）"
    )
    asset_manager_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),  # 通过接口契约获取
        allow_null=True,
        required=False,
        help_text="管理人工号（可选）"
    )

    class Meta:
        model: Type[Asset] = Asset
        exclude: List[str] = ["asset_recordcode"]
        extra_kwargs = {
            # 可以移除 asset_code 的 extra_kwargs，因为已显式声明
            # "asset_code": {
            #     "required": True,
            #     "help_text": "资产编码（唯一，最大20字符）"
            # },
            "asset_name": {
                "required": True,
                "help_text": "资产名称（唯一，最大100字符）"
            },
            "asset_purchase_price": {
                "required": True,
                "help_text": "采购价格（小数，如 12000.50）"
            },
            "asset_purchase_date": {
                "required": True,
                "help_text": "购买日期（格式：YYYY-MM-DD）"
            },
            "asset_entry_date": {
                "required": True,
                "help_text": "入库日期（格式：YYYY-MM-DD）"
            },
        }

    def validate_asset_purchase_price(self, value: Any) -> Decimal:
        """
        验证采购价格

        将数字类型转换为Decimal类型，确保数据类型一致性。

        Args:
            value: 输入的价格值

        Returns:
            Decimal类型的价格值
        """
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        return value


# ========== 出库资产序列化器 ==========


class OutAssetSerializer(serializers.ModelSerializer[OutAsset]):
    """
    出库资产序列化器（优化版）

    【AGENTS 规范 - 去除冗余】已删除字段改为通过 Asset FK 关联查询：
    - outasset_applicant_jobcode → outasset_code__asset_applicant_jobcode
    - outasset_manager_jobcode → outasset_code__asset_manager_jobcode
    - outasset_using_location → outasset_code__asset_using_location
    - outasset_current_status → outasset_code__asset_current_status

    前端字段名保持不变，通过 source 映射实现兼容。
    """

    outasset_code = serializers.SlugRelatedField(
        slug_field="asset_code",
        queryset=Asset.objects.all(),
        help_text="资产编码"
    )
    # 【AGENTS 规范 - 去除冗余】状态改为通过 Asset FK 关联查询
    outasset_current_status = serializers.CharField(
        source="outasset_code.asset_current_status",
        read_only=True,
        help_text="当前状态"
    )
    outasset_recordcode = serializers.CharField(
        read_only=True,
        help_text="出库记录编码"
    )
    # 【AGENTS 规范 - 去除冗余】申请人改为通过 Asset FK 关联查询
    # 【字段名互换】read_only 字段改为无前缀名，避免与 write_only 字段同名覆盖
    applicant_jobcode = serializers.CharField(
        source="outasset_code.asset_applicant_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="申请人工号"
    )
    # 【AGENTS 规范 - 去除冗余】管理人改为通过 Asset FK 关联查询
    # 【字段名互换】read_only 字段改为无前缀名，避免与 write_only 字段同名覆盖
    manager_jobcode = serializers.CharField(
        source="outasset_code.asset_manager_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="管理人工号"
    )
    outasset_contract_code = serializers.CharField(
        source="outasset_code.asset_contract_code.contract_code",
        read_only=True,
        allow_null=True,
        help_text="合同编码"
    )
    outasset_name = serializers.CharField(
        source="outasset_code.asset_name",
        read_only=True,
        help_text="资产名称"
    )
    outasset_specification = serializers.CharField(
        source="outasset_code.asset_specification",
        read_only=True,
        help_text="资产规格"
    )
    # 【AGENTS 规范 - 去除冗余】使用地点改为通过 Asset FK 关联查询
    # 【字段名互换】read_only 字段改为无前缀名，避免与 write_only 字段同名覆盖
    using_location = serializers.CharField(
        source="outasset_code.asset_using_location",
        read_only=True,
        allow_null=True,
        help_text="使用地点"
    )
    # 【AGENTS 规范 - 修复】user_name → employee_name
    outasset_applicant_name = serializers.CharField(
        source="outasset_code.asset_applicant_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="申请人姓名"
    )
    outasset_manager_name = serializers.CharField(
        source="outasset_code.asset_manager_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="管理人姓名"
    )
    # 【新增】出库时必填：申请人/保管人工号，写入 Asset 表
    # 字段名与前端表单一致（outasset_ 前缀），通过 write_only 接收后由 Service 层写入 Asset
    outasset_applicant_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        required=True,
        write_only=True,
        help_text="申请人工号（出库必填，写入 Asset.asset_applicant_jobcode）"
    )
    outasset_manager_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        required=True,
        write_only=True,
        help_text="保管人工号（出库必填，写入 Asset.asset_manager_jobcode）"
    )
    # 【新增】出库时使用地点，写入 Asset 表
    outasset_using_location = serializers.CharField(
        required=True,
        write_only=True,
        help_text="使用地点（出库必填，写入 Asset.asset_using_location）"
    )

    return_date = serializers.DateField(
        allow_null=True,
        required=False,
        help_text="归还日期，格式 YYYY-MM-DD，可为空"
    )

    class Meta:
        model: Type[OutAsset] = OutAsset
        fields: List[str] = [
            "id",
            "outasset_recordcode",
            "outasset_code",
            "outasset_number",
            # 【字段名互换】read_only 返回字段（无前缀）
            "applicant_jobcode",
            "manager_jobcode",
            "using_location",
            "outasset_contract_code",
            "return_date",
            "outasset_current_status",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "outasset_name",
            "outasset_specification",
            "outasset_applicant_name",
            "outasset_manager_name",
            # 【字段名互换】write_only 入参字段（保留 outasset_ 前缀）
            "outasset_applicant_jobcode",
            "outasset_manager_jobcode",
            "outasset_using_location",
        ]
        read_only_fields: List[str] = [
            "id",
            "outasset_recordcode",
            "outasset_name",
            "outasset_specification",
            "outasset_applicant_name",
            "outasset_manager_name",
            "outasset_contract_code",
            "outasset_current_status",
            # 【字段名互换】read_only 返回字段改为无前缀名
            "using_location",
            "applicant_jobcode",
            "manager_jobcode",
        ]

    def create(self, validated_data: Dict[str, Any]) -> OutAsset:
        """
        创建出库资产记录

        Args:
            validated_data: 验证后的数据字典

        Returns:
            创建的出库资产对象
        """
        validated_data.pop("outasset_recordcode", None)
        return super().create(validated_data)


class OutAssetDetailSerializer(serializers.ModelSerializer[OutAsset]):
    """
    出库资产详情序列化器（优化版）

    【AGENTS 规范 - 去除冗余】所有已删除字段改为通过 Asset FK 关联查询。
    前端字段名保持不变，通过 source 映射实现兼容。
    """

    id = serializers.IntegerField(read_only=True, help_text="记录ID")
    outasset_recordcode = serializers.CharField(read_only=True, help_text="出库记录编码")
    outasset_code = serializers.CharField(
        source="outasset_code.asset_code", read_only=True, help_text="资产编码"
    )
    outasset_number = serializers.IntegerField(read_only=True, help_text="出库数量")
    # 【AGENTS 规范 - 去除冗余】申请人改为通过 Asset FK 关联查询
    # 【AGENTS 规范 - 字段名对齐】与 OutAssetSerializer 保持一致
    applicant_jobcode = serializers.CharField(
        source="outasset_code.asset_applicant_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="申请人工号"
    )
    # 【AGENTS 规范 - 去除冗余】管理人改为通过 Asset FK 关联查询
    # 【AGENTS 规范 - 字段名对齐】与 OutAssetSerializer 保持一致
    manager_jobcode = serializers.CharField(
        source="outasset_code.asset_manager_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="管理人工号"
    )
    outasset_contract_code = serializers.CharField(
        source="outasset_code.asset_contract_code.contract_code",
        read_only=True,
        allow_null=True,
        help_text="合同编码"
    )
    return_date = serializers.DateField(allow_null=True, read_only=True, help_text="归还日期")
    # 【AGENTS 规范 - 去除冗余】使用地点改为通过 Asset FK 关联查询
    # 【AGENTS 规范 - 字段名对齐】与 OutAssetSerializer 保持一致
    using_location = serializers.CharField(
        source="outasset_code.asset_using_location",
        read_only=True,
        allow_null=True,
        help_text="使用地点"
    )
    outasset_date = serializers.DateField(read_only=True, help_text="出库日期")
    outasset_type = serializers.CharField(read_only=True, help_text="出库类型")
    outasset_description = serializers.CharField(read_only=True, allow_null=True, help_text="出库说明")
    # 【AGENTS 规范 - 去除冗余】状态改为通过 Asset FK 关联查询
    outasset_current_status = serializers.CharField(
        source="outasset_code.asset_current_status",
        read_only=True,
        help_text="当前状态"
    )
    outasset_previous_status = serializers.CharField(read_only=True, help_text="出库前资产状态")
    outasset_name = serializers.CharField(
        source="outasset_code.asset_name", read_only=True, help_text="资产名称"
    )
    outasset_specification = serializers.CharField(
        source="outasset_code.asset_specification", read_only=True, help_text="资产规格"
    )
    # 【AGENTS 规范 - 修复】user_name → employee_name
    outasset_applicant_name = serializers.CharField(
        source="outasset_code.asset_applicant_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="申请人姓名"
    )
    outasset_manager_name = serializers.CharField(
        source="outasset_code.asset_manager_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="管理人姓名"
    )
    # 【AGENTS 规范 - 跨应用解耦】使用接口契约获取员工序列化器
    # 【AGENTS 规范 - 去除冗余】改为通过 Asset FK 关联查询
    outasset_applicant = get_employee_serializer_class()(
        source="outasset_code.asset_applicant_jobcode",
        read_only=True,
        allow_null=True,
        help_text="申请人完整信息"
    )
    outasset_manager = get_employee_serializer_class()(
        source="outasset_code.asset_manager_jobcode",
        read_only=True,
        allow_null=True,
        help_text="管理人完整信息"
    )
    outasset_contract = ContractSerializer(
        source="outasset_code.asset_contract_code",
        read_only=True,
        allow_null=True,
        help_text="合同完整信息"
    )

    class Meta:
        model: Type[OutAsset] = OutAsset
        fields: List[str] = [
            "id",
            "outasset_recordcode",
            "outasset_code",
            "outasset_number",
            "applicant_jobcode",
            "manager_jobcode",
            "outasset_contract_code",
            "return_date",
            "using_location",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "outasset_current_status",
            "outasset_name",
            "outasset_specification",
            "outasset_applicant_name",
            "outasset_manager_name",
            "outasset_applicant",
            "outasset_manager",
            "outasset_contract",
            "outasset_previous_status",
        ]
        read_only_fields: List[str] = [
            "id",
            "outasset_recordcode",
            "outasset_code",
            "outasset_current_status",
            "outasset_number",
            "applicant_jobcode",
            "manager_jobcode",
            "outasset_contract_code",
            "return_date",
            "using_location",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "outasset_name",
            "outasset_specification",
            "outasset_applicant_name",
            "outasset_manager_name",
            "outasset_applicant",
            "outasset_manager",
            "outasset_contract",
            "outasset_previous_status",
        ]


# ========== 回收资产序列化器 ==========


class RecycleAssetSerializer(serializers.ModelSerializer[RecycleAsset]):
    """
    回收资产序列化器（读写分离版）

    【读写分离】read_only 返回字段使用短名，write_only 入参字段使用原名：
    - recycle_asset_storage_code (write_only) → storage_code (read_only)
    - recycle_asset_recycle_person_jobcode (write_only) → recycle_person_jobcode (read_only)
    - recycle_asset_storage_name → storage_name (read_only)
    - recycle_asset_using_person_name → using_person_name (read_only)
    - recycle_asset_using_person_jobcode → using_person_jobcode (read_only)
    - recycle_asset_recycle_person_name → recycle_person_name (read_only)
    """
    recycle_record_code = serializers.CharField(
        read_only=True,
        help_text="回收记录编码"
    )

    outasset_recordcode = serializers.SlugRelatedField(
        slug_field="outasset_recordcode",
        queryset=OutAsset.objects.all(),
        help_text="出库记录编码"
    )
    recycle_asset_name = serializers.CharField(
        source="recycle_asset_code.asset_name",
        read_only=True,
        help_text="回收资产名称"
    )
    # 【读写分离】read_only 返回字段使用短名
    storage_name = serializers.CharField(
        source="recycle_asset_code.asset_storage_code.storage_name",
        read_only=True,
        help_text="回收仓库名称"
    )
    # 【读写分离】read_only 返回字段使用短名
    using_person_name = serializers.CharField(
        source="outasset_recordcode.outasset_code.asset_manager_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="资产使用人姓名"
    )
    # 【读写分离】read_only 返回字段使用短名
    recycle_person_name = serializers.CharField(
        source="operator_jobcode.employee_name",
        read_only=True,
        allow_null=True,
        help_text="回收操作人姓名"
    )
    # 【读写分离】read_only 返回字段使用短名，后端自动从 Asset FK 获取
    using_person_jobcode = serializers.CharField(
        source="outasset_recordcode.outasset_code.asset_manager_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="使用人工号"
    )
    using_person_department = serializers.CharField(
        source="outasset_recordcode.outasset_code.asset_manager_jobcode.employee_department",
        read_only=True,
        allow_null=True,
        help_text="资产使用人部门"
    )
    # 【读写分离】read_only 返回字段使用短名
    recycle_person_jobcode = serializers.CharField(
        source="operator_jobcode.employee_jobcode",
        read_only=True,
        allow_null=True,
        help_text="回收人工号"
    )
    # 【读写分离】write_only 入参字段，原名保持前端兼容
    recycle_asset_recycle_person_jobcode = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        required=True,
        write_only=True,
        help_text="回收人工号（映射到 operator_jobcode）"
    )
    # 【读写分离】read_only 返回字段使用短名
    storage_code = serializers.CharField(
        source="recycle_asset_code.asset_storage_code.storage_code",
        read_only=True,
        allow_null=True,
        help_text="仓库编码"
    )
    # 【读写分离】write_only 入参字段，原名保持前端兼容
    recycle_asset_storage_code = serializers.SlugRelatedField(
        slug_field="storage_code",
        queryset=Storage.objects.all(),
        required=True,
        write_only=True,
        help_text="回收后仓库编码（写入 Asset.asset_storage_code）"
    )

    class Meta:
        model: Type[RecycleAsset] = RecycleAsset
        # 【AGENTS 规范 - 业务唯一编码】recycle_record_code 为只读，创建时由 Model.save() 自动生成
        fields = [
            'id', 'recycle_record_code', 'recycle_asset_date', 'recycle_asset_code',
            'outasset_recordcode',
            # write_only 入参字段（原名）
            'recycle_asset_storage_code', 'recycle_asset_recycle_person_jobcode',
            # read_only 返回字段（短名）
            'storage_code', 'storage_name',
            'recycle_person_jobcode', 'recycle_person_name',
            'using_person_jobcode', 'using_person_name','using_person_department',
            'recycle_asset_name', 'recycle_asset_number',
            'is_active'
        ]


# ========== 待报废资产序列化器 ==========


class DamagedAssetSerializer(serializers.ModelSerializer[DamagedAsset]):
    """
    待报废资产序列化器（优化版）

    【AGENTS 规范 - 去除冗余】已删除字段改为通过 Asset FK 关联查询：
    - damaged_asset_contract_code → damaged_asset_code__asset_contract_code
    - damaged_asset_storage_code → damaged_asset_code__asset_storage_code

    前端字段名保持不变，通过 source 映射实现兼容。
    """

    damaged_asset_name = serializers.CharField(
        source="damaged_asset_code.asset_name",
        read_only=True,
        help_text="资产名称"
    )
    # 【AGENTS 规范 - 去除冗余】合同改为通过 Asset FK 关联查询
    damaged_asset_contract_name = serializers.CharField(
        source="damaged_asset_code.asset_contract_code.contract_name",
        read_only=True,
        allow_null=True,
        help_text="合同名称"
    )
    # 【AGENTS 规范 - 去除冗余】仓库改为通过 Asset FK 关联查询
    damaged_asset_storage_name = serializers.CharField(
        source="damaged_asset_code.asset_storage_code.storage_name",
        read_only=True,
        allow_null=True,
        help_text="仓库名称"
    )
    damaged_asset_description = serializers.CharField(
        source="damaged_asset_code.asset_description",
        read_only=True,
        help_text="资产描述"
    )
    damaged_asset_specification = serializers.CharField(
        source="damaged_asset_code.asset_specification",
        read_only=True,
        help_text="资产规格"
    )
    # 【AGENTS 规范 - 去除冗余】合同编码改为通过 Asset FK 关联查询
    damaged_asset_contract_code = serializers.CharField(
        source="damaged_asset_code.asset_contract_code.contract_code",
        read_only=True,
        allow_null=True,
        help_text="合同编码"
    )
    # 【AGENTS 规范 - 去除冗余】仓库编码改为通过 Asset FK 关联查询
    damaged_asset_storage_code = serializers.CharField(
        source="damaged_asset_code.asset_storage_code.storage_code",
        read_only=True,
        allow_null=True,
        help_text="仓库编码"
    )

    class Meta:
        model: Type[DamagedAsset] = DamagedAsset
        fields = [
            'id', 'damaged_asset_code', 'damaged_asset_contract_code',
            'damaged_asset_storage_code', 'approval_status', 'approver','damaged_date',
            'damaged_asset_name', 'damaged_asset_contract_name', 'damaged_asset_storage_name',
            'damaged_asset_number','damaged_asset_description','damaged_asset_specification','is_active'
        ]

# ========== 已报废资产序列化器 ==========


class WasteAssetSerializer(serializers.ModelSerializer[WasteAsset]):
    """
    已报废资产序列化器（优化版）

    【AGENTS 规范 - 去除冗余】已删除字段改为通过 Asset FK 关联查询：
    - waste_asset_contract_code → waste_asset_code__asset_contract_code

    前端字段名保持不变，通过 source 映射实现兼容。
    """

    asset_code = serializers.CharField(
        source="waste_asset_code.asset_code",
        read_only=True,
        help_text="资产编码"
    )
    asset_name = serializers.CharField(
        source="waste_asset_code.asset_name",
        read_only=True,
        help_text="资产名称"
    )
    # 【AGENTS 规范 - 去除冗余】合同改为通过 Asset FK 关联查询
    contract_name = serializers.CharField(
        source="waste_asset_code.asset_contract_code.contract_name",
        read_only=True,
        allow_null=True,
        help_text="合同名称"
    )
    waste_asset_specification = serializers.CharField(
        source="waste_asset_code.asset_specification",
        read_only=True,
        help_text="资产规格"
    )
    # 【AGENTS 规范 - 去除冗余】合同编码改为通过 Asset FK 关联查询
    waste_asset_contract_code = serializers.CharField(
        source="waste_asset_code.asset_contract_code.contract_code",
        read_only=True,
        allow_null=True,
        help_text="合同编码"
    )

    class Meta:
        model: Type[WasteAsset] = WasteAsset
        fields = [
            'id', 'waste_asset_code', 'waste_asset_contract_code',
            'waste_asset_date','waste_asset_description',
            'asset_code', 'asset_name', 'contract_name','waste_asset_specification',
            'is_active'
        ]


# ========== 硬盘序列号序列化器 ==========


class HardDiskSNSerializer(serializers.ModelSerializer[HardDiskSN]):
    """
    硬盘序列号序列化器

    用于硬盘序列号的单条管理和查询操作。
    支持序列号的格式验证和唯一性校验。

    字段说明：
        基础字段：
            - asset_code: 关联资产编码
            - harddisk_number: 硬盘数量（该资产下的硬盘总数）
            - harddisk_sn_code: 硬盘序列号（单条记录的唯一标识）

        只读展示字段：
            - asset_name: 资产名称
            - asset_type: 资产类型
            - harddisk_sn_count: 序列号数量（固定返回1，单条记录即一块硬盘）
    """

    asset_name = serializers.CharField(
        source="asset_code.asset_name",
        read_only=True,
        help_text="资产名称"
    )
    asset_type = serializers.CharField(
        # 【修复 H5】修正 source 路径，使用 asset_type_secondary 而非 asset_type_name
        source="asset_code.asset_type_code.asset_type_secondary",
        read_only=True,
        help_text="资产类型"
    )
    harddisk_sn_count = serializers.SerializerMethodField(
        help_text="硬盘SN关联数量"
    )
    harddisk_user_jobcode = serializers.CharField(
        source="asset_code.asset_manager_jobcode",
        read_only=True,
        help_text="资产管理员工号"
    )
    class Meta:
        model: Type[HardDiskSN] = HardDiskSN
        # 【修复 H3】显式列出字段，排除内部字段
        fields = [
            'id', 'asset_code', 'harddisk_number', 'harddisk_sn_code',
            'harddisk_no', 'harddisk_type', 'harddisk_status', 'harddisk_sn_description',
            'asset_name', 'asset_type', 'harddisk_sn_count','harddisk_user_jobcode',
            'is_active'
        ]

    def get_harddisk_sn_count(self, obj: HardDiskSN) -> int:
        """
        获取硬盘序列号数量

        【AGENTS 规范】单条 HardDiskSN 记录代表一块硬盘，
        因此固定返回 1。此方法用于列表展示时统一接口格式。

        Args:
            obj: 硬盘序列号对象

        Returns:
            固定返回 1（单条记录即一块硬盘）
        """
        return 1

    def validate_harddisk_sn_code(self, value: str) -> str:
        """
        验证硬盘序列号格式

        【AGENTS 规范】序列号校验规则：
        1. 必须是非空字符串
        2. 长度不少于3个字符
        3. 去除首尾空白

        Args:
            value: 序列号字符串

        Returns:
            验证并清理后的序列号字符串

        Raises:
            ValidationError: 序列号格式不正确时抛出
        """
        if not value or not value.strip():
            raise serializers.ValidationError("硬盘序列号不能为空")

        cleaned_value = value.strip()

        if len(cleaned_value) < 3:
            raise serializers.ValidationError(f"序列号 '{cleaned_value}' 长度不能少于3个字符")

        return cleaned_value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证数据的完整性

        【AGENTS 规范】单条记录校验逻辑：
        1. 序列号唯一性校验（排除当前编辑的记录自身）
        2. 关联资产编码有效性校验

        Args:
            attrs: 待验证的数据字典

        Returns:
            验证后的数据字典

        Raises:
            ValidationError: 数据校验失败时抛出
        """
        harddisk_sn_code = attrs.get("harddisk_sn_code")
        asset_code = attrs.get("asset_code")

        # 校验序列号唯一性（排除自身，用于更新场景）
        if harddisk_sn_code:
            from .selectors import HardDiskSNSelector
            existing = HardDiskSNSelector.get_harddisk_sn_by_code(harddisk_sn_code)
            if existing:
                # 获取当前实例的 ID（创建时为 None）
                current_id = getattr(self.instance, 'id', None) if self.instance else None
                if existing.id != current_id:
                    raise serializers.ValidationError(
                        f"硬盘序列号 '{harddisk_sn_code}' 已存在"
                    )

        # 校验关联资产是否存在
        if asset_code:
            from .selectors import AssetSelector
            asset = AssetSelector.get_asset_by_code(
                asset_code.asset_code if hasattr(asset_code, 'asset_code') else str(asset_code)
            )
            if asset is None:
                raise serializers.ValidationError(f"资产编码 '{asset_code}' 不存在")

        return attrs


# ========== 硬盘序列号批量序列化器 ==========


class DiskItemSerializer(serializers.Serializer):
    """
    单条硬盘记录序列化器（用于批量保存）

    【AGENTS 规范】用于 HardDiskSNBatchSerializer 中 disks 数组的逐条校验。
    对应前端 DiskItem 接口，支持新增（无 id）和编辑（有 id）两种模式。

    字段说明：
        - id: 后端记录 ID（编辑模式必传，新增模式不传）
        - harddisk_no: 硬盘编号（1~N，标识第几块硬盘）
        - harddisk_sn_code: 硬盘序列号（必填，唯一）
        - harddisk_type: 硬盘类型（HDD/SSD/NVMe/Other，可选）
        - harddisk_status: 硬盘状态（active/repair/scrap/lost/damaged，可选）
        - harddisk_sn_description: 硬盘描述（可选）
    """

    id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="后端记录 ID（编辑已有记录时传递，新增时不传）"
    )
    harddisk_no = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="硬盘编号（从1开始递增）"
    )
    harddisk_sn_code = serializers.CharField(
        required=True,
        max_length=100,
        trim_whitespace=True,
        help_text="硬盘序列号（必填，全局唯一）"
    )
    harddisk_type = serializers.ChoiceField(
        required=False,
        allow_null=True,
        choices=[
            ("HDD", "HDD"),
            ("SSD", "SSD"),
            ("NVMe", "NVMe"),
            ("Other", "Other"),
        ],
        help_text="硬盘类型"
    )
    harddisk_status = serializers.ChoiceField(
        required=False,
        allow_null=True,
        choices=[
            ("active", "正常"),
            ("repair", "维修"),
            ("scrap", "报废"),
            ("lost", "丢失"),
            ("damaged", "损坏"),
        ],
        help_text="硬盘状态"
    )
    harddisk_sn_description = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="硬盘描述"
    )

    def validate_harddisk_sn_code(self, value: str) -> str:
        """
        验证硬盘序列号格式

        【AGENTS 规范】序列号基础校验：
        1. 去除首尾空白
        2. 长度不少于3个字符
        3. 不能为空字符串

        Args:
            value: 原始序列号字符串

        Returns:
            清理后的序列号字符串

        Raises:
            ValidationError: 格式不符合要求时抛出
        """
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise serializers.ValidationError(
                f"序列号 '{cleaned}' 长度不能少于3个字符"
            )
        return cleaned


class HardDiskSNBatchSerializer(serializers.Serializer):
    """
    硬盘序列号批量保存序列化器

    【AGENTS 规范】接收前端批量保存请求，统一处理新增和编辑场景。
    采用"先验证后执行"策略：所有记录校验通过后，才执行数据库操作。

    前端提交格式：
        {
            "asset_code": "ASSET-ZDDN-000004",
            "disks": [
                { "harddisk_no": 1, "harddisk_sn_code": "SN001", ... },           // 新增
                { "id": 5, "harddisk_no": 2, "harddisk_sn_code": "SN002", ... }   // 编辑
            ]
        }

    后端处理逻辑：
        1. 校验 asset_code 有效且资产存在
        2. 校验 disks 数组非空
        3. 逐条校验 disk 记录字段格式
        4. 校验 disks 内部 harddisk_sn_code 不重复
        5. 校验 harddisk_sn_code 与数据库现有记录不冲突（排除编辑记录自身）
        6. 校验编辑模式下的 id 对应记录存在且属于同一资产
        7. 全部通过后返回校验后的数据，由 Service 层执行数据库操作
    """

    asset_code = serializers.CharField(
        required=True,
        max_length=100,
        trim_whitespace=True,
        help_text="资产编码（必填）"
    )
    disks = DiskItemSerializer(
        required=True,
        many=True,
        help_text="硬盘记录数组（至少1条）"
    )

    def validate_asset_code(self, value: str) -> str:
        """
        验证资产编码有效性

        【AGENTS 规范】资产编码必须对应数据库中存在的资产记录。

        Args:
            value: 资产编码字符串

        Returns:
            清理后的资产编码字符串

        Raises:
            ValidationError: 资产不存在时抛出
        """
        from .selectors import AssetSelector
        cleaned = value.strip()
        asset = AssetSelector.get_asset_by_code(cleaned)
        if asset is None:
            raise serializers.ValidationError(
                f"资产编码 '{cleaned}' 不存在"
            )
        return cleaned

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量保存全局校验

        【AGENTS 规范】预检模式校验逻辑：
        1. disks 数组非空校验
        2. disks 内部序列号唯一性校验（同一批次内不能重复）
        3. 序列号与数据库唯一性校验（排除编辑记录自身）
        4. 编辑模式 id 有效性校验（记录存在且属于同一资产）

        Args:
            attrs: 经过字段级校验后的数据字典

        Returns:
            全局校验通过后的数据字典

        Raises:
            ValidationError: 任何全局校验失败时抛出，包含详细错误信息
        """
        disks = attrs.get("disks", [])
        asset_code = attrs.get("asset_code", "")

        # 【校验1】disks 数组非空
        if not disks:
            raise serializers.ValidationError(
                {"disks": "硬盘记录数组不能为空"}
            )

        # 【校验2】disks 内部序列号唯一性
        sn_codes = [d.get("harddisk_sn_code", "").strip() for d in disks]
        duplicate_sns = [
            sn for sn, count in __import__('collections').Counter(sn_codes).items()
            if count > 1
        ]
        if duplicate_sns:
            raise serializers.ValidationError(
                {"disks": f"提交记录中存在重复的序列号: {', '.join(duplicate_sns)}"}
            )

        # 【校验3】序列号与数据库唯一性 + 【校验4】编辑模式 id 有效性
        from .selectors import HardDiskSNSelector
        from .models import HardDiskSN

        for idx, disk in enumerate(disks):
            disk_id = disk.get("id")
            sn_code = disk.get("harddisk_sn_code", "").strip()

            # 查询数据库中是否已有此序列号
            existing = HardDiskSNSelector.get_harddisk_sn_by_code(sn_code)

            if existing:
                if disk_id is None:
                    # 新增模式：序列号已存在 → 冲突
                    raise serializers.ValidationError(
                        {"disks": f"第 {idx + 1} 条记录的序列号 '{sn_code}' 已存在"}
                    )
                elif existing.id != disk_id:
                    # 编辑模式：序列号被其他记录占用 → 冲突
                    raise serializers.ValidationError(
                        {"disks": f"第 {idx + 1} 条记录的序列号 '{sn_code}' 已被其他记录使用"}
                    )
                # else: existing.id == disk_id，编辑自身，合法

            # 编辑模式：校验 id 对应的记录存在且属于同一资产
            if disk_id is not None:
                try:
                    record = HardDiskSN.objects.get(id=disk_id)
                except HardDiskSN.DoesNotExist:
                    raise serializers.ValidationError(
                        {"disks": f"第 {idx + 1} 条记录要编辑的 ID {disk_id} 不存在"}
                    )

                if record.asset_code.asset_code != asset_code:
                    raise serializers.ValidationError(
                        {"disks": f"第 {idx + 1} 条记录 ID {disk_id} 不属于资产 '{asset_code}'"}
                    )

        return attrs


# ========== 组合序列化器 ==========


class CombinedAssetSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    组合资产序列化器

    用于组合资产数据库和合同数据库的信息。
    提供完整的资产和合同信息，便于前端展示。

    字段说明：
        公共字段：
            - contract_code: 合同编码

        资产信息字段：
            - asset_code: 资产编码
            - asset_name: 资产名称
            - asset_purchase_price: 采购价格
            - asset_purchase_number: 采购数量
            - asset_unit: 资产单位
            - asset_brand: 资产品牌
            - asset_specification: 资产规格
            - asset_type: 资产类型
            - asset_classification: 资产分类
            - asset_purhase_date: 采购日期
            - asset_warranty_period: 保修期
            - asset_entry_date: 入库日期
            - asset_storage: 仓库
            - asset_entry_person_jobcode: 入库人工号
            - asset_entry_person_name: 入库人姓名
            - asset_manager: 管理人
            - asset_status: 资产状态
            - asset_description: 资产描述

        合同信息字段：
            - contract_name: 合同名称
            - contract_type: 合同类型
            - contract_price: 合同金额
            - contract_supplier: 供应商
            - contract_signing_date: 签订日期
            - contract_warranty_period: 合同保修期
            - contract_preliminary_acceptance_date: 初验日期
            - contract_final_acceptance_date: 终验日期
            - contract_settlment_status: 结算状态
            - contract_settlment_price: 结算金额
            - contract_paid_count_number: 已付款次数
            - contract_paid_price: 已付款金额
            - contract_paid_record: 付款记录
    """

    contract_code = serializers.CharField(help_text="合同编码")
    asset_code = serializers.CharField(help_text="资产编码")
    asset_name = serializers.CharField(help_text="资产名称")
    asset_purchase_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="采购价格"
    )
    asset_purchase_number = serializers.IntegerField(help_text="采购数量")
    asset_unit = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="资产单位"
    )
    asset_brand = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="资产品牌"
    )
    asset_specification = serializers.CharField(help_text="资产规格")
    asset_type = serializers.CharField(help_text="资产类型")
    asset_classification = serializers.CharField(help_text="资产分类")
    asset_purhase_date = serializers.DateField(help_text="采购日期")
    asset_warranty_period = serializers.IntegerField(help_text="保修期（月）")
    asset_entry_date = serializers.DateField(help_text="入库日期")
    asset_storage = serializers.CharField(help_text="仓库名称")
    asset_entry_person_jobcode = serializers.CharField(help_text="入库人工号")
    asset_entry_person_name = serializers.CharField(help_text="入库人姓名")
    asset_manager = serializers.CharField(help_text="管理人姓名")
    asset_status = serializers.CharField(help_text="资产状态")
    # 【架构优化】移除 using_record 字段，操作历史已移至 AssetOperationLog
    asset_description = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="资产描述"
    )
    contract_name = serializers.CharField(help_text="合同名称")
    contract_type = serializers.CharField(help_text="合同类型")
    contract_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="合同金额"
    )
    contract_supplier = serializers.CharField(help_text="供应商")
    contract_signing_date = serializers.DateField(help_text="签订日期")
    contract_warranty_period = serializers.IntegerField(help_text="合同保修期（月）")
    contract_preliminary_acceptance_date = serializers.DateField(
        allow_null=True,
        help_text="初验日期"
    )
    contract_final_acceptance_date = serializers.DateField(
        allow_null=True,
        help_text="终验日期"
    )
    contract_settlment_status = serializers.CharField(help_text="结算状态")
    contract_settlment_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
        help_text="结算金额"
    )
    contract_paid_count_number = serializers.IntegerField(help_text="已付款次数")
    contract_paid_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
        help_text="已付款金额"
    )
    contract_paid_record = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        help_text="付款记录"
    )

    @classmethod
    def get_asset_details_data(cls, asset_code: str) -> Dict[str, Any]:
        """
        获取组合的资产数据

        根据资产编码查询资产和合同的完整信息，
        组合成一个完整的数据字典返回。

        Args:
            asset_code: 资产编码

        Returns:
            包含资产和合同信息的字典
        """
        combined_data: Dict[str, Any] = {
            "asset_code": asset_code,
            "asset_name": None,
            "asset_purchase_price": None,
            "asset_unit": None,
            "asset_brand": None,
            "asset_specification": None,
            "asset_type": None,
            "asset_classification": None,
            "asset_purhase_date": None,
            "asset_warranty_period": None,
            "asset_entry_date": None,
            "asset_storage": None,
            "asset_status": None,
            "asset_entry_person_jobcode": None,
            "asset_entry_person_name": None,
            "asset_manager": None,
            "asset_description": None,
            "contract_code": None,
            "contract_name": None,
            "contract_type": None,
            "contract_price": None,
            "contract_supplier": None,
            "contract_signing_date": None,
            "contract_warranty_period": None,
            "contract_preliminary_acceptance_date": None,
            "contract_final_acceptance_date": None,
            "contract_settlment_status": None,
            "contract_settlment_price": None,
            "contract_paid_count_number": None,
            "contract_paid_price": None,
            "contract_paid_record": None,
        }

        # 【AGENTS 规范 - P2-12】改用 AssetSelector.get_asset_detail_by_code()，
        # 避免 Serializer 层直接调用 Asset.objects.select_related(...).get(...)
        database_asset = AssetSelector.get_asset_detail_by_code(asset_code)
        if database_asset:
            combined_data.update({
                "asset_name": database_asset.asset_name,
                "asset_purchase_price": database_asset.asset_purchase_price,
                "asset_purchase_number": database_asset.asset_purchase_number,
                "asset_unit": database_asset.asset_unit,
                "asset_brand": database_asset.asset_brand,
                "asset_specification": database_asset.asset_specification,
                "asset_purchase_date": database_asset.asset_purchase_date,
                "asset_warranty_period": database_asset.asset_warranty_period,
                "asset_entry_date": database_asset.asset_entry_date,
                "asset_storage": (
                    database_asset.asset_storage_code.storage_name
                    if database_asset.asset_storage_code
                    else None
                ),
                "asset_status": database_asset.asset_current_status,
                "asset_entry_person_jobcode": (
                    database_asset.asset_entry_person_jobcode.employee_jobcode
                    if database_asset.asset_entry_person_jobcode
                    else None
                ),
                "asset_entry_person_name": (
                    database_asset.asset_entry_person_jobcode.employee_name
                    if database_asset.asset_entry_person_jobcode
                    else None
                ),
                "asset_manager": (
                    database_asset.asset_manager_jobcode.employee_name
                    if database_asset.asset_manager_jobcode
                    else None
                ),
                "asset_description": database_asset.asset_description,
                "asset_type": (
                    database_asset.asset_type_code.asset_type_secondary
                    if database_asset.asset_type_code
                    else None
                ),
                "asset_classification": (
                    dict(AssetType.ASSET_TYPE_CATEGORY_CHOICES).get(
                        database_asset.asset_type_code.asset_type_category, None
                    ) if database_asset.asset_type_code else None
                ),
            })

            if database_asset.asset_contract_code:
                contract = database_asset.asset_contract_code
                combined_data.update({
                    "contract_code": contract.contract_code,
                    "contract_name": contract.contract_name,
                    "contract_type": contract.contract_type,
                    "contract_price": contract.contract_price,
                    "contract_supplier": contract.contract_supplier,
                    "contract_signing_date": contract.contract_signing_date,
                    "contract_warranty_period": contract.contract_warranty_period,
                    "contract_preliminary_acceptance_date": (
                        contract.contract_preliminary_acceptance_date
                    ),
                    "contract_final_acceptance_date": (
                        contract.contract_final_acceptance_date
                    ),
                    "contract_settlment_status": contract.contract_settlment_status,
                    "contract_settlment_price": contract.contract_settlment_price,
                    "contract_paid_count_number": contract.contract_paid_count_number,
                    "contract_paid_price": contract.contract_paid_price,
                    "contract_paid_record": contract.contract_paid_record,
                })

        return combined_data


# ========== 通用序列化器 ==========


class DashboardStatSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    仪表盘统计序列化器

    用于仪表盘统计数据的序列化。
    提供资产总数、合同总数、在用资产数等统计信息。

    字段说明：
        - total_assets: 资产总数
        - total_contracts: 合同总数
        - active_assets: 在用资产数
    """

    total_assets = serializers.IntegerField(help_text="资产总数")
    total_contracts = serializers.IntegerField(help_text="合同总数")
    active_assets = serializers.IntegerField(help_text="在用资产数")


class ErrorResponseSerializer(serializers.Serializer[Dict[str, Any]]):
    """
    错误响应序列化器

    用于统一错误响应格式。
    所有API错误响应都使用此序列化器。

    字段说明：
        - success: 请求是否成功（固定为False）
        - error: 错误描述信息
        - debug_info: 调试信息（可选）
    """

    success = serializers.BooleanField(
        default=False,
        help_text="请求是否成功"
    )
    error = serializers.CharField(help_text="错误描述")
    debug_info = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="调试信息（可选）"
    )


class EmptySerializer(serializers.Serializer[None]):
    """
    空序列化器

    用于不需要请求体或响应体的API端点。
    例如：删除操作、注销操作等。
    """

    pass


# ========== 资产操作记录序列化器 ==========


class AssetOperationLogSerializer(serializers.ModelSerializer[AssetOperationLog]):
    """
    资产操作记录序列化器

    【AGENTS 规范 - 架构优化】
    用于资产操作记录的序列化，支持查询操作。

    字段说明：
        - id: 记录ID
        - asset_code: 资产编码
        - operation_type: 操作类型
        - operation_type_display: 操作类型中文显示
        - operation_time: 操作时间
        - operator_jobcode: 操作人工号
        - operator_name: 操作人姓名
        - before_data: 变更前数据（JSON）
        - after_data: 变更后数据（JSON）
        - description: 操作描述
        - related_record_code: 关联记录编码
        - related_record_type: 关联记录类型
        - ip_address: 操作IP地址

    【易错点】
    - 此序列化器仅用于查询，不支持创建/更新/删除
    - before_data 和 after_data 为 JSON 格式，前端需自行解析
    """

    operation_type_display = serializers.CharField(
        source="get_operation_type_display",
        read_only=True,
        help_text="操作类型中文显示"
    )

    class Meta:
        model: Type[AssetOperationLog] = AssetOperationLog
        fields = [
            'id',
            'logging_id',
            'asset_code',
            'operation_type',
            'operation_type_display',
            'operation_time',
            'operator_jobcode',
            'operator_name',
            'before_data',
            'after_data',
            'description',
            'related_record_code',
            'related_record_type',
            'ip_address',
        ]
        # 【重要】所有字段均为只读
        read_only_fields = fields



class AssetBatchItemSerializer(serializers.Serializer):
    """单条资产批量创建数据校验"""
    row_number = serializers.IntegerField(required=False, help_text="Excel 行号（前端传入，用于错误定位）")
    asset_name = serializers.CharField(required=True)
    asset_type_code = serializers.SlugRelatedField(
        queryset=AssetType.objects.filter(is_deleted=False),
        slug_field='asset_type_code',
        required=True
    )
    asset_purchase_price = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
    asset_purchase_date = serializers.DateField(required=False)
    asset_entry_date = serializers.DateField(required=False)
    asset_storage_code = serializers.SlugRelatedField(
        queryset=Storage.objects.filter(is_deleted=False),
        slug_field='storage_code',
        required=False
    )
    asset_contract_code = serializers.SlugRelatedField(
        queryset=Contract.objects.filter(is_deleted=False),
        slug_field='contract_code',
        required=False
    )
    asset_purchase_number = serializers.IntegerField(required=False, default=1, min_value=1)
    asset_department_code = serializers.SlugRelatedField(
        queryset=Department.objects.filter(is_deleted=False),
        slug_field='department_code',
        required=False
    )
    asset_employee_jobcode = serializers.SlugRelatedField(
        queryset=Employee.objects.filter(is_deleted=False),
        slug_field='employee_jobcode',
        required=False
    )
    asset_remark = serializers.CharField(required=False, allow_blank=True)


class AssetBatchCreateSerializer(serializers.Serializer):
    """批量创建请求校验"""
    MAX_BATCH_SIZE = 100
    items = AssetBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: List[Dict]) -> List[Dict]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条，"
                f"当前 {len(value)} 条，请分 {len(value) // self.MAX_BATCH_SIZE + 1} 批提交"
            )
        from collections import Counter
        names = [item.get('asset_name') for item in value if item.get('asset_name')]
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            raise serializers.ValidationError(
                f"提交记录中存在重复资产名称: {', '.join(duplicates)}"
            )
        return value


class AssetBatchDeleteSerializer(serializers.Serializer):
    """批量删除请求校验"""
    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="资产编码列表"
    )

    def validate_ids(self, value: List[str]) -> List[str]:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条"
            )
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
