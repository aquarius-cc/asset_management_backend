"""
生命周期序列化器

包含 BrokenAsset, LostAsset, FoundAsset 等生命周期记录的序列化器。
"""

from rest_framework import serializers

from apps.assetmanagement.models import (
    Asset,
    BrokenAsset,
    FoundAsset,
    LostAsset,
)


# ==================== BrokenAsset 序列化器 ====================


class BrokenAssetListSerializer(serializers.ModelSerializer[BrokenAsset]):
    """损坏记录列表序列化器 - list action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)

    class Meta:
        model = BrokenAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "broken_date",
            "operator_name",
            "broken_reason",
            "created_at",
        ]
        read_only_fields = fields


class BrokenAssetCreateSerializer(serializers.ModelSerializer[BrokenAsset]):
    """损坏记录创建序列化器 - create action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )

    class Meta:
        model = BrokenAsset
        fields = ["recordcode", "asset_recordcode", "broken_date", "broken_reason", "broken_description"]
        extra_kwargs = {"broken_reason": {"required": True}, "broken_date": {"required": False}}


class BrokenAssetUpdateSerializer(serializers.ModelSerializer[BrokenAsset]):
    """损坏记录更新序列化器 - update/partial_update action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = BrokenAsset
        fields = ["recordcode", "asset_recordcode", "broken_date", "broken_reason", "broken_description"]
        extra_kwargs = {"broken_reason": {"required": False}}


class BrokenAssetDetailSerializer(serializers.ModelSerializer[BrokenAsset]):
    """损坏记录详情序列化器 - retrieve action"""

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
        model = BrokenAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "broken_date",
            "operator_employee",
            "operator_name",
            "operator_jobcode",
            "broken_reason",
            "broken_description",
            "version",
            "created_at",
            "updated_at",
        ]


BrokenAssetSerializer = BrokenAssetListSerializer  # 向后兼容


# ==================== LostAsset 序列化器 ====================


class LostAssetListSerializer(serializers.ModelSerializer[LostAsset]):
    """遗失记录列表序列化器 - list action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)

    class Meta:
        model = LostAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "lost_date",
            "operator_name",
            "lost_reason",
            "last_known_location",
            "created_at",
        ]
        read_only_fields = fields


class LostAssetCreateSerializer(serializers.ModelSerializer[LostAsset]):
    """遗失记录创建序列化器 - create action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )

    class Meta:
        model = LostAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "lost_date",
            "last_known_location",
            "lost_reason",
            "lost_description",
        ]
        extra_kwargs = {"lost_reason": {"required": True}, "lost_date": {"required": False}}


class LostAssetUpdateSerializer(serializers.ModelSerializer[LostAsset]):
    """遗失记录更新序列化器 - update/partial_update action"""

    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = LostAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "lost_date",
            "last_known_location",
            "lost_reason",
            "lost_description",
        ]
        extra_kwargs = {"lost_reason": {"required": False}}


class LostAssetDetailSerializer(serializers.ModelSerializer[LostAsset]):
    """遗失记录详情序列化器 - retrieve action"""

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
        model = LostAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "lost_date",
            "operator_employee",
            "operator_name",
            "operator_jobcode",
            "last_known_location",
            "lost_reason",
            "lost_description",
            "version",
            "created_at",
            "updated_at",
        ]


LostAssetSerializer = LostAssetListSerializer  # 向后兼容


# ==================== FoundAsset 序列化器 ====================


class FoundAssetListSerializer(serializers.ModelSerializer[FoundAsset]):
    """找回记录列表序列化器 - list action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)
    lost_asset_code = serializers.CharField(source="lost_asset_recordcode.recordcode", read_only=True)

    class Meta:
        model = FoundAsset
        fields = [
            "recordcode",
            "lost_asset_recordcode",
            "lost_asset_code",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "found_date",
            "found_location",
            "operator_name",
            "created_at",
        ]
        read_only_fields = fields


class FoundAssetCreateSerializer(serializers.ModelSerializer[FoundAsset]):
    """找回记录创建序列化器 - create action"""

    recordcode = serializers.CharField(read_only=True)
    lost_asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=LostAsset.objects.filter(is_deleted=False), write_only=True
    )
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )

    class Meta:
        model = FoundAsset
        fields = [
            "recordcode",
            "lost_asset_recordcode",
            "asset_recordcode",
            "found_date",
            "found_location",
            "found_description",
        ]
        extra_kwargs = {"found_date": {"required": False}}


class FoundAssetUpdateSerializer(serializers.ModelSerializer[FoundAsset]):
    """找回记录更新序列化器 - update/partial_update action"""

    recordcode = serializers.CharField(read_only=True)
    lost_asset_recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = FoundAsset
        fields = [
            "recordcode",
            "lost_asset_recordcode",
            "asset_recordcode",
            "found_date",
            "found_location",
            "found_description",
        ]


class FoundAssetDetailSerializer(serializers.ModelSerializer[FoundAsset]):
    """找回记录详情序列化器 - retrieve action"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    asset_specification = serializers.CharField(
        source="asset_recordcode.asset_specification", read_only=True, allow_null=True
    )
    operator_name = serializers.CharField(source="operator_employee.employee_name", read_only=True, allow_null=True)
    operator_jobcode = serializers.CharField(
        source="operator_employee.employee_jobcode", read_only=True, allow_null=True
    )
    lost_asset_code = serializers.CharField(source="lost_asset_recordcode.recordcode", read_only=True)

    class Meta:
        model = FoundAsset
        fields = [
            "recordcode",
            "lost_asset_recordcode",
            "lost_asset_code",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "asset_specification",
            "found_date",
            "found_location",
            "operator_employee",
            "operator_name",
            "operator_jobcode",
            "found_description",
            "version",
            "created_at",
            "updated_at",
        ]


FoundAssetSerializer = FoundAssetListSerializer  # 向后兼容
