"""
资产管理 Admin 配置（已修复所有字段引用错误）
"""

from django.contrib import admin
from .models import (
    Storage,
    AssetType,
    Contract,
    Asset,
    OutAsset,
    RecycleAsset,
    DamagedAsset,
    WasteAsset,
    HardDiskSN
)


@admin.register(Storage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ['storage_code', 'storage_name',
                    'storage_type', 'storage_address']
    search_fields = ['storage_name', 'storage_code']
    list_filter = ['storage_type']


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    def asset_type_name(self, obj):
        return f"{obj.asset_type_primary} - {obj.asset_type_secondary}"
    asset_type_name.short_description = "资产分类名称"
    asset_type_name.admin_order_field = 'asset_type_primary'

    list_display = ['asset_type_code',
                    'asset_type_name', 'asset_type_category']
    search_fields = ['asset_type_primary',
                     'asset_type_secondary', 'asset_type_code']
    list_filter = ['asset_type_category']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = [
        'contract_code',
        'contract_name',
        'contract_type',
        'contract_price',
        'contract_settlment_status'
    ]
    search_fields = ['contract_name', 'contract_code', 'contract_supplier']
    list_filter = ['contract_type', 'contract_settlment_status']
    date_hierarchy = 'contract_signing_date'


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = [
        'asset_code',
        'asset_name',
        'asset_current_status',          # 【架构优化】移除 asset_appearance，统一用 asset_current_status
        # 'sort_order',                    # 【架构优化】新增排序字段
        'asset_purchase_price',
        'asset_entry_date'
    ]
    search_fields = ['asset_name', 'asset_code', 'asset_brand']
    list_filter = ['asset_current_status',
                   'asset_type_code', 'asset_storage_code']
    date_hierarchy = 'asset_entry_date'


@admin.register(OutAsset)
class OutAssetAdmin(admin.ModelAdmin):
    def outasset_applicant_name(self, obj):
        # 【AGENTS 规范 - 修复】user_name → employee_name
        if obj.outasset_applicant_jobcode:
            return obj.outasset_applicant_jobcode.employee_name
        return '-'
    outasset_applicant_name.short_description = '申请人'

    def outasset_manager_name(self, obj):
        # 【AGENTS 规范 - 修复】user_name → employee_name
        if obj.outasset_manager_jobcode:
            return obj.outasset_manager_jobcode.employee_name
        return '-'
    outasset_manager_name.short_description = '保管人'

    list_display = [
        'id',
        'outasset_code',
        'outasset_type',
        'outasset_recordcode',           # ← 已加逗号
        'outasset_date',
        'outasset_applicant_name',       # 显示姓名而非工号（可选）
        'outasset_manager_name'
        # 或直接用：'outasset_applicant_jobcode', 'outasset_manager_jobcode'
    ]
    search_fields = ['outasset_code__asset_name']
    list_filter = ['outasset_type']
    date_hierarchy = 'outasset_date'


@admin.register(RecycleAsset)
class RecycleAssetAdmin(admin.ModelAdmin):
    def asset_code(self, obj):
        if obj.outasset_recordcode and obj.outasset_recordcode.outasset_code:
            return obj.outasset_recordcode.outasset_code.asset_code
        return '-'
    asset_code.short_description = '资产编码'

    def asset_name(self, obj):
        if obj.outasset_recordcode and obj.outasset_recordcode.outasset_code:
            return obj.outasset_recordcode.outasset_code.asset_name
        return '-'
    asset_name.short_description = '资产名称'

    def recycle_person_name(self, obj):
        # 【AGENTS 规范 - 去除冗余】recycle_asset_recycle_person_jobcode 删除
        # 回收人通过 operator_jobcode 获取
        # 【AGENTS 规范 - 修复】user_name → employee_name
        if obj.operator_jobcode:
            return obj.operator_jobcode.employee_name
        return '-'
    recycle_person_name.short_description = '回收人'

    def storage_name(self, obj):
        # 【AGENTS 规范 - 去除冗余】recycle_asset_storage_code 删除
        # 仓库通过 recycle_asset_code.asset_storage_code 关联查询
        if obj.recycle_asset_code and obj.recycle_asset_code.asset_storage_code:
            return obj.recycle_asset_code.asset_storage_code.storage_name
        return '-'
    storage_name.short_description = '存储仓库'

    list_display = [
        'recycle_record_code',
        'asset_code',
        'asset_name',
        'outasset_recordcode',
        'recycle_asset_date',
        'storage_name',  # 【修改】通过关联查询获取
        'recycle_person_name'
    ]

    search_fields = [
        'recycle_record_code',
        'outasset_recordcode__outasset_code__asset_code',
        'outasset_recordcode__outasset_code__asset_name',
        # 【AGENTS 规范 - 修复】operator_jobcode__user_name → operator_jobcode__employee_name
        'operator_jobcode__employee_name'
    ]
    # 【AGENTS 规范 - 去除冗余】recycle_asset_storage_code list_filter 删除
    # 如需按仓库筛选，需自定义 FilterSet 通过 recycle_asset_code__asset_storage_code 实现
    list_filter = []
    readonly_fields = ['outasset_recordcode', 'recycle_record_code']
    date_hierarchy = 'recycle_asset_date'


@admin.register(DamagedAsset)
class DamagedAssetAdmin(admin.ModelAdmin):
    def damaged_storage_name(self, obj):
        # 【AGENTS 规范 - 去除冗余】damaged_asset_storage_code 删除
        # 仓库通过 damaged_asset_code.asset_storage_code 关联查询
        if obj.damaged_asset_code and obj.damaged_asset_code.asset_storage_code:
            return obj.damaged_asset_code.asset_storage_code.storage_name
        return '-'
    damaged_storage_name.short_description = '存储仓库'

    list_display = ['damaged_asset_code',
                    'damaged_storage_name', 'approval_status']
    search_fields = ['damaged_asset_code__asset_name']


@admin.register(WasteAsset)
class WasteAssetAdmin(admin.ModelAdmin):
    list_display = ['waste_asset_code', 'waste_asset_date']
    date_hierarchy = 'waste_asset_date'


@admin.register(HardDiskSN)
class HardDiskSNAdmin(admin.ModelAdmin):
    def asset_name(self, obj):
        return obj.asset_code.asset_name if obj.asset_code else '-'
    asset_name.short_description = '所属资产'

    def asset_manager_name(self, obj):
        # 【AGENTS 规范 - 修复】user_name → employee_name
        if obj.asset_code and obj.asset_code.asset_manager_jobcode:
            return obj.asset_code.asset_manager_jobcode.employee_name
        return '-'
    asset_manager_name.short_description = '资产保管人'

    def harddisk_sn_status_display(self, obj):
        return obj.get_harddisk_status_display()
    harddisk_sn_status_display.short_description = '硬盘状态'

    list_display = [
        'id',
        'harddisk_sn_code',
        'asset_name',
        'harddisk_number',
        'harddisk_type',
        'asset_manager_name',
        'harddisk_sn_status_display'     # ← 使用正确字段 harddisk_status
    ]
    search_fields = [
        'harddisk_sn_code',
        'asset_code__asset_name',
        # 【AGENTS 规范 - 修复】user_name → employee_name
        'asset_code__asset_manager_jobcode__employee_name'
    ]
    list_filter = ['harddisk_status']    # ← 正确字段名
