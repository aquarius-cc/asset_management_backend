"""
LostAsset Admin 配置
"""

from django.contrib import admin

from apps.assetmanagement.models import LostAsset


@admin.register(LostAsset)
class LostAssetAdmin(admin.ModelAdmin):
    def asset_code_display(self, obj):
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else "-"

    asset_code_display.short_description = "资产编码"

    def asset_name(self, obj):
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else "-"

    asset_name.short_description = "资产名称"

    def operator_name(self, obj):
        return obj.operator_employee.employee_name if obj.operator_employee else "-"

    operator_name.short_description = "操作人"

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
    readonly_fields = ["recordcode", "asset_recordcode", "operator_employee"]
