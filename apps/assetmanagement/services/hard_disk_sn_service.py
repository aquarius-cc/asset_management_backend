"""
硬盘序列号服务

提供硬盘序列号的创建、更新、删除、批量保存等业务逻辑。
"""

from typing import Any

from django.db import IntegrityError, transaction

from apps.assetmanagement.audit import AuditLogger
from apps.assetmanagement.models import Asset, HardDiskSN
from apps.assetmanagement.selectors import AssetSelector, HardDiskSNSelector
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError


class HardDiskSNService:
    """
    硬盘序列号业务服务

    采用"先验证后执行"策略,所有校验通过后才执行数据库操作。
    使用数据库事务确保批量操作的原子性。
    """

    @staticmethod
    @transaction.atomic
    def create(
        data: dict[str, Any], operator_jobcode: str | None = None, operator_name: str | None = None
    ) -> HardDiskSN:
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

        try:
            with transaction.atomic():
                harddisk = HardDiskSN.objects.create(**data)
        except IntegrityError as exc:
            if "harddisk_sn_code" in str(exc):
                raise AppValidationError(
                    detail=f"序列号 {sn_code} 已存在",
                    error_code="DUPLICATE_SN_CODE",
                ) from exc
            raise

        AuditLogger.log_asset_update(
            asset=harddisk.asset_recordcode,
            before_data={},
            after_data=data,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        return harddisk  # type: ignore[no-any-return]

    @staticmethod
    @transaction.atomic
    def update(
        recordcode: str,
        update_data: dict[str, Any],
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> HardDiskSN:
        """
        更新硬盘记录
        - 若修改序列号,校验新唯一性
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
        try:
            with transaction.atomic():
                harddisk.save()
        except IntegrityError as exc:
            if "harddisk_sn_code" in str(exc):
                raise AppValidationError(
                    detail=f"序列号 {new_sn or harddisk.harddisk_sn_code} 已存在",
                    error_code="DUPLICATE_SN_CODE",
                ) from exc
            raise

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
            asset_code=harddisk.asset_recordcode.asset_code if harddisk.asset_recordcode else None,  # type: ignore[arg-type]
            asset_name=harddisk.asset_recordcode.asset_name if harddisk.asset_recordcode else None,  # type: ignore[arg-type]
            asset=harddisk.asset_recordcode,
            operator_jobcode=operator_jobcode,
            operator_name=operator_name,
        )

        harddisk.delete()

    @staticmethod
    @transaction.atomic
    def batch_save(asset_recordcode: str, disks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量保存硬盘(资产入库时调用)
        - 有 recordcode → 更新(仅应用显式提供的字段,禁止跨资产改挂)
        - 无 recordcode → 创建(序列号必填)
        - 校验资产存在、目标硬盘存在且归属一致、序列号唯一性
        """
        HardDiskSNService._validate_payload(disks)
        asset = HardDiskSNService._resolve_asset(asset_recordcode)
        rcs = [rc for rc in (disk.get("recordcode") for disk in disks) if rc]
        targets = HardDiskSNService._resolve_targets(asset, rcs)
        HardDiskSNService._validate_sn_presence(disks)
        HardDiskSNService._check_duplicates(disks, targets)
        try:
            with transaction.atomic():
                created, updated = HardDiskSNService._apply_disks(asset, targets, disks)
        except IntegrityError as exc:
            if "harddisk_sn_code" in str(exc):
                raise AppValidationError(
                    detail="序列号重复,可能已被并发写入,请刷新后重试",
                    error_code="DUPLICATE_SN_CODE",
                ) from exc
            raise

        return {
            "created": created,
            "updated": updated,
            "total": len(disks),
            "asset_recordcode": asset_recordcode,
        }

    @staticmethod
    def _validate_payload(disks: list[dict[str, Any]]) -> None:
        """校验批次规模与空列表"""
        if len(disks) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量保存不能超过 {MAX_BATCH_SIZE} 条",
                error_code="BATCH_SIZE_EXCEEDED",
            )
        if not disks:
            raise AppValidationError(detail="硬盘列表不能为空", error_code="EMPTY_DISKS")

    @staticmethod
    def _resolve_asset(asset_recordcode: str) -> Asset:
        """解析资产,不存在时抛错"""
        asset = AssetSelector.get_asset_by_recordcode(asset_recordcode)
        if asset is None:
            raise AppValidationError(
                detail=f"资产 recordcode '{asset_recordcode}' 不存在",
                error_code="ASSET_NOT_FOUND",
            )
        return asset

    @staticmethod
    def _resolve_targets(asset: Asset, rcs: list[str]) -> dict[str, HardDiskSN]:
        """批量解析目标硬盘,校验存在性与资产归属"""
        targets = HardDiskSNSelector.get_by_recordcodes(rcs)
        missing = [rc for rc in rcs if rc not in targets]
        if missing:
            raise AppValidationError(
                detail=f"硬盘记录不存在: {', '.join(missing)}",
                error_code="HARD_DISK_NOT_FOUND",
            )
        for target in targets.values():
            if target.asset_recordcode_id != asset.recordcode:
                raise AppValidationError(
                    detail=f"硬盘 {target.harddisk_sn_code} 属于其他资产,禁止批量跨资产修改",
                    error_code="ASSET_MISMATCH",
                )
        return targets

    @staticmethod
    def _validate_sn_presence(disks: list[dict[str, Any]]) -> None:
        """创建盘必须提供非空序列号"""
        for disk in disks:
            if not disk.get("recordcode") and not disk.get("harddisk_sn_code", "").strip():
                raise AppValidationError(detail="硬盘序列号不能为空", error_code="MISSING_SN_CODE")

    @staticmethod
    def _check_duplicates(disks: list[dict[str, Any]], targets: dict[str, HardDiskSN]) -> None:
        """序列号唯一性预检,更新盘回传自身 SN 时豁免"""
        sn_codes = [
            disk.get("harddisk_sn_code", "").strip() for disk in disks if disk.get("harddisk_sn_code", "").strip()
        ]
        existing = HardDiskSNSelector.get_existing_sn_codes(sn_codes)
        duplicates = []
        for disk in disks:
            sn = disk.get("harddisk_sn_code", "").strip()
            if not sn:
                continue
            rc = disk.get("recordcode")
            target = targets.get(rc) if rc else None
            if target is not None and sn == target.harddisk_sn_code:
                continue
            if sn in existing:
                duplicates.append(sn)
        if duplicates:
            raise AppValidationError(
                detail=f"序列号重复: {', '.join(duplicates)}",
                error_code="DUPLICATE_SN_CODE",
            )

    @staticmethod
    def _apply_disks(
        asset: Asset, targets: dict[str, HardDiskSN], disks: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """执行磁盘写入,返回 (created, updated)"""
        created_count = 0
        updated_count = 0
        for disk in disks:
            disk_data = dict(disk)
            rc = disk_data.pop("recordcode", None)
            if rc:
                obj = targets[rc]
                if "harddisk_sn_code" in disk_data:
                    disk_data["harddisk_sn_code"] = disk_data["harddisk_sn_code"].strip()
                for key, value in disk_data.items():
                    setattr(obj, key, value)
                obj.save()
                updated_count += 1
            else:
                disk_data["harddisk_sn_code"] = disk_data["harddisk_sn_code"].strip()
                disk_data["asset_recordcode"] = asset
                HardDiskSN.objects.create(**disk_data)
                created_count += 1
        return created_count, updated_count
