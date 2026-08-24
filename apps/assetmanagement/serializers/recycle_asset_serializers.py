"""
回收资产相关序列化器

包含 RecycleAsset 及其批量操作序列化器。

【AGENTS 规范 - 序列化器分层设计】
每个模块按 Action 分离序列化器:
- ListSerializer: 列表查询(扁平字段,只读,精简)
- CreateSerializer: 创建操作(写入字段)
- DetailSerializer: 详情查询(嵌套对象,只读,完整)
"""

from typing import Any

from rest_framework import serializers

from apps.assetmanagement.interfaces import get_employee_queryset
from apps.assetmanagement.models import OutAsset, RecycleAsset, Storage
from apps.assetmanagement.serializers.asset_crud_serializers import AssetDetailSerializer
from core.constants import MAX_BATCH_SIZE as DEFAULT_MAX_BATCH_SIZE


# ==================== RecycleAsset 序列化器 ====================


class RecycleAssetListSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    回收资产列表序列化器
    用途:list action
    特点:扁平字段,只读,精简
    """

    outasset_recordcode = serializers.CharField(source="outasset_recordcode.recordcode", read_only=True)
    asset_recordcode = serializers.CharField(source="asset_recordcode.recordcode", read_only=True)
    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)
    contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    using_person_name = serializers.CharField(
        source="asset_recordcode.asset_manager_recordcode.employee_name", read_only=True, allow_null=True
    )
    using_person_jobcode = serializers.CharField(
        source="asset_recordcode.asset_manager_recordcode.employee_jobcode", read_only=True, allow_null=True
    )
    recycle_person_jobcode = serializers.CharField(
        source="operator_employee.employee_jobcode", read_only=True, allow_null=True
    )
    recycle_person_name = serializers.CharField(
        source="operator_employee.employee_name", read_only=True, allow_null=True
    )

    class Meta:
        model = RecycleAsset
        fields = [
            "recordcode",
            "outasset_recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "contract_code",
            "storage_name",
            "recycle_asset_date",
            "recycle_asset_description",
            "recycle_person_jobcode",
            "recycle_person_name",
            "using_person_jobcode",
            "using_person_name",
            "recycle_asset_number",
            "recycle_type",
            "is_broken",
            "broken_reason",
            "is_lost",
            "lost_reason",
            "is_active",
        ]
        read_only_fields = fields


class RecycleAssetCreateSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    回收资产创建序列化器
    用途:create, update, partial_update action
    特点:写入字段,SlugRelatedField 自动转换
    """

    recordcode = serializers.CharField(read_only=True)
    outasset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=OutAsset.objects.filter(is_deleted=False)
    )
    asset_recordcode = serializers.CharField(source="asset_recordcode.recordcode", read_only=True)
    storage_code = serializers.SlugRelatedField(
        slug_field="storage_code", queryset=Storage.objects.all(), required=True, write_only=True
    )

    class Meta:
        model = RecycleAsset
        fields = [
            "recordcode",
            "outasset_recordcode",
            "asset_recordcode",
            "storage_code",
            "recycle_asset_date",
            "recycle_asset_description",
            "recycle_asset_number",
            "recycle_type",
            "is_broken",
            "broken_reason",
            "is_lost",
            "lost_reason",
            "is_active",
        ]
        extra_kwargs = {
            "recycle_asset_number": {"required": False, "default": 1},
            "recycle_asset_date": {"required": True},
            "recycle_type": {"required": True},
            "is_broken": {"required": False, "default": False},
            "broken_reason": {"required": False, "max_length": 100},
            "is_lost": {"required": False, "default": False},
            "lost_reason": {"required": False, "max_length": 100},
        }

    def validate(self, attrs: Any) -> None:
        if attrs.get("is_broken") and attrs.get("is_lost"):
            raise serializers.ValidationError("is_broken 和 is_lost 不能同时为 True")
        return attrs  # type: ignore[no-any-return]

    def create(self, validated_data: Any) -> RecycleAsset:
        validated_data.pop("recycle_asset_recycle_person_jobcode", None)
        validated_data.pop("recycle_asset_storage", None)
        return super().create(validated_data)  # type: ignore[no-any-return]


class RecycleAssetDetailSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    回收资产详情序列化器
    用途:retrieve action
    特点:嵌套对象,只读,完整
    """

    asset = AssetDetailSerializer(source="asset_recordcode", read_only=True)
    recycle_person_jobcode = serializers.CharField(
        source="operator_employee.employee_jobcode", read_only=True, allow_null=True
    )
    recycle_person_name = serializers.CharField(
        source="operator_employee.employee_name", read_only=True, allow_null=True
    )
    recycle_person_department = serializers.CharField(
        source="operator_employee.employee_department.department_name", read_only=True, allow_null=True
    )

    class Meta:
        model = RecycleAsset
        fields = [
            "id",
            "recordcode",
            "outasset_recordcode",
            "asset_recordcode",
            "recycle_asset_date",
            "recycle_asset_description",
            "asset",
            "recycle_person_jobcode",
            "recycle_person_name",
            "recycle_person_department",
            "recycle_asset_number",
            "recycle_type",
            "is_active",
        ]


class RecycleAssetUpdateSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    回收资产更新序列化器
    用途:update, partial_update action
    特点:写入字段,recordcode 和关联字段只读
    """

    recordcode = serializers.CharField(read_only=True)
    outasset_recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(source="asset_recordcode.recordcode", read_only=True)

    class Meta:
        model = RecycleAsset
        fields = [
            "recordcode",
            "outasset_recordcode",
            "asset_recordcode",
            "recycle_asset_date",
            "recycle_asset_description",
            "recycle_asset_number",
            "recycle_type",
            "is_active",
        ]
        extra_kwargs = {
            "recycle_asset_number": {"required": False},
            "recycle_asset_date": {"required": False},
            "recycle_type": {"required": False},
        }


# ==================== 保持向后兼容 ====================
RecycleAssetSerializer = RecycleAssetCreateSerializer


# ========== 批量操作序列化器(RecycleAsset) ==========


class RecycleAssetBatchItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    row_number = serializers.IntegerField(required=False)
    recycle_outasset_code = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=OutAsset.objects.filter(is_deleted=False), required=True
    )
    recycle_date = serializers.DateField(required=False)
    recycle_type = serializers.CharField(required=True)
    recycle_description = serializers.CharField(required=False, allow_blank=True)


class RecycleAssetBatchCreateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    items = RecycleAssetBatchItemSerializer(many=True, required=True)
    recycle_asset_storage = serializers.SlugRelatedField(
        slug_field="storage_code", queryset=Storage.objects.all(), required=False, allow_null=True
    )
    recycle_asset_recycle_person_jobcode = serializers.SlugRelatedField(  # type: ignore[var-annotated]
        slug_field="employee_jobcode", queryset=get_employee_queryset(), required=False, allow_null=True
    )

    def validate_items(self, value: Any) -> None:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量创建不能超过 {self.MAX_BATCH_SIZE} 条")
        outasset_codes = [item["recycle_outasset_code"].recordcode for item in value]
        if len(outasset_codes) != len(set(outasset_codes)):
            raise serializers.ValidationError("提交记录中存在重复的出库记录编码")
        return value  # type: ignore[no-any-return]


class RecycleAssetBatchDeleteSerializer(serializers.Serializer):  # type: ignore[type-arg]
    MAX_BATCH_SIZE = DEFAULT_MAX_BATCH_SIZE  # DR-1: 常量单一来源(core/constants.py)
    ids = serializers.ListField(child=serializers.CharField(), required=True)

    def validate_ids(self, value: Any) -> None:
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value  # type: ignore[no-any-return]
