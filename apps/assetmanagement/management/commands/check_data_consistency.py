"""
每日数据一致性检查 management command
依据: Project_Requirements/03-安全与运维/06-非功能需求与运维.md §6.3
"""

import logging
from typing import Any, cast

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

        # [M-PERF-04] 3N+3→5：一次拉取维修中/已出库的资产编码集合，
        # 三轮巡检改为对 Asset 结果集做内存判定，查询数与资产量解耦。
        # recordcode 为 CharField 主键（str），django-stubs 对 FK _id 回退 int 推断，cast 收口。
        repairing_codes = cast(
            "set[str]",
            {
                code
                for code in RepairAsset.objects.filter(repair_status=RepairAsset.RepairStatus.IN_PROGRESS).values_list(
                    "asset_recordcode_id", flat=True
                )
                if code is not None
            },
        )
        out_codes = cast(
            "set[str]",
            {code for code in OutAsset.objects.values_list("asset_recordcode_id", flat=True) if code is not None},
        )

        for recordcode, asset_code in Asset.objects.filter(asset_current_status=Asset.AssetStatus.BROKEN).values_list(
            "recordcode", "asset_code"
        ):
            if recordcode not in repairing_codes:
                issues.append(f"资产 {asset_code} 状态为 broken 但无进行中维修记录")

        for recordcode, asset_code in Asset.objects.filter(asset_current_status=Asset.AssetStatus.IN_USE).values_list(
            "recordcode", "asset_code"
        ):
            if recordcode not in out_codes:
                issues.append(f"资产 {asset_code} 状态为 in_use 但无出库记录")

        for recordcode, asset_code in Asset.objects.filter(asset_current_status=Asset.AssetStatus.IN_STORE).values_list(
            "recordcode", "asset_code"
        ):
            if recordcode in out_codes:
                issues.append(f"资产 {asset_code} 状态为 in_store 但存在出库记录")

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
