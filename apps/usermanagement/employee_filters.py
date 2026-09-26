"""员工列表/搜索/导出共用的声明式筛选定义。

【为什么是本项目首个 FilterSet】
其余 15 个 ViewSet 一律用声明式 ``filterset_fields``，但 ``filterset_fields``
的**值必须是模型字段路径**——员工部门编码挂在关联对象上（``Employee`` 上无
``department_code``），无法把对外参数名 ``department_code`` 映射到
``employee_department__department_code``（写 ``filterset_fields = ["department_code"]``
会在构造 filterset 时抛 ``FieldDoesNotExist``）。故此处显式声明 FilterSet，
把 ORM 路径藏在 ``field_name`` 里，对外只暴露业务语义名。

【DR-1 取行口径单一入口】
``department_code`` / ``employee_status`` 的解析此前散落且**互相矛盾**：
前端 ``ContactsView.vue`` 两个分支都传 ``department_code``，但列表端点的
``filterset_fields`` 只认 ``employee_department__department_code``、搜索端点
只读 ``keyword``，导致部门筛选控件**两条路径均静默失效**。本模块把两个名字
收敛到一处声明，列表 / 搜索 / 统计 / 导出四条路径共用。

【``employee_department__department_code`` 保留为别名】
不删是为了保持 OpenAPI 纯增量（删参数属请求参数删除，需 §1.3 人工审批）。
新代码一律用 ``department_code``；别名仅为兼容既有调用方与文档。
"""

from __future__ import annotations

from django_filters import rest_framework as filters

from apps.usermanagement.models import Employee, EmployeeStatus


__all__ = [
    "DEPARTMENT_CODE_FIELD",
    "EmployeeFilterSet",
]

#: 部门编码在 Employee 上的真实字段路径（对外参数名不同，故需显式声明）
DEPARTMENT_CODE_FIELD = "employee_department__department_code"


class EmployeeFilterSet(filters.FilterSet):  # type: ignore[misc]  # django_filters 无类型存根
    """员工域筛选：状态 + 部门（列表 / 搜索 / 统计 / 导出共用）。

    【上面那个 type: ignore 不能删】CI 门禁是 ``mypy . --strict``
    （``ci.yml`` backend-type-check），``--strict`` 含
    ``disallow_subclassing_any``，故子类化无存根的 ``FilterSet`` 需要
    ``misc`` 豁免；而用项目宽松配置（``mypy .``，无该开关但开了
    ``warn_unused_ignores``）单跑时它又会被判为 unused-ignore。两种门禁口径
    相反，保留即可——删掉会让 CI 红。

    ``filterset_class`` 会**取代** ``filterset_fields``（DjangoFilterBackend
    优先取前者），故新增筛选维度必须在此声明，否则该维度静默失效。

    状态用 ``ChoiceFilter`` 而非 ``CharFilter``：``ChoiceFilter`` 同时提供
    取值校验（非法值 400）与 OpenAPI enum 文档，二者是 ``filterset_fields``
    旧实现本就具备的能力，改用 CharFilter 会静默丢失（DR-1：不降级既有契约）。
    choices 取自 ``EmployeeStatus``（Model 侧权威源）。
    """

    employee_status = filters.ChoiceFilter(
        choices=EmployeeStatus.choices,
        field_name="employee_status",
        lookup_expr="exact",
    )
    department_code = filters.CharFilter(
        field_name=DEPARTMENT_CODE_FIELD,
        lookup_expr="exact",
    )
    # 兼容别名：历史 filterset_fields 声明名，新代码请用 department_code
    employee_department__department_code = filters.CharFilter(
        field_name=DEPARTMENT_CODE_FIELD,
        lookup_expr="exact",
    )

    class Meta:
        model = Employee
        fields: list[str] = []
