"""
FoundAsset Admin 配置
"""

from typing import Any

from django.contrib import admin

from apps.assetmanagement.models import FoundAsset


@admin.register(FoundAsset)
class FoundAssetAdmin(admin.ModelAdmin):
    def asset_code_display(self, obj: Any) -> None:
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"

    def asset_name(self, obj: Any) -> None:
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"

    def lost_asset_code_display(self, obj: Any) -> None:
        return obj.lost_asset_recordcode.recordcode if obj.lost_asset_recordcode else "-"

    lost_asset_code_display.short_description = "关联遗失记录"

    def operator_name(self, obj: Any) -> None:
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"

    list_display = [
        "recordcode",
        "asset_code_display",
        "asset_name",
        "lost_asset_code_display",
        "found_date",
        "operator_name",
    ]
    search_fields = ["asset_recordcode__asset_name"]
    list_filter = ["found_date"]
    date_hierarchy = "found_date"
    readonly_fields = ["recordcode", "lost_asset_recordcode", "asset_recordcode", "operator_employee"]
