"""
资产 CRUD 相关序列化器

包含 Asset、AssetCreate、AssetDetail、AssetUpdate、CombinedAsset、
AssetOperationLog、CombineSearch 等序列化器。
"""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.assetmanagement.interfaces import (
    get_employee_queryset,
    get_employee_serializer_class,
)
from apps.assetmanagement.models import Asset, AssetOperationLog, AssetType, Contract, Storage
from apps.assetmanagement.selectors import AssetSelector
from apps.assetmanagement.serializers.base_model_serializers import (
    AssetTypeSerializer,
    ContractSerializer,
    HardDiskSNSimpleSerializer,
    StorageSerializer,
)


class AssetListSerializer(serializers.ModelSerializer):
    """资产列表序列化器(精简版)"""

    type_category = serializers.CharField(source="asset_type_recordcode.type_code", read_only=True)
    asset_type_name = serializers.CharField(source="asset_type_recordcode.type_name", read_only=True, allow_null=True)
    contract_code = serializers.CharField(
        source="asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    contract_name = serializers.CharField(
        source="asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    storage_code = serializers.CharField(
        source="asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    storage_name = serializers.CharField(
        source="asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    entry_person_name = serializers.CharField(
        source="asset_entry_person_recordcode.employee_name", read_only=True, allow_null=True
    )
    applicant_name = serializers.CharField(
        source="asset_applicant_recordcode.employee_name", read_only=True, allow_null=True
    )
    manager_name = serializers.CharField(
        source="asset_manager_recordcode.employee_name", read_only=True, allow_null=True
    )

    class Meta:
        model = Asset
        fields = [
            "recordcode",
            "asset_code",
            "asset_name",
            "asset_brand",
            "asset_unit",
            "asset_purchase_number",
            "asset_specification",
            "asset_purchase_price",
            "asset_purchase_date",
            "asset_warranty_period",
            "asset_current_status",
            "asset_description",
            "asset_using_location",
            "asset_entry_date",
            "type_category",
            "asset_type_name",
            "contract_code",
            "contract_name",
            "storage_code",
            "storage_name",
            "entry_person_name",
            "applicant_name",
            "manager_name",
            "is_active",
            "version",
        ]
        read_only_fields = fields


# ==================== 保持向后兼容 ====================
AssetSerializer = AssetListSerializer


class AssetDetailSerializer(serializers.ModelSerializer):
    # 使用 source 参数映射后端字段名到前端字段名(读取时)
    asset_type = AssetTypeSerializer(source="asset_type_recordcode", read_only=True)
    asset_contract = ContractSerializer(source="asset_contract_recordcode", read_only=True)
    asset_storage = StorageSerializer(source="asset_storage_recordcode", read_only=True)
    asset_entry_person = get_employee_serializer_class()(source="asset_entry_person_recordcode", read_only=True)
    asset_applicant = get_employee_serializer_class()(source="asset_applicant_recordcode", read_only=True)
    asset_manager = get_employee_serializer_class()(source="asset_manager_recordcode", read_only=True)
    harddisk_sns = HardDiskSNSimpleSerializer(many=True, read_only=True)

    class Meta:
        model = Asset
        fields = [
            "recordcode",
            "asset_code",
            "asset_name",
            "asset_brand",
            "asset_unit",
            "asset_purchase_number",
            "asset_specification",
            "asset_purchase_price",
            "asset_purchase_date",
            "asset_warranty_period",
            "asset_current_status",
            "asset_description",
            "asset_using_location",
            "asset_entry_date",
            "asset_type",
            "asset_contract",
            "asset_storage",
            "asset_entry_person",
            "asset_applicant",
            "asset_manager",
            "harddisk_sns",
            "is_active",
            "version",
        ]


