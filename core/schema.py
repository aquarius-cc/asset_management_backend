"""通用 OpenAPI Schema 覆写（全端点共用，DR-1/DR-4）。

本模块收敛**两个**互不相干的 OpenAPI 声明机制，均为「机制写一次、opt-in 写在
被修的 ViewSet 上」：

1. ``ForceFilterDiscoverySchema.get_filter_backends()`` —— 补 ``_is_list_view()``
   启发式缺口（BF-049），见下文背景。
2. ``ForceFilterDiscoverySchema._get_filter_parameters()`` —— 给 ``?search=``
   补字段集说明（BF-052 遗留③），见下文「窄口径搜索」。

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

【窄口径搜索：为什么需要给 ``?search=`` 写说明】
DRF ``SearchFilter`` 自动产出的参数**只有一个英文泛化描述**（``A search term.``），
既不说明匹配哪些字段，也不说明它与本项目另一套 ``?keyword=`` 口径的差异。实测后果
（员工域）：同一个词换参数结果不同——``?search=技术部`` 命中 0 条（部门名不在
``search_fields``），``?keyword=技术部`` 有结果；``?search=在职`` 命中 0 条，
``?keyword=在职`` 命中全部在职员工。消费方无从判断该用哪个。

【为什么改写自动发现结果而非注入新参数】
见 ``_get_filter_parameters`` 的 docstring：override 路径是**整体替换**且会丢掉
``required: false``；改写路径则原样保留自动版全部属性，且**只改已存在的参数、
绝不注入**。

【为什么必须按 action 白名单限定】
注意：改写方案**不注入**参数，故白名单**不再承担防泄漏职责**（防泄漏已由
「只改写已存在参数」从根上保证）。它守的是另一件事——**说明的语义正确性**：
`search_param_note` 断言「同端点存在 keyword 宽口径，两者同传为 AND」。若某个
action 暴露 `search` 却不暴露 `keyword`（例如将来新增的按名精确查询端点），这段
对比说明在该端点就是**错的**。名单把「该端点是否适用窄/宽对比」变成显式决定。
漏登记由护栏测试 ``test_search_param_endpoints_match_view_optin_list`` 双向互锁抓出。
"""

from typing import Any

from drf_spectacular.openapi import AutoSchema
from rest_framework.settings import api_settings


__all__ = ["ForceFilterDiscoverySchema"]


class ForceFilterDiscoverySchema(AutoSchema):
    """为 ViewSet 显式列出的 action 强制开启筛选参数发现 + 补窄口径搜索说明。

    使用方式::

        class MyViewSet(ModelViewSet):
            schema = ForceFilterDiscoverySchema
            force_filter_discovery_actions = frozenset({"export", "statistics"})
            search_param_description_actions = frozenset({"list"})
            search_param_note = "本参数为窄口径；同端点 keyword 为宽口径，两者同传为 AND。"
    """

    def get_filter_backends(self) -> list[Any]:
        """仅当当前 action 在 ViewSet 的 opt-in 名单内时绕过 ``_is_list_view()`` 启发式。"""
        forced_actions = getattr(self.view, "force_filter_discovery_actions", ())
        if getattr(self.view, "action", None) in forced_actions:
            return list(getattr(self.view, "filter_backends", []))
        return super().get_filter_backends()

    def get_override_parameters(self) -> list[Any]:
        """本类不注入 override 参数，保留覆写仅为显式声明该意图。

        ``override_parameters`` 由库对**每个** operation 无条件套用且做整体替换，
        若用它来加 ``?search=`` 说明，就得为每个 action 完整复刻自动版形态，还得
        自己保证「不注入到不读该参数的路由」。改走 ``_get_filter_parameters`` 后
        这两个负担都不存在，故此处只留一行说明，避免后人误以为漏了实现。
        """
        return super().get_override_parameters()

    def _get_filter_parameters(self) -> list[Any]:
        """在**自动发现结果上**改写 ``?search=`` 的 description，而非覆盖它。

        【为什么不走 ``get_override_parameters()``】
        ``_get_parameters()``（``openapi.py:263-276``）最后对 override 执行
        ``parameters[key] = parameter``——**整体替换**。走 override 必须完整复刻
        自动版形态，且 ``build_parameter_type``（``plumbing.py:390-391``）在
        ``required=False`` 时**整个省略 ``required`` 键**，使基线 diff 从「仅
        description」变成「description + 丢失 required: false」。

        【本方案的两个优点】
        ① ``required: false`` 及未来 ``SearchFilter`` 新增的任何属性都**原样保留**；
        ② **只改写已发现的参数、绝不注入**——若某 action 运行时/启发式上不暴露
        ``search``，这里找不到就什么都不做，从根上排除了「文档有、运行时无」的
        反向失真（这是按 action 限定白名单的根本原因）。

        代价：``_get_filter_parameters`` 是库私有方法。本模块已按 drf-spectacular
        0.29 锁定行为，升级库时需重跑 ``test_employee_search_contract`` 护栏。
        """
        # 库私有方法无类型标注，strict 下需按行豁免（ignore 必须与调用同行）
        parameters: list[Any] = list(super()._get_filter_parameters())  # type: ignore[no-untyped-call]
        action = getattr(self.view, "action", None)
        if action not in getattr(self.view, "search_param_description_actions", ()):
            return parameters

        search_fields = list(getattr(self.view, "search_fields", None) or ())
        if not search_fields:
            return parameters

        note = getattr(self.view, "search_param_note", "")
        description = f"模糊匹配字段：{'、'.join(search_fields)}。{note}".rstrip("。")
        for parameter in parameters:
            if parameter.get("name") == api_settings.SEARCH_PARAM and parameter.get("in") == "query":
                parameter["description"] = description
        return parameters
