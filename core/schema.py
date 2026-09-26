"""通用 OpenAPI Schema 覆写（全端点共用，DR-1/DR-4）。

【背景：drf-spectacular 0.29 的 ``_is_list_view()`` 启发式缺口】
``AutoSchema.get_filter_backends()`` 的实现是::

    if not self._is_list_view():
        return []
    return getattr(self.view, 'filter_backends', [])

即**只有「200 响应被推断为 list serializer」的 action 才会发现筛选参数**。
对「返回聚合字典 / 二进制，但运行时确实消费筛选参数」的 action，这道启发式
会整体关闭 ``DjangoFilterBackend`` / ``SearchFilter`` / ``OrderingFilter``
的参数发现，OpenAPI 因此**丢失真实支持的查询参数**。

本项目两个已知触发点（同一机制，故只做一处机制修复）：

| action | 200 响应 | 运行时是否消费筛选参数 |
|:--|:--|:--|
| ``statistics`` | 聚合字典（非 list） | 是（``filter_queryset(get_queryset())``） |
| ``export`` | xlsx 二进制（非 list） | 员工域是；其余 10 个资产类导出端点否 |

【为什么不用 ``@extend_schema(filters=True)``】
drf-spectacular 提供 ``filters=True`` 覆盖，但它只能挂在**该 action 自身的
装饰器**上。员工 ``export`` 的 action 定义在 ``ExportExcelMixin``（11 个导出
端点的唯一实现，DR-1），要逐个 ViewSet 重声明同一 action 等于复制实现，故改用
本模块：**机制写一次，opt-in 写在被修的 ViewSet 上**（类属性
``force_filter_discovery_actions``），未列入的 action 行为与库默认完全一致。

【边界】
不做「全 ViewSet 一律强制发现」。未列入 ``force_filter_discovery_actions``
的 action 一律沿用库默认启发式——例如那 10 个资产类导出端点运行时本就**不跑**
``filter_queryset``（走 Mixin 默认 ``get_export_queryset()``），其 OpenAPI 只声明
``limit`` / ``offset`` 是**如实**的，强行补筛选参数反而会再次制造
「文档有、运行时无」的反向失真（BF-049 的另一半教训）。
"""

from typing import Any

from drf_spectacular.openapi import AutoSchema


__all__ = ["ForceFilterDiscoverySchema"]


class ForceFilterDiscoverySchema(AutoSchema):
    """为 ViewSet 显式列出的 action 强制开启筛选参数发现。

    使用方式::

        class MyViewSet(ModelViewSet):
            schema = ForceFilterDiscoverySchema
            force_filter_discovery_actions = frozenset({"export", "statistics"})
    """

    def get_filter_backends(self) -> list[Any]:
        """仅当当前 action 在 ViewSet 的 opt-in 名单内时绕过 ``_is_list_view()`` 启发式。"""
        forced_actions = getattr(self.view, "force_filter_discovery_actions", ())
        if getattr(self.view, "action", None) in forced_actions:
            return list(getattr(self.view, "filter_backends", []))
        return super().get_filter_backends()
