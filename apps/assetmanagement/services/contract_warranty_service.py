"""
合同质保期同步服务 - 提供质保期更新时自动同步关联资产的保修期。

Class:
  - ContractWarrantyService: 合同质保期同步服务
    - update_warranty_period: 更新合同质保期并同步关联资产保修期
    - _sync_asset_warranty: 同步资产保修期(仅同步未手动修改的资产)
    - get_contract_warranty_info: 获取合同质保信息
    - batch_update_asset_warranty: 批量更新指定资产的保修期

调用链:
  本模块被 -> ContractViewSet(质保期相关 action)调用
  本模块依赖 -> Asset, Contract, GenericAuditService
"""

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.assetmanagement.models import Asset, Contract
from core.audit_service import GenericAuditService


logger = logging.getLogger(__name__)


class ContractWarrantyService:
    """
    合同质保期同步服务

    提供质保期更新和资产保修期同步功能。
    """

    def __init__(self, contract: Contract):
        self.contract = contract

    def update_warranty_period(self, new_period: int, operator: str = "system") -> dict[str, Any]:
        """
        更新合同质保期并同步关联资产

        Args:
            new_period: 新的质保期(年)
            operator: 操作人

        Returns:
            更新结果,包含old_period、new_period、synced_assets
        """
        old_period = self.contract.contract_warranty_period
        self.contract.contract_warranty_period = new_period
        self.contract.save(update_fields=["contract_warranty_period", "updated_at"])

        # 同步关联资产的保修期
        synced_count = self._sync_asset_warranty(new_period)

        # 记录审计日志
        GenericAuditService.log_update(
            record_code=self.contract.contract_code,
            app_label="contract",
            description=f"更新合同质保期: {old_period}年 -> {new_period}年",
            before_data={"contract_warranty_period": old_period},
            after_data={"contract_warranty_period": new_period, "synced_assets": synced_count},
            operator_jobcode=operator,
        )

        return {"old_period": old_period, "new_period": new_period, "synced_assets": synced_count}

    def _sync_asset_warranty(self, warranty_period: int) -> int:
        """
        同步关联资产的保修期

        只更新未手动修改过保修期的资产。

        Args:
            warranty_period: 新的保修期(年)

        Returns:
            同步的资产数量
        """
        # 查询关联的资产(未手动修改过保修期的)
        assets = list(
            Asset.objects.filter(
                asset_contract_recordcode=self.contract, is_deleted=False, warranty_manually_modified=False
            )
        )

        if not assets:
            return 0

        # 批量更新
        now = timezone.now()
        for asset in assets:
            asset.asset_warranty_period = warranty_period
            asset.updated_at = now

        Asset.objects.bulk_update(assets, ["asset_warranty_period", "updated_at"])

        logger.info(f"批量同步{len(assets)}个资产保修期 -> {warranty_period}年")

        return len(assets)

    def get_contract_warranty_info(self) -> dict[str, Any]:
        """
        获取合同质保期信息

        Returns:
            包含合同质保期和关联资产保修期统计的信息
        """
        from django.db.models import Count, Q

        # 查询关联资产
        assets = Asset.objects.filter(asset_contract_recordcode=self.contract, is_deleted=False)

        # 使用聚合查询一次性获取统计数据
        stats = assets.aggregate(
            total=Count("id"),
            synced=Count("id", filter=Q(warranty_manually_modified=False)),
            manual=Count("id", filter=Q(warranty_manually_modified=True)),
        )

        # 统计保修期分布
        warranty_distribution = {}
        for asset in assets.values("asset_warranty_period").annotate(count=Count("id")):
            warranty = asset["asset_warranty_period"] or 0
            warranty_distribution[warranty] = asset["count"]

        return {
            "contract_warranty_period": self.contract.contract_warranty_period,
            "total_assets": stats["total"],
            "synced_assets": stats["synced"],
            "manual_assets": stats["manual"],
            "warranty_distribution": warranty_distribution,
        }

    @transaction.atomic
    def batch_update_asset_warranty(
        self, asset_recordcodes: list[str], warranty_period: int, operator: str = "system"
    ) -> dict[str, Any]:
        """
        批量更新指定资产的保修期

        Args:
            asset_recordcodes: 资产recordcode列表
            warranty_period: 新的保修期(年)
            operator: 操作人

        Returns:
            更新结果
        """
        assets = list(
            Asset.objects.filter(
                recordcode__in=asset_recordcodes, asset_contract_recordcode=self.contract, is_deleted=False
            )
        )

        if not assets:
            # 记录审计日志(即使没有更新的资产)
            GenericAuditService.log_update(
                record_code=self.contract.contract_code,
                app_label="contract",
                description=f"批量更新资产保修期: 0个资产(请求{len(asset_recordcodes)}个,匹配0个) -> {warranty_period}年",
                after_data={
                    "asset_count": 0,
                    "warranty_period": warranty_period,
                    "asset_recordcodes": asset_recordcodes,
                },
                operator_jobcode=operator,
            )
            return {"total_requested": len(asset_recordcodes), "updated_count": 0, "warranty_period": warranty_period}

        # 批量更新
        for asset in assets:
            asset.asset_warranty_period = warranty_period
            asset.warranty_manually_modified = True  # 标记为手动修改

        Asset.objects.bulk_update(assets, ["asset_warranty_period", "warranty_manually_modified", "updated_at"])

        # 记录审计日志
        GenericAuditService.log_update(
            record_code=self.contract.contract_code,
            app_label="contract",
            description=f"批量更新资产保修期: {len(assets)}个资产 -> {warranty_period}年",
            after_data={
                "asset_count": len(assets),
                "warranty_period": warranty_period,
                "asset_recordcodes": asset_recordcodes,
            },
            operator_jobcode=operator,
        )

        return {
            "total_requested": len(asset_recordcodes),
            "updated_count": len(assets),
            "warranty_period": warranty_period,
        }
