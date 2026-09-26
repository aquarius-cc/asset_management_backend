"""
员工管理视图 —— 读侧查询 action Mixin

【为何拆出（DR-5 / BR-6）】
``apps/usermanagement/views/employee_view.py`` 因 BF-047（导出取行口径收敛）
与 BF-048（员工域行级 RBAC）新增 146 行，一度达 505 行，越过 BR-6 的 500 行
硬上限，且本次新增量 ≥ 50 行，DR-5 要求同步拆分。拆法按**读写职责**切分：
本模块承载全部只读查询 action（7 个），``EmployeeViewSet`` 保留配置、
取行口径与写侧 / 批量 action。

**DRF 继承 action 已被 router 正确收集**（``SimpleRouter.get_urls`` 遍历
``dir(viewset)``，故基类上的 ``@action`` 方法同样生效），行为与拆分前一致；
回归由 ``test_employee_rbac_scope`` / ``test_employee_export`` 锁定。

**与 ``core.excel_export.ExportExcelMixin`` 同型的 mixin 约定**：本模块
只提供 action，不假设宿主类的具体类型，故对 ``self`` 上由宿主类提供的
能力（``get_queryset`` / ``paginate_queryset`` / ``get_serializer`` /
``_filtered_employee_queryset``）沿用既有 ``# type: ignore[attr-defined]``
标注方式，不新造 Protocol。
"""

from typing import TYPE_CHECKING

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.decorators import action

from apps.usermanagement.selectors import EmployeeSelector
from apps.usermanagement.serializers import EmployeeDetailSerializer, EmployeeSerializer
from core.department_scope import get_employee_scoped_queryset_for_user
from utils.response_utils import error_response, success_response


if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.response import Response


__all__ = ["EmployeeQueryActionsMixin"]


# 【BF-050】statistics 返回的是聚合字典，不是分页数组。原先手工声明
# ``EmployeeDetailSerializer(many=True)`` 使基线落成 ``PaginatedEmployeeDetailList``
# （张冠李戴的模板），drf-spectacular 对手工声明不做校正，错误直接进基线。
# 字段集与 ``EmployeeSelector.get_employee_statistics()`` 的返回键逐一对应。
# 用 inline_serializer 而非新增运行时 Serializer：聚合字典由 Selector 直接构造，
# 本端点唯一目的是**文档准确**（BF-050 为 P3 文档失真），不引入第二处
# 结构定义去承担运行时职责。
EmployeeStatisticsDataSchema = inline_serializer(
    name="EmployeeStatistics",
    fields={
        "total_employees": serializers.IntegerField(help_text="可见范围内员工总数"),
        "active_employees": serializers.IntegerField(help_text="可见范围内在职（active）员工数"),
        "by_status": serializers.DictField(help_text='按员工状态分组：{"状态码": {"name": 状态名, "count": 数量}}'),
        "by_department": serializers.DictField(
            child=serializers.IntegerField(),
            help_text='按部门名称分组：{"部门名": 数量}（未分配部门的员工不计入）',
        ),
    },
)


