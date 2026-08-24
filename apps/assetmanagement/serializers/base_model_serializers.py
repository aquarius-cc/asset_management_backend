"""
基础模型序列化器

包含 Storage, Contract, AssetType, HardDiskSN 等基础模型的序列化器。
"""

from typing import Any

from rest_framework import serializers

from apps.assetmanagement.models import (
    AssetType,
    Contract,
    HardDiskSN,
    Storage,
)


class StorageSerializer(serializers.ModelSerializer[Storage]):
    class Meta:
        model = Storage
        fields = [
            "recordcode",
            "storage_code",
            "storage_name",
            "storage_address",
            "storage_type",
            "storage_description",
            "is_active",
        ]


class AssetTypeSerializer(serializers.ModelSerializer[AssetType]):
    """
    资产类型序列化器

    输出字段:
    - parent: FK ID(recordcode)
    - parent_type_code: 业务编码(方便前端显示)
    - path: 物化路径
    """

    parent_type_code = serializers.CharField(
        source="parent.type_code", read_only=True, allow_null=True, help_text="父级类型编码"
    )

    class Meta:
        model = AssetType
        fields = [
            "recordcode",
            "type_code",
            "type_name",
            "parent",
            "parent_type_code",
            "path",
            "level",
            "type_description",
            "sort_order",
            "is_active",
        ]


# ==================== Contract 序列化器 ====================


class ContractListSerializer(serializers.ModelSerializer[Contract]):
    """
    合同列表序列化器
    用途:list action
    特点:精简字段,只读
    """

    class Meta:
        model = Contract
        fields = [
            "recordcode",
            "contract_code",
            "contract_name",
            "contract_type",
            "supplier_name",
            "contract_amount",
            "settlemented_price",
            "contract_total_quantity",
            "contract_start_date",
            "contract_end_date",
            "contract_status",
            "project_change",
            "amount_paid",
            "amount_unpaid",
            "is_active",
            "version",
        ]
        read_only_fields = fields


class ContractCreateSerializer(serializers.ModelSerializer[Contract]):
    """
    合同创建序列化器
    用途:create action
    特点:写入字段
    """

    recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = Contract
        fields = [
            "recordcode",
            "contract_code",
            "contract_name",
            "contract_type",
            "supplier_name",
            "contract_amount",
            "settlemented_price",
            "contract_total_quantity",
            "contract_start_date",
            "contract_end_date",
            "contract_status",
            "project_change",
            "project_change_type",
            "project_change_description",
            "receive_check_date",
            "initial_check_date",
            "final_check_date",
            "paid_record",
            "amount_paid",
            "amount_unpaid",
            "contract_description",
            "sort_order",
            "is_active",
        ]
        extra_kwargs = {
            "contract_code": {"required": True},
            "contract_name": {"required": True},
        }


class ContractDetailSerializer(serializers.ModelSerializer[Contract]):
    """
    合同详情序列化器
    用途:retrieve action
    特点:完整字段,只读
    """

    class Meta:
        model = Contract
        fields = [
            "recordcode",
            "contract_code",
            "contract_name",
            "contract_type",
            "supplier_name",
            "contract_amount",
            "settlemented_price",
            "contract_total_quantity",
            "contract_start_date",
            "contract_end_date",
            "contract_status",
            "project_change",
            "project_change_type",
            "project_change_description",
            "receive_check_date",
            "initial_check_date",
            "final_check_date",
            "paid_record",
            "amount_paid",
            "amount_unpaid",
            "contract_description",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
            "version",
        ]
        read_only_fields = fields


class ContractUpdateSerializer(serializers.ModelSerializer[Contract]):
    """
    合同更新序列化器
    用途:update, partial_update action
    特点:写入字段,recordcode 只读
    """

    recordcode = serializers.CharField(read_only=True)

    class Meta:
        model = Contract
        fields = [
            "recordcode",
            "contract_code",
            "contract_name",
            "contract_type",
            "supplier_name",
            "contract_amount",
            "settlemented_price",
            "contract_total_quantity",
            "contract_start_date",
            "contract_end_date",
            "contract_status",
            "project_change",
            "project_change_type",
            "project_change_description",
            "receive_check_date",
            "initial_check_date",
            "final_check_date",
            "paid_record",
            "amount_paid",
            "amount_unpaid",
            "contract_description",
            "sort_order",
            "is_active",
        ]
        extra_kwargs = {
            "contract_code": {"required": False},
            "contract_name": {"required": False},
        }