class AssetUpdateSerializer(serializers.ModelSerializer):
    """资产更新序列化器

    排除 recordcode 和 asset_code(后端自动生成,不可修改)。
    前端传入业务编码(asset_type_code/contract_code/storage_code/employee_jobcode),
    DRF SlugRelatedField 自动转换为 recordcode 存入数据库。
    """

    # FK 字段:前端传入业务编码,DRF 自动转换为 recordcode
    asset_type = serializers.SlugRelatedField(
        slug_field="type_code",
        queryset=AssetType.objects.filter(is_deleted=False),
        source="asset_type_recordcode",
        required=False,
    )
    asset_contract = serializers.SlugRelatedField(
        slug_field="contract_code",
        queryset=Contract.objects.filter(is_deleted=False),
        source="asset_contract_recordcode",
        allow_null=True,
        required=False,
    )
    asset_storage = serializers.SlugRelatedField(
        slug_field="storage_code",
        queryset=Storage.objects.filter(is_deleted=False),
        source="asset_storage_recordcode",
        allow_null=True,
        required=False,
    )
    asset_entry_person = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_entry_person_recordcode",
        allow_null=True,
        required=False,
    )
    asset_applicant = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_applicant_recordcode",
        allow_null=True,
        required=False,
    )
    asset_manager = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_manager_recordcode",
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Asset
        fields = [
            "asset_name",
            "asset_purchase_price",
            "asset_purchase_number",
            "asset_unit",
            "asset_brand",
            "asset_specification",
            "asset_type",
            "asset_contract",
            "asset_purchase_date",
            "asset_warranty_period",
            "asset_entry_date",
            "asset_storage",
            "asset_entry_person",
            "asset_applicant",
            "asset_manager",
            "asset_using_location",
            "asset_current_status",
            "asset_description",
        ]
        extra_kwargs = {
            "asset_name": {"required": False},
            "asset_purchase_price": {"required": False, "write_only": True},
            "asset_purchase_date": {"required": False},
            "asset_entry_date": {"required": False},
        }


