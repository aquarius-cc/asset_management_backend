"""
资产管理视图公共 Mixins

提供可复用的视图行为：
- RecordcodeLookupMixin: pk / recordcode 双模式对象查找
- AdminWritePermissionMixin: 写操作限制为管理员
"""

from django.http import Http404
from rest_framework import permissions

from core.permissions import IsSystemAdmin


class RecordcodeLookupMixin:
    """
    支持 pk（数字）和 recordcode（字符串）双模式查找的 get_object()。

    子类必须设置 lookup_field = "recordcode"（或其变体如 "asset_recordcode__asset_code"）。
    """

    def get_object(self):
        queryset = self.get_queryset()
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        if lookup_value.isdigit():
            try:
                obj = queryset.get(pk=lookup_value)
                self.check_object_permissions(self.request, obj)
                return obj
            except self.queryset.model.DoesNotExist:
                pass

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except self.queryset.model.DoesNotExist:
            raise Http404(f"{self.queryset.model.__name__} '{lookup_value}' not found.")

        self.check_object_permissions(self.request, obj)
        return obj


class AdminWritePermissionMixin:
    """
    写操作（create/update/destroy 等）限制为管理员，读操作需认证。

    子类可通过 admin_actions 类属性扩展需管理员权限的操作列表。
    """
    admin_actions = [
        "create", "update", "partial_update", "destroy",
        "change_status", "change_outasset_employee",
    ]

    def get_permissions(self):
        if self.action in self.admin_actions:
            return [IsSystemAdmin()]
        return [permissions.IsAuthenticated()]
