"""
已报废资产相关序列化器

包含 WasteAsset 及其批量操作序列化器。

【AGENTS 规范 - 序列化器分层设计】
每个模块按 Action 分离序列化器：
- ListSerializer: 列表查询（扁平字段，只读，精简）
- CreateSerializer: 创建操作（写入字段）
- DetailSerializer: 详情查询（嵌套对象，只读，完整）
"""

from rest_framework import serializers

from apps.assetmanagement.models import WasteAsset


# ==================== WasteAsset 序列化器 ====================


class WasteAssetCreateSerializer(serializers.ModelSerializer):
    """
    已报废资产创建序列化器
    用途：create action（通常由审批流程自动创建）
    特点：写入字段
    """

    recordcode = serializers.CharField(read_only=True)
    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    waste_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )
    waste_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)

    class Meta:
        model = WasteAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "damaged_recordcode",
            "waste_asset_number",
            "waste_asset_date",
            "waste_asset_description",
            "is_active",
            "asset_code",
            "asset_name",
            "waste_asset_contract_code",
            "waste_asset_specification",
        ]


class WasteAssetListSerializer(serializers.ModelSerializer):
    """
    已报废资产列表序列化器
    用途：list action
    特点：精简字段，只读
    """

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    waste_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)
    waste_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )

    class Meta:
        model = WasteAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "waste_asset_contract_code",
            "waste_asset_date",
            "waste_asset_description",
            "asset_code",
            "asset_name",
            "contract_name",
            "waste_asset_specification",
            "is_active",
        ]
        read_only_fields = fields


class WasteAssetDetailSerializer(serializers.ModelSerializer):
    """
    已报废资产详情序列化器
    用途：retrieve action
    特点：完整字段，只读
    """

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)
    contract_name = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_name", read_only=True, allow_null=True
    )
    waste_asset_specification = serializers.CharField(source="asset_recordcode.asset_specification", read_only=True)
    waste_asset_contract_code = serializers.CharField(
        source="asset_recordcode.asset_contract_recordcode.contract_code", read_only=True, allow_null=True
    )

    class Meta:
        model = WasteAsset
        fields = [
            "id",
            "recordcode",
            "asset_recordcode",
            "damaged_recordcode",
            "waste_asset_number",
            "waste_asset_date",
            "waste_asset_description",
            "is_active",
            "asset_code",
            "asset_name",
            "contract_name",
            "waste_asset_contract_code",
            "waste_asset_specification",
            "version",
        ]


# ==================== 保持向后兼容 ====================
WasteAssetSerializer = WasteAssetListSerializer


# ========== 批量操作序列化器（WasteAsset） ==========


class WasteAssetBatchDeleteSerializer(serializers.Serializer):
    """已报废资产批量删除请求校验"""

    MAX_BATCH_SIZE = 100
    ids = serializers.ListField(child=serializers.CharField(), required=True, help_text="已报废记录编码列表")

    def validate_ids(self, value):
        if len(value) > self.MAX_BATCH_SIZE:
            raise serializers.ValidationError(f"单次批量删除不能超过 {self.MAX_BATCH_SIZE} 条")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("ids 列表中存在重复项")
        return value
