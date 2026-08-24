"""
硬盘序列号查询选择器

提供硬盘序列号相关的查询方法(从 base_selector.py 拆分)。
"""

from typing import Any

from django.db.models import QuerySet

from apps.assetmanagement.models import HardDiskSN
from core.department_scope import get_asset_linked_queryset_for_user


class HardDiskSNSelector:
    """硬盘序列号查询选择器"""

    @staticmethod
    def get_queryset_for_user(user: Any) -> Any:
        """RBAC 行级过滤(硬盘通过 asset_recordcode 关联到 Asset)"""
        return get_asset_linked_queryset_for_user(user, HardDiskSN.objects.filter(is_deleted=False))

    @staticmethod
    def get_by_recordcode(recordcode: str) -> HardDiskSN | None:
        """按 recordcode 查询单条"""
        try:
            return HardDiskSN.objects.get(recordcode=recordcode, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def get_by_recordcodes(recordcodes: list[str]) -> dict[str, HardDiskSN]:
        """按 recordcode 批量查询(返回 {recordcode: HardDiskSN} 映射)"""
        records = HardDiskSN.objects.filter(recordcode__in=recordcodes, is_deleted=False)
        return {record.recordcode: record for record in records}

    @staticmethod
    def get_by_pk(pk: int) -> HardDiskSN | None:
        """按主键查询"""
        try:
            return HardDiskSN.objects.get(pk=pk, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def get_by_sn_code(sn_code: str) -> HardDiskSN | None:
        """按序列号查询"""
        try:
            return HardDiskSN.objects.get(harddisk_sn_code=sn_code, is_deleted=False)
        except HardDiskSN.DoesNotExist:
            return None

    @staticmethod
    def exists_by_sn_code(sn_code: str) -> bool:
        """检查序列号是否已存在"""
        return HardDiskSN.objects.filter(harddisk_sn_code=sn_code, is_deleted=False).exists()

    @staticmethod
    def get_existing_sn_codes(sn_codes: list[str]) -> set[str]:
        """批量查询已存在的序列号集合"""
        if not sn_codes:
            return set()
        return set(
            HardDiskSN.objects.filter(harddisk_sn_code__in=sn_codes, is_deleted=False).values_list(
                "harddisk_sn_code", flat=True
            )
        )

    @staticmethod
    def get_by_asset(asset_recordcode: str) -> QuerySet[HardDiskSN]:
        """查询某资产的所有硬盘"""
        return HardDiskSN.objects.filter(asset_recordcode=asset_recordcode, is_deleted=False).order_by(
            "harddisk_sn_code"
        )

    @staticmethod
    def get_by_asset_code(asset_code: str) -> QuerySet[HardDiskSN]:
        """按资产编码查询所有硬盘"""
        return HardDiskSN.objects.filter(
            asset_recordcode__asset_code=asset_code,
            asset_recordcode__is_deleted=False,
            is_deleted=False,
        ).order_by("harddisk_sn_code")

    @staticmethod
    def count_by_asset(asset_recordcode: str) -> int:
        """统计某资产的硬盘数量"""
        return HardDiskSN.objects.filter(asset_recordcode=asset_recordcode, is_deleted=False).count()

    @staticmethod
    def get_by_status(status: str) -> QuerySet[HardDiskSN]:
        """按状态查询"""
        return HardDiskSN.objects.filter(harddisk_status=status, is_deleted=False)
