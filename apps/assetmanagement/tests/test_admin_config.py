"""Django Admin 状态字段只读断言(AUD-03)

后台表单若可直接编辑 asset_current_status / contract_status,
将绕过 AssetFSM/ContractFSM 与三类审计日志(AssetStateLog/AssetOperationLog/GenericAudit),
产出 FSM 无法复现的数据组合,故状态字段必须列入 readonly_fields。
"""

from django.contrib import admin

from apps.assetmanagement.admin.asset_admin import AssetAdmin, ContractAdmin
from apps.assetmanagement.models import Asset, Contract


class TestAdminStatusReadonly:
    """状态字段必须 readonly(状态变更所有权归 FSM)"""

    def test_asset_current_status_is_readonly_in_admin(self):
        """AssetAdmin 变更表单不得暴露可编辑的 asset_current_status"""
        model_admin = AssetAdmin(Asset, admin.site)
        assert "asset_current_status" in model_admin.get_readonly_fields(None)

    def test_contract_status_is_readonly_in_admin(self):
        """ContractAdmin 变更表单不得暴露可编辑的 contract_status"""
        model_admin = ContractAdmin(Contract, admin.site)
        assert "contract_status" in model_admin.get_readonly_fields(None)
