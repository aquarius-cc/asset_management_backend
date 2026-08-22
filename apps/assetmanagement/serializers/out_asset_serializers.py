"""
出库相关序列化器

包含 OutAsset 及其批量操作序列化器。

【AGENTS 规范 - 序列化器分层设计】
每个模块按 Action 分离序列化器:
- ListSerializer: 列表查询(扁平字段,只读,精简)
- CreateSerializer: 创建操作(写入字段)
- DetailSerializer: 详情查询(嵌套对象,只读,完整)
"""

from rest_framework import serializers

from apps.assetmanagement.interfaces import get_employee_queryset, get_employee_serializer_class
from apps.assetmanagement.models import Asset, OutAsset
from apps.assetmanagement.serializers.base_model_serializers import ContractSerializer
from core.constants import MAX_BATCH_SIZE as DEFAULT_MAX_BATCH_SIZE


# ==================== OutAsset 序列化器 ====================


class OutAssetListSerializer(serializers.ModelSerializer):
    """
    出库记录列表序列化器
    用途:list, recyclable action
    特点:扁平字段,只读,精简性能优化
    """

    asset_recordcode = serializers.CharField(source="asset_recordcode.recordcode", read_only=True)
    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)
    asset_brand = serializers.CharField(source="asset_recordcode.asset_brand", read_only=True, allow_null=True)
    outasset_current_status = serializers.CharField(source="asset_recordcode.asset_current_status", read_only=True)
    outasset_applicant_name = serializers.CharField(
        source="asset_recordcode.asset_applicant_recordcode.employee_name", read_only=True, allow_null=True
    )
    outasset_manager_name = serializers.CharField(
        source="asset_recordcode.asset_manager_recordcode.employee_name", read_only=True, allow_null=True
    )
    outasset_manager_jobcode = serializers.CharField(
        source="asset_recordcode.asset_manager_recordcode.employee_jobcode", read_only=True, allow_null=True
    )
    outasset_manager_department = serializers.CharField(
        source="asset_recordcode.asset_manager_recordcode.employee_department_name", read_only=True, allow_null=True
    )

    class Meta:
        model = OutAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "asset_brand",
            "outasset_number",
            "outasset_date",
            "outasset_type",
            "outasset_current_status",
            "outasset_description",
            "outasset_applicant_name",
            "outasset_manager_name",
            "outasset_manager_jobcode",
            "outasset_manager_department",
            "return_date",
            "outasset_previous_status",
        ]
        read_only_fields = fields


class OutAssetCreateSerializer(serializers.ModelSerializer):
    """
    出库记录创建序列化器
    用途:create, update, partial_update action
    特点:写入字段,SlugRelatedField 自动转换业务编码为 recordcode
    """

    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False)
    )
    recordcode = serializers.CharField(read_only=True)
    outasset_using_location = serializers.CharField(required=False, write_only=True, allow_blank=True, allow_null=True)

    class Meta:
        model = OutAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "outasset_number",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "return_date",
            "outasset_using_location",
        ]
        extra_kwargs = {
            "outasset_number": {"required": False, "default": 1},
            "outasset_type": {"required": True},
            "outasset_date": {"required": True},
        }

    def create(self, validated_data):
        validated_data.pop("outasset_using_location", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("outasset_using_location", None)
        return super().update(instance, validated_data)


class OutAssetDetailSerializer(serializers.ModelSerializer):
    """
    出库记录详情序列化器
    用途:retrieve action
    特点:嵌套对象,只读,完整字段
    """

    asset_recordcode = serializers.CharField(source="asset_recordcode.recordcode", read_only=True)
    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)
    contract = ContractSerializer(source="asset_recordcode.asset_contract_recordcode", read_only=True, allow_null=True)
    outasset_current_status = serializers.CharField(source="asset_recordcode.asset_current_status", read_only=True)
    outasset_applicant = get_employee_serializer_class()(
        source="asset_recordcode.asset_applicant_recordcode", read_only=True, allow_null=True
    )
    outasset_manager = get_employee_serializer_class()(
        source="asset_recordcode.asset_manager_recordcode", read_only=True, allow_null=True
    )
    outasset_using_location = serializers.CharField(
        source="asset_recordcode.asset_using_location", read_only=True, allow_null=True
    )
    outasset_snapshot = serializers.JSONField(read_only=True, allow_null=True)

    class Meta:
        model = OutAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "outasset_number",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "outasset_current_status",
            "outasset_previous_status",
            "contract",
            "return_date",
            "outasset_applicant",
            "outasset_manager",
            "outasset_using_location",
            "outasset_snapshot",
        ]
        read_only_fields = fields


class OutAssetUpdateSerializer(serializers.ModelSerializer):
    """
    出库记录更新序列化器
    用途:update, partial_update action
    特点:写入字段,recordcode 和 asset_recordcode 只读
    """

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = OutAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "outasset_number",
            "outasset_date",
            "outasset_type",
            "outasset_description",
            "return_date",
        ]
        extra_kwargs = {
            "outasset_number": {"required": False},
            "outasset_type": {"required": False},
            "outasset_date": {"required": False},
        }


# ==================== 保持向后兼容 ====================
# 旧的序列化器名称别名,用于批量操作等场景
OutAssetSerializer = OutAssetCreateSerializer


# ========== 批量操作序列化器(OutAsset) ==========


class OutAssetBatchItemSerializer(serializers.Serializer):
    row_number = serializers.IntegerField(required=False)
    outasset_asset = serializers.SlugRelatedField(
        slug_field="asset_code",
        queryset=Asset.objects.filter(is_deleted=False, asset_current_status="in_store"),
        required=True,
    )
    outasset_number = serializers.IntegerField(required=False, default=1, min_value=1)
    outasset_date = serializers.DateField(required=False)
    outasset_type = serializers.CharField(required=True)
    outasset_description = serializers.CharField(required=False, allow_blank=True)
    return_date = serializers.DateField(required=False, allow_null=True)
    outasset_applicant = serializers.SlugRelatedField(
        slug_field="employee_jobcode", queryset=get_employee_queryset(), required=True, write_only=True
    )
    outasset_manager = serializers.SlugRelatedField(
        slug_field="employee_jobcode", queryset=get_employee_queryset(), required=True, write_only=True
    )
    outasset_using_location = serializers.CharField(required=True, write_only=True)


class OutAssetBatchCreateSerializer(serializers.Serializer):
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    items = OutAssetBatchItemSerializer(many=True, required=True)

    def validate_items(self, value):
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        # 【P0-14 修复】字段名应为 outasset_asset(非 outasset_code)
        asset_codes = [item["outasset_asset"].asset_code for item in value]
        if len(asset_codes) != len(set(asset_codes)):
            raise serializers.ValidationError("提交记录中存在重复的资产编码")
        return value


class OutAssetBatchDeleteSerializer(serializers.Serializer):
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    ids = serializers.ListField(child=serializers.CharField(), required=True)

    def validate_ids(self, value):
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
