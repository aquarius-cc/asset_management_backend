"""
RepairAsset serializers
"""

from rest_framework import serializers

from apps.assetmanagement.models import Asset, RepairAsset


class RepairAssetListSerializer(serializers.ModelSerializer):
    """Repair record list serializer - list action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)

    class Meta:
        model = RepairAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "repair_date",
            "repair_status",
            "repair_reason",
            "operator_name",
            "created_at",
        ]
        read_only_fields = fields


class RepairAssetCreateSerializer(serializers.ModelSerializer):
    """Repair record create serializer - create action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode",
        queryset=Asset.objects.filter(is_deleted=False),
        write_only=True,
    )

    class Meta:
        model = RepairAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "repair_date",
            "expected_return_date",
            "repair_reason",
            "repair_description",
        ]
        extra_kwargs = {
            "repair_reason": {"required": True},
            "repair_date": {"required": False},
        }


class RepairAssetUpdateSerializer(serializers.ModelSerializer):
    """Repair record update serializer - update/partial_update action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = RepairAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "repair_date",
            "expected_return_date",
            "actual_return_date",
            "repair_status",
            "repair_reason",
            "repair_description",
            "repair_cost",
            "physical_grade_before",
            "physical_grade_after",
        ]
        extra_kwargs = {"repair_reason": {"required": False}}


class RepairAssetDetailSerializer(serializers.ModelSerializer):
    """Repair record detail serializer - retrieve action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    asset_specification = serializers.CharField(
        source="asset_recordcode.asset_specification", read_only=True, allow_null=True
    )
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)
    operator_jobcode = serializers.CharField(
        source="operator_employee.employee_jobcode", read_only=True, allow_null=True
    )

    class Meta:
        model = RepairAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "repair_date",
            "expected_return_date",
            "actual_return_date",
            "repair_status",
            "repair_reason",
            "repair_description",
            "repair_cost",
            "physical_grade_before",
            "physical_grade_after",
            "operator_employee",
            "operator_name",
            "operator_jobcode",
            "version",
            "created_at",
            "updated_at",
        ]


# Backward compatibility
RepairAssetSerializer = RepairAssetListSerializer


class RepairAssetBatchDeleteSerializer(serializers.Serializer):
    """维修资产批量删除请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="维修记录编码列表")

    def validate_ids(self, value):
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
