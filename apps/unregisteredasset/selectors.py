"""
未登记资产查询选择器

该模块封装未登记资产的所有查询逻辑，遵循 Selector 层职责：
- 只读操作（查询、筛选、统计）
- 不涉及业务逻辑判断
- 返回 QuerySet 或模型实例

【AGENTS 规范 - Selector 层】
- 单一职责：只负责数据查询，不修改数据
- 可组合：支持链式调用和条件筛选
- 类型安全：返回值有类型标注

【使用方式】
    from .selectors import UnregisteredAssetSelector

    # 根据编码获取
    asset = UnregisteredAssetSelector.get_by_code('UNR-20260526-ABC123')

    # 列表筛选
    queryset = UnregisteredAssetSelector.list_by_filters(
        scenario_type='s1_no_record',
        approval_status='pending'
    )
"""

from typing import TYPE_CHECKING, Optional

from django.db.models import QuerySet


if TYPE_CHECKING:
    from apps.unregisteredasset.models import UnregisteredAsset


class UnregisteredAssetSelector:
    """
    未登记资产查询选择器

    提供未登记资产的查询方法，所有方法均为静态方法，无需实例化。

    【查询方法】
    - get_by_code(): 根据编码获取单条记录
    - get_by_id(): 根据 ID 获取单条记录
    - list_by_filters(): 根据条件筛选列表
    - list_by_discovery_person(): 获取指定发现人的记录
    - list_pending(): 获取待审批记录

    【返回值说明】
    - get_* 方法：返回模型实例或 None
    - list_* 方法：返回 QuerySet

    Example:
        >>> from apps.unregisteredasset.selectors import UnregisteredAssetSelector
        >>>
        >>> # 获取单条记录
        >>> asset = UnregisteredAssetSelector.get_by_code('UNR-20260526-ABC123')
        >>>
        >>> # 筛选待审批的 S1 场景记录
        >>> pending_s1 = UnregisteredAssetSelector.list_by_filters(
        ...     scenario_type='s1_no_record',
        ...     approval_status='pending'
        ... )
    """

    @staticmethod
    def get_by_code(unregistered_code: str) -> Optional["UnregisteredAsset"]:
        """
        根据未登记资产编码获取记录

        Args:
            unregistered_code: 未登记资产编码（如 'UNR-20260526-ABC123'）

        Returns:
            UnregisteredAsset: 找到的记录，不存在则返回 None

        Example:
            >>> asset = UnregisteredAssetSelector.get_by_code('UNR-20260526-ABC123')
            >>> if asset:
            ...     print(asset.asset_name)
        """
        from apps.unregisteredasset.models import UnregisteredAsset

        try:
            return UnregisteredAsset.objects.get(unregistered_code=unregistered_code, is_deleted=False)
        except UnregisteredAsset.DoesNotExist:
            return None

    @staticmethod
    def get_by_id(asset_id: int) -> Optional["UnregisteredAsset"]:
        """
        根据 ID 获取未登记资产记录

        Args:
            asset_id: 记录主键 ID

        Returns:
            UnregisteredAsset: 找到的记录，不存在则返回 None

        Example:
            >>> asset = UnregisteredAssetSelector.get_by_id(1)
        """
        from apps.unregisteredasset.models import UnregisteredAsset

        try:
            return UnregisteredAsset.objects.get(id=asset_id, is_deleted=False)
        except UnregisteredAsset.DoesNotExist:
            return None

    @staticmethod
    def list_by_filters(
        scenario_type: str | None = None,
        approval_status: str | None = None,
        discovery_person: str | None = None,
        handle_type: str | None = None,
        related_asset: str | None = None,
    ) -> QuerySet["UnregisteredAsset"]:
        """
        根据条件筛选未登记资产列表

        所有参数均为可选，不传则不过滤该条件。

        Args:
            scenario_type: 场景类型（s1_no_record/s2_no_outasset/s3_status_mismatch）
            approval_status: 审批状态（pending/approved/rejected）
            discovery_person: 发现人工号
            handle_type: 处理方式
            related_asset: 关联资产编码

        Returns:
            QuerySet[UnregisteredAsset]: 筛选后的查询集

        Example:
            >>> # 获取所有待审批的 S1 场景记录
            >>> pending_s1 = UnregisteredAssetSelector.list_by_filters(
            ...     scenario_type='s1_no_record',
            ...     approval_status='pending'
            ... )
            >>>
            >>> # 获取指定发现人的所有记录
            >>> my_assets = UnregisteredAssetSelector.list_by_filters(
            ...     discovery_person='EMP001'
            ... )
        """
        from apps.unregisteredasset.models import UnregisteredAsset

        queryset = UnregisteredAsset.objects.filter(is_deleted=False)

        if scenario_type:
            queryset = queryset.filter(scenario_type=scenario_type)

        if approval_status:
            queryset = queryset.filter(approval_status=approval_status)

        if discovery_person:
            queryset = queryset.filter(discovery_person__employee_jobcode=discovery_person)

        if handle_type:
            queryset = queryset.filter(handle_type=handle_type)

        if related_asset:
            queryset = queryset.filter(related_asset=related_asset)

        return queryset.order_by("-created_at")

    @staticmethod
    def list_by_discovery_person(
        discovery_person: str, approval_status: str | None = None
    ) -> QuerySet["UnregisteredAsset"]:
        """
        获取指定发现人的未登记资产记录

        Args:
            discovery_person: 发现人工号
            approval_status: 可选，筛选特定审批状态

        Returns:
            QuerySet[UnregisteredAsset]: 该发现人的记录列表

        Example:
            >>> # 获取某员工发现的所有待审批记录
            >>> pending = UnregisteredAssetSelector.list_by_discovery_person(
            ...     discovery_person='EMP001',
            ...     approval_status='pending'
            ... )
        """
        return UnregisteredAssetSelector.list_by_filters(
            discovery_person=discovery_person, approval_status=approval_status
        )

    @staticmethod
    def list_pending() -> QuerySet["UnregisteredAsset"]:
        """
        获取所有待审批的未登记资产记录

        Returns:
            QuerySet[UnregisteredAsset]: 待审批记录列表

        Example:
            >>> pending_list = UnregisteredAssetSelector.list_pending()
            >>> print(f'有 {pending_list.count()} 条待审批记录')
        """
        return UnregisteredAssetSelector.list_by_filters(approval_status="pending")

    @staticmethod
    def list_by_scenario(scenario_type: str) -> QuerySet["UnregisteredAsset"]:
        """
        获取指定场景类型的未登记资产记录

        Args:
            scenario_type: 场景类型（s1_no_record/s2_no_outasset/s3_status_mismatch）

        Returns:
            QuerySet[UnregisteredAsset]: 该场景的记录列表

        Example:
            >>> # 获取所有 S1 场景记录
            >>> s1_assets = UnregisteredAssetSelector.list_by_scenario('s1_no_record')
        """
        return UnregisteredAssetSelector.list_by_filters(scenario_type=scenario_type)

    @staticmethod
    def exists_by_code(unregistered_code: str) -> bool:
        """
        检查指定编码的未登记资产是否存在

        Args:
            unregistered_code: 未登记资产编码

        Returns:
            bool: 是否存在（未删除的）记录

        Example:
            >>> if UnregisteredAssetSelector.exists_by_code('UNR-20260526-ABC123'):
            ...     print('编码已存在')
        """
        from apps.unregisteredasset.models import UnregisteredAsset

        return UnregisteredAsset.objects.filter(unregistered_code=unregistered_code, is_deleted=False).exists()
