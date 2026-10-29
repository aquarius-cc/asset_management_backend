"""
资产管理视图公共 Mixins

提供可复用的视图行为:
- RecordcodeLookupMixin: pk / recordcode 双模式对象查找
- AdminWritePermissionMixin: 写操作限制为管理员
"""

import logging
from typing import Any

from django.http import Http404

from core.permissions import IsSystemAdmin, request_method, resolve_viewset_permissions


logger = logging.getLogger(__name__)


class RecordcodeLookupMixin:
    """
    支持 pk(数字)和 recordcode(字符串)双模式查找的 get_object()。

    子类必须设置 lookup_field = "recordcode"(或其变体如 "asset_recordcode__asset_code")。
    """

    def get_object(self) -> Any:
        queryset = self.get_queryset()  # type: ignore[attr-defined]
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]  # type: ignore[attr-defined]

        if lookup_value.isdigit():
            try:
                obj = queryset.get(pk=lookup_value)
                self.check_object_permissions(self.request, obj)  # type: ignore[attr-defined]
                return obj
            except self.queryset.model.DoesNotExist:  # type: ignore[attr-defined]
                # [M-AUD-4] pk 未命中是 digit 值回落 recordcode 查找的正常路径（非异常），
                # debug 级留痕对齐 M-47 范式；真正抛 404 的是下方 recordcode 也未命中分支
                logger.debug("pk 未命中, 回落 recordcode 查找: %s", lookup_value)

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})  # type: ignore[attr-defined]
        except self.queryset.model.DoesNotExist:  # type: ignore[attr-defined]
            raise Http404(f"{self.queryset.model.__name__} '{lookup_value}' not found.")  # type: ignore[attr-defined]

        self.check_object_permissions(self.request, obj)  # type: ignore[attr-defined]
        return obj


class AdminWritePermissionMixin:
    """
    写操作(create/update/destroy)限制为管理员,读操作需认证。

    子类可通过 admin_actions 类属性扩展需管理员权限的操作列表。
    """

    admin_actions = [
        "create",
        "update",
        "partial_update",
        "destroy",
        "change_status",
        "change_outasset_employee",
    ]

    def get_permissions(self) -> Any:
        return resolve_viewset_permissions(
            self.action,  # type: ignore[attr-defined]
            self.admin_actions,
            IsSystemAdmin,
            method=request_method(self),
        )


class OperatorContextMixin:
    """
    操作人上下文 Mixin

    从 request.user 提取操作人信息,供 create/update 等操作
    通过 **self.get_operator_context() 写入操作人字段。
    """

    def get_operator_context(self) -> dict[str, str]:
        """返回操作人工号与姓名上下文(默认使用 auth_username)"""
        username = getattr(self.request.user, "auth_username", None) or str(self.request.user)  # type: ignore[attr-defined]
        return {"operator_jobcode": username, "operator_name": username}
