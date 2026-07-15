"""
资产生命周期管理 Mixin

提供资产状态流转相关的业务方法：标记损坏/遗失、找回、送修、维修完成/失败。
被 AssetService 继承以保持统一 API。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger

if TYPE_CHECKING:
    from apps.assetmanagement.models import RepairAsset
from apps.assetmanagement.models import Asset, BrokenAsset, FoundAsset, LostAsset
from apps.assetmanagement.state_machine import AssetFSM


class AssetLifecycleMixin:
    """资产生命周期状态流转方法"""

    @staticmethod
    @transaction.atomic
    def mark_asset_broken(
        asset_code: str,
        broken_reason: str,
        broken_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> Asset:
        """标记资产为已损坏"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        if asset.asset_current_status == "broken":
            return asset

        from apps.usermanagement.models import Employee
        operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()

        AssetFSM.mark_broken(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, BrokenAsset
        BrokenAsset.objects.create(
            asset_recordcode=asset,
            broken_reason=broken_reason,
            broken_description=broken_description,
            operator_employee=operator,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="broken",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"资产标记为已损坏: {broken_reason}",
        )
        return asset

    @staticmethod
    @transaction.atomic
    def mark_asset_lost(
        asset_code: str,
        lost_reason: str,
        last_known_location: str = "",
        lost_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> Asset:
        """标记资产为已遗失"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        if asset.asset_current_status == "lost":
            return asset

        from apps.usermanagement.models import Employee
        operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()

        AssetFSM.mark_lost(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, LostAsset
        LostAsset.objects.create(
            asset_recordcode=asset,
            last_known_location=last_known_location,
            lost_reason=lost_reason,
            lost_description=lost_description,
            operator_employee=operator,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="lost",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"资产标记为已遗失: {lost_reason}",
        )
        return asset

    @staticmethod
    @transaction.atomic
    def find_and_return_asset(
        asset_code: str,
        found_location: str = "",
        found_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> Asset:
        """找回遗失资产并入库"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        from apps.assetmanagement.models import LostAsset
        lost_record = LostAsset.objects.get(asset_recordcode=asset)

        from apps.usermanagement.models import Employee
        operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()

        AssetFSM.found_and_return(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, FoundAsset
        FoundAsset.objects.create(
            lost_asset_recordcode=lost_record,
            asset_recordcode=asset,
            found_location=found_location,
            found_description=found_description,
            operator_employee=operator,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="found",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="遗失资产找回并入库",
        )
        return asset

    @staticmethod
    @transaction.atomic
    def repair_asset(
        asset_code: str,
        repair_reason: str,
        repair_date: str,
        repair_description: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> "RepairAsset":
        """送修资产: broken -> repairing"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        from apps.usermanagement.models import Employee
        operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()

        AssetFSM.repair(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, RepairAsset
        repair_record = RepairAsset.objects.create(
            asset_recordcode=asset,
            repair_date=repair_date,
            repair_reason=repair_reason,
            repair_description=repair_description or None,
            operator_employee=operator,
            physical_grade_before=asset.physical_grade,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="repair",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description=f"Asset sent for repair: {repair_reason}",
        )
        return repair_record

    @staticmethod
    @transaction.atomic
    def repair_done(
        asset_code: str,
        actual_return_date: str = "",
        physical_grade_after: str = "",
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> "RepairAsset":
        """维修完成: repairing -> in_store"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        from apps.assetmanagement.models import RepairAsset
        repair_record = RepairAsset.objects.filter(
            asset_recordcode=asset, repair_status="in_progress"
        ).first()
        if not repair_record:
            from core.exceptions import AppValidationError
            raise AppValidationError("No in-progress repair record found for this asset")

        AssetFSM.repair_done(asset)
        if physical_grade_after:
            asset.physical_grade = physical_grade_after
        asset.save(update_fields=["asset_current_status", "physical_grade", "updated_at"])

        from django.utils import timezone
        repair_record.repair_status = "completed"
        repair_record.actual_return_date = actual_return_date or timezone.now().date()
        repair_record.physical_grade_after = physical_grade_after or None
        repair_record.save(update_fields=["repair_status", "actual_return_date", "physical_grade_after", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="repair_done",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="Repair completed, asset returned to store",
        )
        return repair_record

    @staticmethod
    @transaction.atomic
    def repair_failed(
        asset_code: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> "RepairAsset":
        """维修失败: repairing -> damaged"""
        asset = Asset.objects.select_for_update().get(asset_code=asset_code)

        from apps.assetmanagement.models import RepairAsset
        repair_record = RepairAsset.objects.filter(
            asset_recordcode=asset, repair_status="in_progress"
        ).first()
        if not repair_record:
            from core.exceptions import AppValidationError
            raise AppValidationError("No in-progress repair record found for this asset")

        AssetFSM.repair_failed(asset)
        asset.save(update_fields=["asset_current_status", "updated_at"])

        repair_record.repair_status = "failed"
        repair_record.save(update_fields=["repair_status", "updated_at"])

        from apps.assetmanagement.models import AssetOperationLog, DamagedAsset
        DamagedAsset.objects.create(
            asset_recordcode=asset,
            damaged_asset_number=1,
        )
        AssetOperationLog.objects.create(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_specification=asset.asset_specification,
            operation_type="repair_failed",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
            description="Repair failed, asset moved to pending scrap",
        )
        return repair_record

    @staticmethod
    @transaction.atomic
    def delete_broken_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict:
        """软删除损坏资产记录（事务包裹、逐条校验、审计日志）"""
        obj = BrokenAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,
            asset_name=obj.asset_recordcode.asset_name,
            asset_specification=obj.asset_recordcode.asset_specification,
            operation_type="delete",
            description=f"损坏资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    @transaction.atomic
    def delete_lost_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict:
        """软删除遗失资产记录（事务包裹、逐条校验、审计日志）"""
        obj = LostAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,
            asset_name=obj.asset_recordcode.asset_name,
            asset_specification=obj.asset_recordcode.asset_specification,
            operation_type="delete",
            description=f"遗失资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}

    @staticmethod
    @transaction.atomic
    def delete_found_asset(
        recordcode: str,
        operator_jobcode: str = "",
        operator_name: str = "",
    ) -> dict:
        """软删除找回资产记录（事务包裹、逐条校验、审计日志）"""
        obj = FoundAsset.objects.select_for_update().get(recordcode=recordcode, is_deleted=False)
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted", "updated_at"])

        AuditLogger.log_operation(
            asset_code=obj.asset_recordcode.asset_code,
            asset_name=obj.asset_recordcode.asset_name,
            asset_specification=obj.asset_recordcode.asset_specification,
            operation_type="delete",
            description=f"找回资产记录删除: {recordcode}",
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )
        return {"recordcode": recordcode, "status": "deleted"}
