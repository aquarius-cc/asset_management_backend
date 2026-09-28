"""
通用序列化器

包含 DashboardStat, ErrorResponse, Empty 等通用序列化器。
"""

from rest_framework import serializers


class DashboardStatSerializer(serializers.Serializer):  # type: ignore[type-arg]
    """仪表盘概览统计的响应结构。

    字段集与 ``DashboardSelector.get_overview_statistics()`` 的 return 键
    **逐一对应**（DR-1：响应结构只此一处定义）。本 serializer 原先只声明 3 个
    字段，而 selector 实际返回 13 个，差额 10 个使 drf-spectacular 回退的
    ``serializer_class`` 把基线写成残缺结构——文档写全了反而被判"多字段"
    （BF-050 同型：手工/回退声明不做校正，错误直接进基线）。

    增删本类字段时必须同步 ``get_overview_statistics()`` 的返回字典。
    """

    total_assets = serializers.IntegerField(help_text="用户可见范围内资产总数")
    total_value = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        help_text="用户可见范围内资产采购价合计",
    )
    total_contracts = serializers.IntegerField(help_text="未删除合同总数（不按用户范围隔离）")
    active_assets = serializers.IntegerField(help_text="在用（in_use）资产数")
    in_stock_assets = serializers.IntegerField(help_text="在库（in_store）资产数")
    monthly_distributed = serializers.IntegerField(help_text="本月发放数")
    monthly_recycled = serializers.IntegerField(help_text="本月回收数")
    pending_waste = serializers.IntegerField(help_text="待报废（damaged）数")
    wasted_assets = serializers.IntegerField(help_text="已报废（scrapped）数")
    total_recycled = serializers.IntegerField(help_text="累计回收数")
    total_distributed = serializers.IntegerField(help_text="累计发放数")
    status_distribution = serializers.DictField(
        help_text='按 8 种资产状态分组：{"状态码": {"name": 状态名, "count": 数量}}',
    )
    timestamp = serializers.CharField(help_text="统计生成时刻（ISO 8601 含时区偏移）")


class ErrorResponseSerializer(serializers.Serializer):  # type: ignore[type-arg]
    success = serializers.BooleanField(default=False)
    error = serializers.CharField()
    debug_info = serializers.DictField(required=False, allow_null=True)


class EmptySerializer(serializers.Serializer):  # type: ignore[type-arg]
    pass