# ==================== 保持向后兼容 ====================
ContractSerializer = ContractCreateSerializer


class HardDiskSNSimpleSerializer(serializers.ModelSerializer[HardDiskSN]):
    """硬盘序列号精简序列化器(用于 Asset 详情嵌套)"""

    class Meta:
        model = HardDiskSN
        fields = [
            "recordcode",
            "harddisk_sn_code",
            "harddisk_type",
            "harddisk_capacity",
            "harddisk_status",
        ]


class HardDiskSNSerializer(serializers.ModelSerializer[HardDiskSN]):
    """硬盘序列号完整序列化器"""

    asset_code = serializers.CharField(source="asset_recordcode.asset_code", read_only=True)
    asset_name = serializers.CharField(source="asset_recordcode.asset_name", read_only=True)

    class Meta:
        model = HardDiskSN
        fields = [
            "recordcode",
            "asset_recordcode",
            "asset_code",
            "asset_name",
            "harddisk_sn_code",
            "harddisk_type",
            "harddisk_capacity",
            "harddisk_status",
            "harddisk_description",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["recordcode", "created_at", "updated_at"]


class HardDiskSNCreateSerializer(serializers.ModelSerializer[HardDiskSN]):
    """硬盘序列号创建序列化器"""

    class Meta:
        model = HardDiskSN
        fields = [
            "asset_recordcode",
            "harddisk_sn_code",
            "harddisk_type",
            "harddisk_capacity",
            "harddisk_status",
            "harddisk_description",
        ]
        extra_kwargs = {
            "asset_recordcode": {"required": True},
            "harddisk_sn_code": {"required": True},
        }


class DiskItemSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量操作单条硬盘"""

    recordcode = serializers.CharField(required=False, help_text="已有记录的 recordcode(更新时传入)")
    harddisk_sn_code = serializers.CharField(max_length=100)
    harddisk_type = serializers.ChoiceField(choices=HardDiskSN.HARDDISK_TYPE_CHOICES, required=False)
    harddisk_capacity = serializers.CharField(required=False, max_length=20)
    harddisk_status = serializers.ChoiceField(choices=HardDiskSN.HARDDISK_STATUS_CHOICES, required=False)
    harddisk_description = serializers.CharField(required=False, allow_blank=True)


class HardDiskSNBatchSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """批量保存硬盘序列号(资产入库时调用)"""

    asset_recordcode = serializers.CharField(required=True)
    disks = DiskItemSerializer(many=True)

    def validate(self, data: Any) -> None:
        disks = data.get("disks", [])
        if not disks:
            raise serializers.ValidationError("硬盘列表不能为空")
        sn_codes = [d["harddisk_sn_code"].strip() for d in disks]
        if len(sn_codes) != len(set(sn_codes)):
            raise serializers.ValidationError("硬盘序列号不能重复")
        return data  # type: ignore[no-any-return]


class CodeField(serializers.Field):  # type: ignore[type-arg]
    def __init__(self, code_key: str, **kwargs: Any) -> None:
        self.code_key = code_key
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, str):
            return {self.code_key: data}
        elif isinstance(data, dict) and self.code_key in data:
            return data
        raise serializers.ValidationError(f"请传入字符串或包含 {self.code_key} 的字典")

    def to_representation(self, value: Any) -> str | None:
        if hasattr(value, self.code_key):
            return getattr(value, self.code_key)  # type: ignore[no-any-return]
        elif isinstance(value, dict) and self.code_key in value:
            return value.get(self.code_key)
        return None


class ContractSimpleSerializer(serializers.Serializer):  # type: ignore[type-arg]
    contract_code = serializers.CharField(required=True)


class StorageSimpleSerializer(serializers.Serializer):  # type: ignore[type-arg]
    storage_code = serializers.CharField(required=True)


class AssettypeSimpleSerializer(serializers.Serializer):  # type: ignore[type-arg]
    type_code = serializers.CharField(required=True)
