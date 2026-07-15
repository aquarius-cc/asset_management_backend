"""
通用序列化器

包含 DashboardStat, ErrorResponse, Empty 等通用序列化器。
"""

from rest_framework import serializers


class DashboardStatSerializer(serializers.Serializer):
    total_assets = serializers.IntegerField(help_text="资产总数")
    total_contracts = serializers.IntegerField(help_text="合同总数")
    active_assets = serializers.IntegerField(help_text="在用资产数")


class ErrorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)
    error = serializers.CharField()
    debug_info = serializers.DictField(required=False, allow_null=True)


class EmptySerializer(serializers.Serializer):
    pass
