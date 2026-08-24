"""
Asset Management Admin Configuration

Registers all asset-related models with Django Admin for backend management.
"""

from typing import Any

from django.contrib import admin

from apps.assetmanagement.models import (
    Asset,
    AssetOperationLog,
    AssetStateLog,
    AssetType,
    BrokenAsset,
    Contract,
    DamagedAsset,
    FoundAsset,
    HardDiskSN,
    LostAsset,
    OutAsset,
    RecycleAsset,
    RepairAsset,
    Storage,
    WasteAsset,
)


# ======================================================================
# Storage
# ======================================================================
@admin.register(Storage)
class StorageAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["recordcode", "storage_name", "storage_location", "storage_manager", "storage_capacity"]
    search_fields = ["storage_name", "storage_location"]
    list_filter = ["created_at"]
    readonly_fields = ["recordcode", "created_at", "updated_at"]


# ======================================================================
# AssetType
# ======================================================================
@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["recordcode", "type_code", "type_name", "get_parent_code", "level", "path"]
    search_fields = ["type_code", "type_name"]
    list_filter = ["level"]
    readonly_fields = ["recordcode", "created_at", "updated_at"]

    def get_parent_code(self, obj: Any) -> str:
        """显示父类型的业务编码"""
        if obj.parent:
            return str(obj.parent.type_code)
        return "—"

    get_parent_code.short_description = "父级类型"  # type: ignore[attr-defined]


# ======================================================================
# Contract
# ======================================================================
@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "recordcode",
        "contract_code",
        "contract_name",
        "supplier_name",
        "contract_amount",
        "contract_status",
        "created_at",
    ]
    search_fields = ["contract_code", "contract_name", "supplier_name"]
    list_filter = ["contract_status", "created_at"]
    readonly_fields = ["recordcode", "created_at", "updated_at"]


