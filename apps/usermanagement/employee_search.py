"""员工域**两套搜索口径**的对外说明文案（DR-1/DR-4 单一归属）。

【为什么存在】
员工域同时暴露两个都叫「搜索」但语义不同的查询参数,历史上没有任何文档说明差异,
实测导致消费方按直觉选错：

============  ==========================================  ==========================
参数          匹配口径                                      实现
============  ==========================================  ==========================
``?search=``  窄：仅 ``search_fields``（3 个字段）           DRF ``SearchFilter``
``?keyword=`` 宽：4 文本字段 + 部门名称 + 中文状态别名       ``EmployeeSelector.search_employees``
============  ==========================================  ==========================

同一词换参数结果不同,例如 ``?search=技术部`` 命中 0 条（部门名不在 ``search_fields``）,
而 ``?keyword=技术部`` 有结果；``?search=在职`` 命中 0 条,``?keyword=在职`` 命中全部
在职员工。二者在 ``/search/`` 与 ``/export/`` 上**同传为 AND（交集）**,而非 OR。

【为什么文案由代码派生而非手写】
本模块**从 :mod:`apps.usermanagement.selectors` 的权威常量派生**字段清单。手写文案
必然随实现改动而失真——而「文档字段清单与实现分叉」正是本条要修的病本身。
DR-1 禁止同一业务事实在两处独立实现,字段清单属业务事实。
"""

from apps.usermanagement.selectors import (
    SEARCH_DEPARTMENT_FIELD,
    SEARCH_NARROW_FIELDS,
    SEARCH_STATUS_ALIASES,
    SEARCH_TEXT_FIELDS,
    SEARCH_WIDE_ONLY_TEXT_FIELDS,
)


__all__ = [
    "AND_SEMANTICS_HINT",
    "keyword_param_description",
    "search_param_note",
]

#: 两参数同传时的真实语义。DRF 侧 ``filter_queryset`` 叠在 ``search_employees``
#: 结果之上（EmployeeViewSet._filtered_employee_queryset）,故为交集。
AND_SEMANTICS_HINT = "两者同传为 AND（交集）,而非 OR。"

#: 每个状态码取首个别名作为代表（在职/离职/退休）——由映射派生,数量变化时自动跟随
_STATUS_ALIAS_SAMPLES = "、".join(aliases[0] for aliases in SEARCH_STATUS_ALIASES.values() if aliases)


def keyword_param_description() -> str:
    """``?keyword=`` 参数说明（宽口径）。

    仅在**运行时确实读取该参数**的端点声明——``/employees/search/`` 与
    ``/employees/export/``。``/employees/``（list）**不读** ``keyword``，故不声明
    （声明了就是「文档超前于运行时」的反向失真）。
    """
    return (
        f"搜索关键词（宽口径）：匹配 {'、'.join(SEARCH_TEXT_FIELDS)} 四个文本字段、"
        f"关联部门名称（{SEARCH_DEPARTMENT_FIELD}）、"
        f"以及中文状态别名（如 {_STATUS_ALIAS_SAMPLES}）。"
        f"同端点的 search 为窄口径（仅 {'、'.join(SEARCH_NARROW_FIELDS)}，"
        f"不含部门名称与状态别名）。"
        f"{AND_SEMANTICS_HINT}"
    )


def search_param_note() -> str:
    """``?search=`` 参数说明的对比部分（窄口径）。

    字段清单本身由 :class:`core.schema.ForceFilterDiscoverySchema` 从视图的
    ``search_fields`` 现场派生（该属性直接引用 :data:`SEARCH_NARROW_FIELDS`），
    此处只补「与 keyword 的差异」——差异部分无法从 ``search_fields`` 单独推出，
    故由此提供。宽口径多出的字段用 :data:`SEARCH_WIDE_ONLY_TEXT_FIELDS`（求差得出），
    不手写。
    """
    return (
        f"本参数为窄口径，不含部门名称与员工状态。"
        f"同端点的 keyword 为宽口径（额外含 {'、'.join(SEARCH_WIDE_ONLY_TEXT_FIELDS)}、"
        f"部门名称与中文状态别名如 {_STATUS_ALIAS_SAMPLES}）。"
        f"{AND_SEMANTICS_HINT}"
    )