class EmployeeQueryActionsMixin:
    """员工管理 ViewSet 的只读查询 action（列表衍生 / 搜索 / 统计 / 详情衍生）"""

    @extend_schema(
        summary="根据 AuthUser ID 查询绑定的 Employee",
        parameters=[
            OpenApiParameter(
                name="auth_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="AuthUser ID",
                required=True,
            ),
        ],
        responses={200: EmployeeDetailSerializer},
    )
    @action(detail=False, methods=["get"], url_path="by-auth-user/(?P<auth_id>[^/.]+)")
    def by_auth_user(self, request: "Request", auth_id: str | None = None) -> "Response":
        """根据 AuthUser ID 查询绑定的 Employee"""
        # 【BF-048】经 get_queryset() 收窄，避免绕过取行口径直连 Employee.objects。
        # auth_id 来自 URL 捕获组（str），AuthUser 主键是整数：先校验再转换。
        # 不可在转换失败时回落为 None —— filter(auth_user_id=None) 会去匹配
        # 「未绑定账号的员工」而误返 200（由 test_by_auth_user_with_malformed_id
        # _returns_404 锚定）；畸形 ID 一律 404，原实现是 ValueError -> 500。
        if auth_id is None or not auth_id.isdigit():
            return error_response(
                message="未找到绑定的员工",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        employee = self.get_queryset().filter(auth_user_id=int(auth_id)).first()  # type: ignore[attr-defined]
        if employee is None:
            return error_response(
                message="未找到绑定的员工",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response(data=EmployeeDetailSerializer(employee).data)

    @action(detail=False, methods=["get"], url_path="employees/(?P<employee_jobcode>[^/.]+)")
    def get_employee_by_jobcode(self, request: "Request", employee_jobcode: str | None = None) -> "Response":
        """根据工号查询员工(统一格式)"""
        # 【BF-048】原用 self.queryset(未收窄),工号可枚举越权读;改走 get_queryset()
        employee = get_object_or_404(
            self.get_queryset(),  # type: ignore[attr-defined]
            employee_jobcode=employee_jobcode,
        )
        serializer = EmployeeDetailSerializer(employee)
        return success_response(data=serializer.data)

    # 【BF-050】删除原手工 parameters 中的 name(path) / page / page_size 三条：
    # 本 action 是 detail=False，路径无占位符故 `name` 无处可填；端点不分页故
    # page / page_size 无效。
    #
    # 【筛选参数靠 AutoSchema 找回，不靠手工再写一遍】drf-spectacular 0.29 的
    # ``AutoSchema.get_filter_backends()`` 有一道启发式：``if not self._is_list_view():
    # return []``——只有「200 响应被推断为 list serializer」的 action 才会发现筛选
    # 参数。本端点返回聚合字典（非 list），故自动注入整体关闭；而运行时
    # ``filter_queryset(get_queryset())`` 确实接受 employee_status /
    # department_code / ordering / search。即**响应形状决定筛选参数是否被声明**：
    # 原先那三条错误参数之所以"看着像"覆盖了自动注入，实际是错误地把响应声明成
    # many=True 才让 _is_list_view() 为真——把响应修对反而让参数全部消失（已实测）。
    # 修法：``EmployeeViewSet.schema = ForceFilterDiscoverySchema`` +
    # ``force_filter_discovery_actions = {"export", "statistics"}``（见 core/schema.py），
    # 由 EmployeeFilterSet 生成参数，enum / title / 选项说明完整保留。
    @extend_schema(
        summary="员工统计（按当前可见范围聚合）",
        responses={200: EmployeeStatisticsDataSchema},
    )
    @action(detail=False, methods=["get"], url_path="statistics")
    def statistics(self, request: "Request") -> "Response":
        """获取员工统计信息(统一格式)

        【口径统一 2026-09-26】统计 = 列表当前可见范围的聚合，故传入
        ``filter_queryset`` 后的 queryset；此前固定统计全量，导致 OpenAPI
        已声明的 ``employee_status`` / ``department_code`` 在本端点形同虚设。

        【BF-048】可见范围含行级权限收窄，故本端点各聚合数值随调用者部门范围变化。
        """
        # 【AGENTS 规范 - P1-10】统计逻辑迁移到 EmployeeSelector.get_employee_statistics()
        stats = EmployeeSelector.get_employee_statistics(
            self.filter_queryset(self.get_queryset())  # type: ignore[attr-defined]
        )
        return success_response(data=stats)

    # 显式指定 url_path 后,后端实际路径以 url_path 值为准。
    # @action 装饰器未指定 url_path,会默认使用方法名 active_employees
    @action(detail=False, methods=["get"], url_path="active_employees")
    def active_employees(self, request: "Request") -> "Response":
        """获取在职员工列表(统一格式)

        【BF-048 收窄 2026-09-26】口径由「所有在职员工」改为「调用者部门范围内的
        在职员工」,与 list/retrieve 同口径(前端无消费方,收窄零破坏面)。
        """
        # 【AGENTS 规范 - P1-10】使用 EmployeeSelector.get_active_employees() 替代直接 ORM 调用
        queryset = get_employee_scoped_queryset_for_user(request.user, EmployeeSelector.get_active_employees())

        page = self.paginate_queryset(queryset)  # type: ignore[attr-defined]
        if page is not None:
            serializer = self.get_serializer(page, many=True)  # type: ignore[attr-defined]
            return self.get_paginated_response(serializer.data)  # type: ignore[attr-defined,no-any-return]

        serializer = self.get_serializer(queryset, many=True)  # type: ignore[attr-defined]
        return success_response(
            data={
                # 【P2-07 修复】使用 queryset.count() 替代 len(serializer.data),避免不必要的序列化
                "count": queryset.count(),
                "results": serializer.data,
            }
        )

    @extend_schema(
        summary="全局模糊搜索员工",
        description=(
            "在员工姓名、工号、手机号、部门名称等关键字段中进行不区分大小写的模糊搜索。\n"
            "✅ 支持中文/英文/数字混合搜索 | ✅ 自动去重 | ✅ 分页返回\n"
            "本端点与列表共享取行口径：可叠加 employee_status / department_code 收窄结果。"
        ),
        parameters=[
            OpenApiParameter(
                name="keyword",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="搜索关键词",
                required=True,
            ),
            # 【不要重复声明筛选参数】employee_status / department_code（含
            # employee_department__department_code 别名）由 EmployeeFilterSet
            # 自动注入到本 action。drf-spectacular 对同名参数是「手工覆盖自动」
            # 而非合并：手工写一遍会削平自动注入的 enum / title / 选项说明
            # （BF-047 回归）。新增筛选维度请改 employee_filters.py。
            OpenApiParameter(name="page", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="page_size", type=OpenApiTypes.INT, location=OpenApiParameter.QUERY, default=20),
        ],
        responses={200: EmployeeSerializer(many=True), 400: OpenApiResponse(description="参数错误")},
    )
    @action(detail=False, methods=["get"], url_path="search", permission_classes=[permissions.IsAuthenticated])
    def global_search(self, request: "Request") -> "Response":
        """
        全局模糊搜索员工(统一格式)

        【AGENTS 规范 - P3-29】搜索逻辑(含状态别名映射)已迁移到
        EmployeeSelector.search_employees(),视图层仅负责调用 Selector 和分页。

        【口径统一 2026-09-26】改用 :meth:`_filtered_employee_queryset`,使
        department_code / employee_status 在搜索路径上真正生效（此前
        ContactsView 搜索分支传部门筛选却被静默忽略）。
        """
        keyword = request.query_params.get("keyword", "").strip()
        if not keyword:
            return error_response(message="请提供搜索关键词")

        # 【AGENTS 规范 - P3-29】使用 EmployeeSelector 替代视图层手写 Q 条件
        queryset = self._filtered_employee_queryset(keyword)  # type: ignore[attr-defined]

        page = self.paginate_queryset(queryset)  # type: ignore[attr-defined]
        if page is not None:
            serializer = self.get_serializer(page, many=True)  # type: ignore[attr-defined]
            return self.get_paginated_response(serializer.data)  # type: ignore[attr-defined,no-any-return]

        serializer = self.get_serializer(queryset, many=True)  # type: ignore[attr-defined]
        return success_response(
            data={
                # 【P2-07 修复】使用 queryset.count() 替代 len(serializer.data)
                "count": queryset.count(),
                "results": serializer.data,
            }
        )

    @action(detail=False, methods=["get"], url_path="(?P<employee_jobcode>[^/.]+)/department")
    def get_department_by_jobcode(self, request: "Request", employee_jobcode: str | None = None) -> "Response":
        """
        根据员工工号查询所在部门

        返回字段:
        - department_code: 部门编码
        - department_name: 部门名称
        - level: 部门层级
        - parent_code: 上级部门编码
        """
        employee = EmployeeSelector.get_employee_by_jobcode(employee_jobcode) if employee_jobcode else None
        if not employee:
            return error_response(message=f"员工 {employee_jobcode} 不存在", status_code=status.HTTP_404_NOT_FOUND)

        if not employee.employee_department:
            return error_response(message=f"员工 {employee_jobcode} 未分配部门", status_code=status.HTTP_404_NOT_FOUND)

        dept = employee.employee_department
        return success_response(
            data={
                "recordcode": dept.recordcode,
                "department_code": dept.department_code,
                "department_name": dept.department_name,
                "level": dept.level,
                "parent_department_code": dept.parent.department_code if dept.parent else None,
                "path": dept.path,
            }
        )