# ======================================================================
# Asset
# ======================================================================
@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "recordcode",
        "asset_code",
        "asset_name",
        "asset_brand",
        "asset_current_status",
        "physical_grade",
        "created_at",
    ]
    search_fields = ["asset_code", "asset_name", "asset_brand"]
    list_filter = ["asset_current_status", "physical_grade", "usage_type"]
    readonly_fields = ["recordcode", "asset_code", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "recordcode",
                    "asset_code",
                    "asset_name",
                    "asset_brand",
                    "asset_specification",
                    "asset_price",
                ),
            },
        ),
        (
            "Status",
            {
                "fields": ("asset_current_status", "physical_grade", "usage_type"),
            },
        ),
        (
            "Relations",
            {
                "fields": ("asset_type_recordcode", "asset_contract_recordcode", "asset_storage_recordcode"),
            },
        ),
        (
            "People",
            {
                "fields": ("asset_applicant_recordcode", "asset_manager_recordcode", "asset_entry_person_recordcode"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )


# ======================================================================
# OutAsset
# ======================================================================
@admin.register(OutAsset)
class OutAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = ["recordcode", "asset_code_display", "outasset_type", "outasset_date", "outasset_number"]
    search_fields = ["asset_recordcode__asset_code", "asset_recordcode__asset_name"]
    list_filter = ["outasset_type", "outasset_date"]
    readonly_fields = ["recordcode", "asset_recordcode", "created_at", "updated_at"]


# ======================================================================
# RecycleAsset
# ======================================================================
@admin.register(RecycleAsset)
class RecycleAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = ["recordcode", "asset_code_display", "recycle_asset_date", "recycle_asset_number"]
    search_fields = ["asset_recordcode__asset_code", "asset_recordcode__asset_name"]
    list_filter = ["recycle_asset_date"]
    readonly_fields = ["recordcode", "asset_recordcode", "created_at", "updated_at"]


# ======================================================================
# BrokenAsset
# ======================================================================
@admin.register(BrokenAsset)
class BrokenAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    def asset_name(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"  # type: ignore[attr-defined]

    def operator_name(self, obj: Any) -> str:
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"  # type: ignore[attr-defined]

    list_display = ["recordcode", "asset_code_display", "asset_name", "broken_date", "operator_name", "broken_reason"]
    search_fields = ["asset_recordcode__asset_name", "broken_reason"]
    list_filter = ["broken_date"]
    date_hierarchy = "broken_date"
    readonly_fields = ["recordcode", "asset_recordcode", "operator_employee", "created_at", "updated_at"]


# ======================================================================
# LostAsset
# ======================================================================
@admin.register(LostAsset)
class LostAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    def asset_name(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"  # type: ignore[attr-defined]

    def operator_name(self, obj: Any) -> str:
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"  # type: ignore[attr-defined]

    list_display = [
        "recordcode",
        "asset_code_display",
        "asset_name",
        "lost_date",
        "operator_name",
        "lost_reason",
        "last_known_location",
    ]
    search_fields = ["asset_recordcode__asset_name", "lost_reason"]
    list_filter = ["lost_date"]
    date_hierarchy = "lost_date"
    readonly_fields = ["recordcode", "asset_recordcode", "operator_employee", "created_at", "updated_at"]


# ======================================================================
# FoundAsset
# ======================================================================
@admin.register(FoundAsset)
class FoundAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    def asset_name(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"  # type: ignore[attr-defined]

    def lost_asset_code_display(self, obj: Any) -> str:
        return obj.lost_asset_recordcode.recordcode if obj.lost_asset_recordcode else "-"

    lost_asset_code_display.short_description = "Lost Record"  # type: ignore[attr-defined]

    def operator_name(self, obj: Any) -> str:
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"  # type: ignore[attr-defined]

    list_display = [
        "recordcode",
        "lost_asset_code_display",
        "asset_code_display",
        "asset_name",
        "found_date",
        "found_location",
        "operator_name",
    ]
    search_fields = ["asset_recordcode__asset_name"]
    list_filter = ["found_date"]
    date_hierarchy = "found_date"
    readonly_fields = [
        "recordcode",
        "lost_asset_recordcode",
        "asset_recordcode",
        "operator_employee",
        "created_at",
        "updated_at",
    ]


# ======================================================================
# RepairAsset
# ======================================================================
@admin.register(RepairAsset)
class RepairAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    def asset_name(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"  # type: ignore[attr-defined]

    def operator_name(self, obj: Any) -> str:
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"  # type: ignore[attr-defined]

    list_display = [
        "recordcode",
        "asset_code_display",
        "asset_name",
        "repair_date",
        "repair_status",
        "repair_reason",
        "operator_name",
    ]
    search_fields = ["asset_recordcode__asset_name", "repair_reason"]
    list_filter = ["repair_status", "repair_date"]
    date_hierarchy = "repair_date"
    readonly_fields = ["recordcode", "asset_recordcode", "operator_employee", "created_at", "updated_at"]


# ======================================================================
# DamagedAsset
# ======================================================================
@admin.register(DamagedAsset)
class DamagedAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = [
        "recordcode",
        "asset_code_display",
        "damaged_asset_number",
        "damaged_date",
        "approval_status",
        "approver",
    ]
    search_fields = ["asset_recordcode__asset_code"]
    list_filter = ["approval_status", "damaged_date"]
    readonly_fields = ["recordcode", "asset_recordcode", "created_at", "updated_at"]


# ======================================================================
# WasteAsset
# ======================================================================
@admin.register(WasteAsset)
class WasteAssetAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = ["recordcode", "asset_code_display", "waste_asset_number", "waste_asset_date"]
    search_fields = ["asset_recordcode__asset_code"]
    list_filter = ["waste_asset_date"]
    readonly_fields = ["recordcode", "asset_recordcode", "damaged_recordcode", "created_at", "updated_at"]


# ======================================================================
# HardDiskSN
# ======================================================================
@admin.register(HardDiskSN)
class HardDiskSNAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = [
        "recordcode",
        "asset_code_display",
        "harddisk_sn_code",
        "harddisk_type",
        "harddisk_capacity",
        "harddisk_status",
    ]
    search_fields = ["harddisk_sn_code", "harddisk_type"]
    list_filter = ["harddisk_type", "harddisk_status"]
    readonly_fields = ["recordcode", "asset_recordcode", "created_at", "updated_at"]


# ======================================================================
# Operation Logs (Read-only)
# ======================================================================
@admin.register(AssetOperationLog)
class AssetOperationLogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["asset_code", "asset_name", "operation_type", "operator_name", "operation_time"]
    search_fields = ["asset_code", "asset_name", "operator_name"]
    list_filter = ["operation_type", "operation_time"]
    date_hierarchy = "operation_time"
    readonly_fields = [f.name for f in AssetOperationLog._meta.get_fields()]


@admin.register(AssetStateLog)
class AssetStateLogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    def asset_code_display(self, obj: Any) -> str:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"  # type: ignore[attr-defined]

    list_display = ["asset_code_display", "from_state", "to_state", "business_doc_no", "created_at"]
    search_fields = ["asset_recordcode__asset_code"]
    list_filter = ["from_state", "to_state", "created_at"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AssetStateLog._meta.get_fields()]