class AssetCreateSerializer(serializers.ModelSerializer):
    """资产创建序列化器

    前端传入业务编码(asset_type_code/contract_code/storage_code/employee_jobcode),
    DRF SlugRelatedField 自动转换为 recordcode 存入数据库。

    字段名约定(前端字段名 → 后端模型字段名):
    - asset_type → asset_type_recordcode: 传入 AssetType.asset_type_code(如 "AT001")
    - asset_contract → asset_contract_recordcode: 传入 Contract.contract_code(如 "CT001")
    - asset_storage → asset_storage_recordcode: 传入 Storage.storage_code(如 "ST001")
    - asset_entry_person → asset_entry_person_recordcode: 传入 Employee.employee_jobcode(如 "E001")
    - asset_applicant → asset_applicant_recordcode: 传入 Employee.employee_jobcode(如 "E002")
    - asset_manager → asset_manager_recordcode: 传入 Employee.employee_jobcode(如 "E003")
    """

    asset_code = serializers.CharField(max_length=64, read_only=True)

    # FK 字段:前端传入业务编码,DRF 自动转换为 recordcode
    # 使用 source 参数映射前端字段名到后端模型字段名
    asset_type = serializers.SlugRelatedField(
        slug_field="type_code",
        queryset=AssetType.objects.filter(is_deleted=False),
        source="asset_type_recordcode",
    )
    asset_contract = serializers.SlugRelatedField(
        slug_field="contract_code",
        queryset=Contract.objects.filter(is_deleted=False),
        source="asset_contract_recordcode",
        allow_null=True,
        required=False,
    )
    asset_storage = serializers.SlugRelatedField(
        slug_field="storage_code",
        queryset=Storage.objects.filter(is_deleted=False),
        source="asset_storage_recordcode",
        allow_null=True,
        required=False,
    )
    asset_entry_person = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_entry_person_recordcode",
        allow_null=True,
        required=False,
    )
    asset_applicant = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_applicant_recordcode",
        allow_null=True,
        required=False,
    )
    asset_manager = serializers.SlugRelatedField(
        slug_field="employee_jobcode",
        queryset=get_employee_queryset(),
        source="asset_manager_recordcode",
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Asset
        fields = [
            "asset_code",
            "asset_name",
            "asset_purchase_price",
            "asset_purchase_number",
            "asset_unit",
            "asset_brand",
            "asset_specification",
            "asset_type",
            "asset_contract",
            "asset_purchase_date",
            "asset_warranty_period",
            "asset_entry_date",
            "asset_storage",
            "asset_entry_person",
            "asset_applicant",
            "asset_manager",
            "asset_using_location",
            "asset_current_status",
            "asset_description",
        ]
        extra_kwargs = {
            "asset_name": {"required": True},
            "asset_purchase_price": {"required": True, "write_only": True},
            "asset_purchase_date": {"required": True},
            "asset_entry_date": {"required": True},
            "asset_purchase_number": {"required": False, "default": 1},
            "asset_warranty_period": {"required": False, "default": 0},
            "asset_current_status": {"required": False, "default": "in_store"},
            "asset_unit": {"required": False, "allow_blank": True, "allow_null": True},
            "asset_brand": {"required": False, "allow_blank": True, "allow_null": True},
            "asset_specification": {"required": False, "allow_blank": True, "allow_null": True},
            "asset_using_location": {"required": False, "allow_blank": True, "allow_null": True},
            "asset_description": {"required": False, "allow_blank": True, "allow_null": True},
        }

    def validate_asset_purchase_price(self, value):
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        return value


class CombinedAssetSerializer(serializers.Serializer):
    contract_code = serializers.CharField()
    asset_code = serializers.CharField()
    asset_name = serializers.CharField()
    asset_purchase_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    asset_purchase_number = serializers.IntegerField()
    asset_unit = serializers.CharField(allow_blank=True, allow_null=True)
    asset_brand = serializers.CharField(allow_blank=True, allow_null=True)
    asset_specification = serializers.CharField()
    asset_type = serializers.CharField()
    asset_classification = serializers.CharField()
    # 【P1-21 修复】字段名拼写修正:purhase → purchase
    asset_purchase_date = serializers.DateField()
    asset_warranty_period = serializers.IntegerField()
    asset_entry_date = serializers.DateField()
    asset_storage = serializers.CharField()
    asset_entry_person = serializers.CharField()
    asset_entry_person_name = serializers.CharField()
    asset_manager = serializers.CharField()
    asset_status = serializers.CharField()
    asset_description = serializers.CharField(allow_blank=True, allow_null=True)
    contract_name = serializers.CharField()
    contract_type = serializers.CharField()
    supplier_name = serializers.CharField(allow_blank=True, allow_null=True)
    contract_amount = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    settlemented_price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    contract_total_quantity = serializers.IntegerField(allow_null=True)
    contract_start_date = serializers.DateField(allow_null=True)
    contract_end_date = serializers.DateField(allow_null=True)
    contract_status = serializers.CharField(allow_blank=True, allow_null=True)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    amount_unpaid = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    paid_record = serializers.CharField(allow_blank=True, allow_null=True)

    @classmethod
    def get_asset_details_data(cls, asset_code: str) -> dict[str, Any]:
        database_asset = AssetSelector.get_asset_detail_by_code(asset_code)
        if not database_asset:
            return {"asset_code": asset_code}
        return AssetDetailSerializer(database_asset).data


class AssetOperationLogSerializer(serializers.ModelSerializer):
    """
    资产操作记录序列化器

    asset_name 和 asset_specification 直接从模型字段读取(冗余存储),
    删除 Asset 不影响操作日志记录。
    """

    operation_type_display = serializers.CharField(source="get_operation_type_display", read_only=True)

    class Meta:
        model = AssetOperationLog
        fields = [
            "id",
            "logging_id",
            "asset_code",
            "asset_name",
            "asset_specification",
            "operation_type",
            "operation_type_display",
            "operation_time",
            "operator_jobcode",
            "operator_name",
            "before_data",
            "after_data",
            "description",
            "related_record_code",
            "related_record_type",
            "ip_address",
        ]
        read_only_fields = fields


class CombineSearchSerializer(serializers.Serializer):
    """
    资产组合搜索序列化器

    - 模糊字段:asset_name, asset_specification, asset_brand
    - 精确字段:asset_current_status, asset_type, asset_storage, asset_contract
    """

    # 模糊匹配字段(支持包含搜索)
    asset_name = serializers.CharField(required=False, allow_blank=True)
    asset_specification = serializers.CharField(required=False, allow_blank=True)
    asset_brand = serializers.CharField(required=False, allow_blank=True)

    # 精确匹配字段(字段名与 Asset 模型一致)
    asset_current_status = serializers.CharField(required=False, allow_blank=True)
    asset_type = serializers.CharField(required=False, allow_blank=True)
    asset_storage = serializers.CharField(required=False, allow_blank=True)
    asset_contract = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        # 去除空字符串,统一转为 None 或空值,便于后续过滤
        for key, value in attrs.items():
            if value == "":
                attrs[key] = None
        return attrs
