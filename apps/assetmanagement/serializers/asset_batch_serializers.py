"""
资产批量操作相关序列化器

包含 AssetBatchItem、AssetBatchCreate、AssetBatchDelete 序列化器。
"""

from typing import Any

from rest_framework import serializers

from apps.assetmanagement.models import AssetType, Contract, Storage
from apps.usermanagement.models import Employee
from core.batch_mixins import BatchDeleteValidationMixin
from core.constants import MAX_BATCH_SIZE as DEFAULT_MAX_BATCH_SIZE


class AssetBatchItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量创建资产序列化器

    前端传入业务编码(asset_type_code/storage_code/contract_code/employee_jobcode),
    DRF SlugRelatedField 自动转换为 recordcode 存入数据库。

    字段名约定(与 Asset 模型一致):
    - asset_type: 传入 AssetType.asset_type_code(如 "AT001")
    - asset_contract: 传入 Contract.contract_code(如 "CT001")
    - asset_storage: 传入 Storage.storage_code(如 "ST001")
    - asset_entry_person: 传入 Employee.employee_jobcode(如 "E001")
    - asset_applicant: 传入 Employee.employee_jobcode(如 "E002")
    - asset_manager: 传入 Employee.employee_jobcode(如 "E003")
    """

    row_number = serializers.IntegerField(required=False, help_text="行号,用于错误定位")
    asset_name = serializers.CharField(required=True, help_text="资产名称")
    asset_type = serializers.SlugRelatedField(
        queryset=AssetType.objects.filter(is_deleted=False),
        slug_field="type_code",
        source="asset_type_recordcode",
        required=True,
        help_text="资产类型编码",
    )
    asset_purchase_price = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, help_text="购买价格", write_only=True
    )
    asset_purchase_date = serializers.DateField(required=False, help_text="购买日期")
    asset_entry_date = serializers.DateField(required=False, help_text="入库日期")
    asset_storage = serializers.SlugRelatedField(
        queryset=Storage.objects.filter(is_deleted=False),
        slug_field="storage_code",
        source="asset_storage_recordcode",
        required=False,
        allow_null=True,
        help_text="仓库编码",
    )
    asset_contract = serializers.SlugRelatedField(
        queryset=Contract.objects.filter(is_deleted=False),
        slug_field="contract_code",
        source="asset_contract_recordcode",
        required=False,
        allow_null=True,
        help_text="合同编码",
    )
    asset_purchase_number = serializers.IntegerField(required=False, default=1, min_value=1, help_text="购买数量")
    asset_entry_person = serializers.SlugRelatedField(
        queryset=Employee.objects.filter(is_deleted=False),
        slug_field="employee_jobcode",
        source="asset_entry_person_recordcode",
        required=False,
        allow_null=True,
        help_text="入库人工号",
    )
    asset_applicant = serializers.SlugRelatedField(
        queryset=Employee.objects.filter(is_deleted=False),
        slug_field="employee_jobcode",
        source="asset_applicant_recordcode",
        required=False,
        allow_null=True,
        help_text="申请人工号",
    )
    asset_manager = serializers.SlugRelatedField(
        queryset=Employee.objects.filter(is_deleted=False),
        slug_field="employee_jobcode",
        source="asset_manager_recordcode",
        required=False,
        allow_null=True,
        help_text="保管人工号",
    )
    asset_specification = serializers.CharField(required=False, allow_blank=True, allow_null=True, help_text="资产规格")
    asset_brand = serializers.CharField(required=False, allow_blank=True, allow_null=True, help_text="资产品牌")
    asset_unit = serializers.CharField(required=False, allow_blank=True, allow_null=True, help_text="资产单位")
    asset_warranty_period = serializers.IntegerField(required=False, default=0, help_text="保修期(年)")
    asset_description = serializers.CharField(required=False, allow_blank=True, allow_null=True, help_text="资产描述")
    asset_using_location = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, help_text="使用地点"
    )


class AssetBatchCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    items = AssetBatchItemSerializer(many=True, required=True)

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("批量创建至少需要 1 条记录")
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        from collections import Counter

        names = [item.get("asset_name") for item in value if item.get("asset_name")]
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            raise serializers.ValidationError(f"提交记录中存在重复资产名称: {', '.join(duplicates)}")  # type: ignore[arg-type]
        return value


class AssetBatchDeleteSerializer(BatchDeleteValidationMixin, serializers.Serializer):  # type: ignore[type-arg]
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    ids = serializers.ListField(child=serializers.CharField(), required=True)
