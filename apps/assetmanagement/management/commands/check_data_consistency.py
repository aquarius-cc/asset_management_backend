"""
每日数据一致性检查 management command
依据: Project_Requirements/03-安全与运维/06-非功能需求与运维.md §6.3
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.assetmanagement.models import Asset, OutAsset, RepairAsset


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "每日数据一致性检查:验证资产状态与业务记录的一致性"

    def add_arguments(self, parser: Any) -> None:
        # [M-12] issues 非空时以非零退出码终止（manage.py 下 CommandError → exit 1），
        # 供 CI/定时任务据此告警；不带本参数行为逐字节不变
        parser.add_argument(
            "--strict",
            action="store_true",
            dest="strict",
            help="发现一致性问题时抛出 CommandError（非零退出码）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        strict = options.get("strict", False)
        issues = []

        # 检查1: broken 状态资产应有进行中维修记录
        broken_assets = Asset.objects.filter(asset_current_status=Asset.AssetStatus.BROKEN)
        for asset in broken_assets:
            if not RepairAsset.objects.filter(
                asset_recordcode=asset,
                repair_status=RepairAsset.RepairStatus.IN_PROGRESS,
            ).exists():
                msg = f"资产 {asset.asset_code} 状态为 broken 但无进行中维修记录"
                issues.append(msg)

        # 检查2: in_use 状态资产应有出库记录
        in_use_assets = Asset.objects.filter(asset_current_status=Asset.AssetStatus.IN_USE)
        for asset in in_use_assets:
            if not OutAsset.objects.filter(asset_recordcode=asset).exists():
                msg = f"资产 {asset.asset_code} 状态为 in_use 但无出库记录"
                issues.append(msg)

        # 检查3: in_store 状态资产不应有任何出库记录
        # [M-12] 原谓词 out_status=OutAsset.OutStatus.PENDING 引用了从未存在的字段
        # （type: ignore 掩盖的存量 AttributeError，检查 3 对 in_store 资产必然崩溃）。
        # 出库记录创建即资产转 in_use，in_store + 有出库记录即为不一致，无「待处理」子集。
        in_store_assets = Asset.objects.filter(asset_current_status=Asset.AssetStatus.IN_STORE)
        for asset in in_store_assets:
            if OutAsset.objects.filter(asset_recordcode=asset).exists():
                msg = f"资产 {asset.asset_code} 状态为 in_store 但存在出库记录"
                issues.append(msg)

        # 输出结果
        if issues:
            for issue in issues:
                self.stdout.write(self.style.WARNING(issue))
            logger.warning("数据一致性检查发现 %d 个问题", len(issues))
            self.stderr.write(f"ERROR: 发现 {len(issues)} 个一致性问题")
            if strict:
                raise CommandError(f"数据一致性检查发现 {len(issues)} 个问题")
        else:
            self.stdout.write(self.style.SUCCESS("数据一致性检查通过"))
