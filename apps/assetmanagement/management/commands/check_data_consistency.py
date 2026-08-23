"""
每日数据一致性检查 management command
依据: Project_Requirements/03-安全与运维/06-非功能需求与运维.md §6.3
"""

import logging

from django.core.management.base import BaseCommand

from apps.assetmanagement.models import Asset, OutAsset, RepairAsset


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "每日数据一致性检查:验证资产状态与业务记录的一致性"

    def handle(self, *args, **options):
        issues = []

        # 检查1: broken 状态资产应有进行中维修记录
        broken_assets = Asset.objects.filter(
            asset_current_status=Asset.AssetStatus.BROKEN
        )
        for asset in broken_assets:
            if not RepairAsset.objects.filter(
                asset_recordcode=asset,
                repair_status=RepairAsset.RepairStatus.IN_PROGRESS,
            ).exists():
                msg = f"资产 {asset.asset_code} 状态为 broken 但无进行中维修记录"
                issues.append(msg)

        # 检查2: in_use 状态资产应有出库记录
        in_use_assets = Asset.objects.filter(
            asset_current_status=Asset.AssetStatus.IN_USE
        )
        for asset in in_use_assets:
            if not OutAsset.objects.filter(asset_recordcode=asset).exists():
                msg = f"资产 {asset.asset_code} 状态为 in_use 但无出库记录"
                issues.append(msg)

        # 检查3: in_store 状态资产不应有进行中出库记录
        in_store_assets = Asset.objects.filter(
            asset_current_status=Asset.AssetStatus.IN_STORE
        )
        for asset in in_store_assets:
            if OutAsset.objects.filter(
                asset_recordcode=asset,
                out_status=OutAsset.OutStatus.PENDING,
            ).exists():
                msg = f"资产 {asset.asset_code} 状态为 in_store 但有待处理出库记录"
                issues.append(msg)

        # 输出结果
        if issues:
            for issue in issues:
                self.stdout.write(self.style.WARNING(issue))
            logger.warning(f"数据一致性检查发现 {len(issues)} 个问题")
            self.stderr.write(f"ERROR: 发现 {len(issues)} 个一致性问题")
        else:
            self.stdout.write(self.style.SUCCESS("数据一致性检查通过"))
