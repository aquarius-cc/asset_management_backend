"""
待报废资产相关序列化器

包含 DamagedAsset 及其批量操作序列化器。

【AGENTS 规范 - 序列化器分层设计】
每个模块按 Action 分离序列化器:
- ListSerializer: 列表查询(扁平字段,只读,精简)
- CreateSerializer: 创建操作(写入字段)
- DetailSerializer: 详情查询(嵌套对象,只读,完整)
"""

from rest_framework import serializers

from apps.assetmanagement.models import DamagedAsset


# ==================== DamagedAsset 序列化器 ====================


class DamagedAssetCreateSerializer(serializers.ModelSerializer):
    """
    待报废资产创建序列化器
    用途:create action
    特点:写入字段
    """

    recordcode = serializers.CharField(read_only=True)
    damaged_asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    damaged_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    damaged_asset_contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    damaged_asset_storage_code = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    damaged_asset_storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    damaged_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = DamagedAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "damaged_asset_number",
            "damaged_date",
            "damaged_asset_description",
            "is_active",
            "damaged_asset_name",
            "damaged_asset_contract_code",
            "damaged_asset_contract_name",
            "damaged_asset_storage_code",
            "damaged_asset_storage_name",
            "damaged_asset_specification",
        ]


class DamagedAssetUpdateSerializer(serializers.ModelSerializer):
    """
    待报废资产更新序列化器
    用途:update, partial_update action
    特点:写入字段,recordcode 只读
    """

    recordcode = serializers.CharField(read_only=True)
    damaged_asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    damaged_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    damaged_asset_contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    damaged_asset_storage_code = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    damaged_asset_storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    damaged_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = DamagedAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "damaged_asset_number",
            "damaged_date",
            "damaged_asset_description",
            "is_active",
            "damaged_asset_name",
            "damaged_asset_contract_code",
            "damaged_asset_contract_name",
            "damaged_asset_storage_code",
            "damaged_asset_storage_name",
            "damaged_asset_specification",
        ]
        extra_kwargs = {
            "damaged_asset_number": {"required": False},
            "damaged_date": {"required": False},
        }


class DamagedAssetApproveSerializer(serializers.ModelSerializer):
    """
    待报废资产审批序列化器
    用途:approve, reject action
    特点:审批相关字段
    """

    recordcode = serializers.CharField(read_only=True)
    damaged_asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    damaged_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    damaged_asset_contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    damaged_asset_storage_code = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    damaged_asset_storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    damaged_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = DamagedAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "approval_status",
            "approver",
            "damaged_date",
            "damaged_asset_number",
            "damaged_asset_description",
            "is_active",
            "damaged_asset_name",
            "damaged_asset_contract_code",
            "damaged_asset_contract_name",
            "damaged_asset_storage_code",
            "damaged_asset_storage_name",
            "damaged_asset_specification",
        ]


class DamagedAssetListSerializer(serializers.ModelSerializer):
    """
    待报废资产列表序列化器
    用途:list action
    特点:精简字段,只读
    """

    damaged_asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    damaged_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    damaged_asset_contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    damaged_asset_storage_code = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    damaged_asset_storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    damaged_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = DamagedAsset
        fields = [
            "recordcode",
            "asset_recordcode",
            "approval_status",
            "approver",
            "damaged_date",
            "damaged_asset_number",
            "damaged_asset_description",
            "is_active",
            "damaged_asset_name",
            "damaged_asset_contract_code",
            "damaged_asset_contract_name",
            "damaged_asset_storage_code",
            "damaged_asset_storage_name",
            "damaged_asset_specification",
        ]
        read_only_fields = fields


class DamagedAssetDetailSerializer(serializers.ModelSerializer):
    """
    待报废资产详情序列化器
    用途:retrieve action
    特点:完整字段,只读
    """

    damaged_asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    damaged_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    damaged_asset_contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    damaged_asset_storage_code = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_code", read_only=True, allow_null=True
    )
    damaged_asset_storage_name = serializers.CharField(
        source="asset_recordcode.asset_storage_recordcode.storage_name", read_only=True, allow_null=True
    )
    damaged_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = DamagedAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "approval_status",
            "approver",
            "damaged_date",
            "damaged_asset_number",
            "damaged_asset_description",
            "is_active",
            "damaged_asset_name",
            "damaged_asset_contract_code",
            "damaged_asset_contract_name",
            "damaged_asset_storage_code",
            "damaged_asset_storage_name",
            "damaged_asset_specification",
            "version",
        ]


# ==================== 保持向后兼容 ====================
DamagedAssetSerializer = DamagedAssetListSerializer


# ========== 批量操作序列化器(DamagedAsset) ==========


# 【P1-10 修复】为 DamagedAsset 批量删除添加序列化器验证
class DamagedAssetBatchDeleteSerializer(serializers.Serializer):
    """待报废资产批量删除请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="待报废记录编码列表")

    def validate_ids(self, value):
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
