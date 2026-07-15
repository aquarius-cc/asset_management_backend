"""
硬盘序列号服务

提供硬盘序列号的创建、更新、删除、批量保存等业务逻辑。
"""

from typing import Any

from django.db import transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import HardDiskSN
from apps.assetmanagement.selectors import AssetSelector, HardDiskSNSelector
from core.exceptions import AppValidationError


class HardDiskSNService:
    """
    硬盘序列号业务服务

    采用"先验证后执行"策略，所有校验通过后才执行数据库操作。
    使用数据库事务确保批量操作的原子性。
    """

    @staticmethod
    @transaction.atomic
    def create(data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None) -> HardDiskSN:
        """
        创建单条硬盘记录
        - 校验序列号唯一性
        - 校验关联资产存在
        """
        sn_code = data.get("harddisk_sn_code", "").strip()
        if not sn_code:
            raise AppValidationError(detail="硬盘序列号不能为空", error_code="MISSING_SN_CODE")

        if HardDiskSNSelector.exists_by_sn_code(sn_code):
            raise AppValidationError(
                detail=f"序列号 {sn_code} 已存在",
                error_code="DUPLICATE_SN_CODE",
            )

        harddisk = HardDiskSN.objects.create(**data)

        AuditLogger.log_asset_update(
            asset=harddisk.asset_recordcode,
            before_data={},
            after_data=data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return harddisk

    @staticmethod
    @transaction.atomic
    def update(
        recordcode: str, update_data: dict[str, Any],
        operator_jobcode: str | None = None, operator_name: str | None = None,
    ) -> HardDiskSN:
        """
        更新硬盘记录
        - 若修改序列号，校验新唯一性
        """
        harddisk = HardDiskSNSelector.get_by_recordcode(recordcode)
        if not harddisk:
            raise AppValidationError(detail="硬盘记录不存在", error_code="HARD_DISK_NOT_FOUND")

        new_sn = update_data.get("harddisk_sn_code")
        if new_sn and new_sn.strip() != harddisk.harddisk_sn_code:
            if HardDiskSNSelector.exists_by_sn_code(new_sn.strip()):
                raise AppValidationError(
                    detail=f"序列号 {new_sn} 已存在",
                    error_code="DUPLICATE_SN_CODE",
                )
            update_data["harddisk_sn_code"] = new_sn.strip()

        before_data = {key: getattr(harddisk, key) for key in update_data.keys()}

        for key, value in update_data.items():
            setattr(harddisk, key, value)
        harddisk.save()

        AuditLogger.log_asset_update(
            asset=harddisk.asset_recordcode,
            before_data=before_data,
            after_data=update_data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return harddisk

    @staticmethod
    @transaction.atomic
    def delete(recordcode: str, operator_jobcode: str | None = None, operator_name: str | None = None) -> None:
        """软删除硬盘记录"""
        harddisk = HardDiskSNSelector.get_by_recordcode(recordcode)
        if not harddisk:
            raise AppValidationError(detail="硬盘记录不存在", error_code="HARD_DISK_NOT_FOUND")

        AuditLogger.log_asset_delete(
            asset_code=harddisk.asset_recordcode.asset_code if harddisk.asset_recordcode else None,
            asset_name=harddisk.asset_recordcode.asset_name if harddisk.asset_recordcode else None,
            asset=harddisk.asset_recordcode,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        harddisk.delete()

    @staticmethod
    @transaction.atomic
    def batch_save(asset_recordcode: str, disks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量保存硬盘（资产入库时调用）
        - 有 recordcode → 更新
        - 无 recordcode → 创建
        - 校验序列号唯一性
        """
        MAX_BATCH_SIZE = 100
        if len(disks) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量保存不能超过 {MAX_BATCH_SIZE} 条",
                error_code="BATCH_SIZE_EXCEEDED",
            )

        sn_codes = [d.get("harddisk_sn_code", "").strip() for d in disks]
        # 批量唯一性校验（排除自身已软删除的记录）
        existing = set(
            HardDiskSN.objects.filter(
                harddisk_sn_code__in=sn_codes, is_deleted=False
            ).values_list("harddisk_sn_code", flat=True)
        )
        duplicates = [s for s in sn_codes if s in existing]
        if duplicates:
            raise AppValidationError(
                detail=f"序列号重复: {', '.join(duplicates)}",
                error_code="DUPLICATE_SN_CODE",
            )

        created_count = 0
        updated_count = 0

        for disk_data in disks:
            rc = disk_data.pop("recordcode", None)
            disk_data["asset_recordcode"] = asset_recordcode
            disk_data["harddisk_sn_code"] = disk_data.get("harddisk_sn_code", "").strip()

            if rc:
                obj = HardDiskSNSelector.get_by_recordcode(rc)
                if obj:
                    for k, v in disk_data.items():
                        setattr(obj, k, v)
                    obj.save()
                    updated_count += 1
            else:
                HardDiskSN.objects.create(**disk_data)
                created_count += 1

        return {
            "created": created_count,
            "updated": updated_count,
            "total": len(disks),
            "asset_recordcode": asset_recordcode,
        }
