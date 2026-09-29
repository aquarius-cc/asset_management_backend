"""
员工管理视图
"""

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet
from django.http import HttpResponseBase
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.usermanagement.employee_filters import EmployeeFilterSet
from apps.usermanagement.employee_search import keyword_param_description, search_param_note
from apps.usermanagement.models import Employee, EmployeeRole, EmployeeStatus
from apps.usermanagement.selectors import SEARCH_NARROW_FIELDS, EmployeeSelector
from apps.usermanagement.serializers import (
    EmployeeBatchCreateSerializer,
    EmployeeBatchDeleteSerializer,
    EmployeeBatchSortSerializer,
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeSerializer,
    EmployeeUpdateSerializer,
)
from apps.usermanagement.services import EmployeeService
from apps.usermanagement.views.employee_auth_mixin import EmployeeAuthMixin
from apps.usermanagement.views.employee_query_actions import EmployeeQueryActionsMixin
from core.batch_mixins import BatchDeleteViewMixin, BatchResponseHelper
from core.excel_export import ExportExcelMixin
from core.excel_export.schema import EXPORT_ACTION_SCHEMA, EXPORT_PAGINATION_PARAMETERS
from core.mixins import LoggingMixin, ResponseWrapperMixin
from core.pagination import CustomPageNumberPagination
from core.permissions import CanExportExcel, IsSystemAdmin
from core.schema import ForceFilterDiscoverySchema
from utils.response_utils import error_response, success_response


if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.response import Response
    from rest_framework.serializers import Serializer


# LoggingMixin.perform_* 与 DRF Mixin 存根签名存在已知偏差(项目内 mixin, 运行时行为正确)
class EmployeeViewSet(  # type: ignore[misc]
    EmployeeAuthMixin,
    BatchDeleteViewMixin,
    EmployeeQueryActionsMixin,
    ExportExcelMixin,
    LoggingMixin,
    ResponseWrapperMixin,
    viewsets.ModelViewSet,  # type: ignore[type-arg]
):
    """
    员工管理视图集

    继承 ResponseWrapperMixin 自动处理统一的响应格式:
    - list: 分页/不分页均返回 {code, msg, data}
    - create: 返回 {code, msg, data}
    - retrieve: 返回 {code, msg, data}
    - update/partial_update: 返回 {code, msg, data}
    - destroy: 返回 {code, msg, data}

    自定义 action 中手动调用 success_response/error_response 保持统一格式

    【修复 S12】管理操作需要管理员权限,防止普通用户创建/修改/删除员工

    【DR-5 / BR-6 拆分 2026-09-26】只读查询 action（by-auth-user / 按工号 /
    statistics / active_employees / search / 按工号查部门）迁至
    ``EmployeeQueryActionsMixin``，本类保留配置、取行口径与写侧 / 批量 action。
    """

    queryset = EmployeeSelector.get_queryset_with_bind_status()
    serializer_class = EmployeeSerializer
    pagination_class = CustomPageNumberPagination

    #: 员工导出列。不含 employee_phone：导出属批量落盘行为，最小化 PII 外泄面。
    export_columns: list[dict[str, Any]] = [
        {"header": "员工工号", "field": "employee_jobcode"},
        {"header": "员工名称", "field": "employee_name"},
        {"header": "系统角色", "field": "role", "display_map": dict(EmployeeRole.choices)},
        {"header": "员工状态", "field": "employee_status", "display_map": dict(EmployeeStatus.choices)},
        {"header": "所属部门", "field": "employee_department__department_name"},
        {"header": "员工位置", "field": "employee_location"},
    ]
    export_filename = "employees.xlsx"
    export_sheet_name = "员工列表"

    def get_permissions(self) -> list[permissions.BasePermission]:
        permission_classes: list[type[permissions.BasePermission]]
        """
        自定义权限:管理员可管理员工,普通用户只能查看
        """
        # H2 修复:绑定/解绑操作使用 IsSystemAdmin 而非 IsAdminUser
        if self.action == "export_excel":
            # 导出为批量落盘行为,须走导出权限矩阵。
            # 不可落入下方 else 的 IsAuthenticated(否则任意登录用户可导出全量员工档案)。
            permission_classes = [CanExportExcel]
        elif self.action in [
            "bind_auth_user",
            "unbind_auth_user",
            "replace_auth_user",
        ]:
            permission_classes = [IsSystemAdmin]
        elif self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "batch_create",
            "batch_delete",
            "batch_sort",
            "change_status",
        ]:
            permission_classes = [IsSystemAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    #: 【DR-1 收敛】显式 FilterSet 而非 filterset_fields：员工部门编码挂在关联对象上，
    #: 声明式 filterset_fields 无法把对外参数名 department_code 映射到
    #: employee_department__department_code。filterset_class 会**取代**
    #: filterset_fields，新增筛选维度必须在 employee_filters.py 声明，否则静默失效。
    filterset_class = EmployeeFilterSet
    search_fields = list(SEARCH_NARROW_FIELDS)
    ordering_fields = [
        "employee_jobcode",
        "employee_name",
        "sort_order",
        "employee_department__level",
        "employee_department__department_code",
        "employee_department__sort_order",
    ]
    ordering = [
        "employee_department__level",
        "employee_department__department_code",
        "employee_department__sort_order",
        "sort_order",
        "employee_jobcode",
    ]
    lookup_field = "employee_jobcode"

    # 【BF-049 / BF-050】这两个 action 的 200 响应不是 list（聚合字典 / xlsx 二进制），
    # drf-spectacular 0.29 的 ``_is_list_view()`` 启发式会整体关闭筛选参数发现，而运行时
    # ``_filtered_employee_queryset`` 确实消费 employee_status / department_code /
    # ordering / search / keyword。机制与边界详见 core/schema.py。
    # 注意名单里是 **action 方法名**（``view.action`` 取自 DRF ``action_map``，值即方法名），
    # 不是 url_path：``export_excel`` 而非 ``export``。
    schema = ForceFilterDiscoverySchema()
    force_filter_discovery_actions = frozenset({"export_excel", "statistics"})
    # 【A-44 遗留③】``?search=`` 自动产出的描述只有泛化英文 "A search term."，
    # 不说明字段集、也不说明与 ``?keyword=`` 的差异。给这 4 个 action 补说明。
    # 名单即「运行时真正暴露 search 的 action」——override 对每个 operation 无条件
    # 生效，不限定就会把 search 注入 retrieve/update/bind-auth-user 等 7 个不读它的
    # 路由，制造「文档有、运行时无」的反向失真。漏登记由护栏测试
    # test_search_param_not_leaked_to_non_search_routes 抓出。
    # 名单里是 **action 方法名**（同 force_filter_discovery_actions）。
    search_param_description_actions = frozenset({"list", "global_search", "export_excel", "statistics"})
    search_param_note = search_param_note()

    # ---------- 取行口径单一入口（DR-1 / DR-3） ----------

    def get_queryset(self) -> QuerySet[Employee]:
        """员工域行级隔离单一入口(BF-048)：按调用者部门范围收窄。

        覆写 DRF 默认 ``get_queryset()`` 而非只改 ``_filtered_employee_queryset``,
        因为 ``get_object()`` 内部即 ``filter_queryset(get_queryset())`` —— 挂在这里
        可一次覆盖 list / retrieve / search / statistics / export 五条读路径,
        含 ``retrieve``(工号可枚举)这一原先无任何收窄的旁路。

        范围规则集中在 ``core.department_scope``(DR-1),与
        ``OperationLogSelector._scope_by_user`` 同语义：dept_manager 见本部门+下级,
        asset_admin/regular_user 见本部门,system_admin/auditor/superuser 不限,
        部门级角色但无部门则空集。
        """
        return EmployeeSelector.get_queryset_for_user(self.request.user)

    def _filtered_employee_queryset(self, keyword: str = "") -> QuerySet[Employee]:
        """员工域取行口径唯一实现，供 list / search / statistics / export 共用。

        步骤固定为「列表同源基准 -> search_employees 搜索语义 -> DRF 声明式筛选」，
        任一路径单独实现即构成口径分叉（BF-047 的成因）。

        Args:
            keyword: 搜索关键词。**列表口径**的搜索（与 ``/search/`` 端点同源）；
                空串表示不启用搜索。DRF ``SearchFilter`` 的 ``?search=`` 是另一套
                更窄的语义（``search_fields`` 不含部门名、无状态别名映射），
                前端只应使用 ``keyword``。

        Returns:
            员工查询集（已按声明式筛选与 ordering 收窄）
        """
        base = self.get_queryset()
        keyword = keyword.strip()
        if keyword:
            base = EmployeeSelector.search_employees(keyword, base=base)
        return self.filter_queryset(base)

    def get_export_queryset(self) -> QuerySet[Employee]:
        """导出取行口径：与列表同源（含 ``keyword`` 与声明式筛选）。

        覆写 :meth:`core.excel_export.ExportExcelMixin.get_export_queryset` 的默认
        实现，使导出的行集合等于用户在列表上看到的行集合。

        注意 ``?search=`` 走 DRF SearchFilter 的窄口径，与列表的 ``keyword``
        语义不同（见 :meth:`_filtered_employee_queryset` 说明）。
        """
        keyword = str(self.request.query_params.get("keyword", ""))
        return self._filtered_employee_queryset(keyword)

    def update(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """更新员工(含审计日志)"""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        before_data = EmployeeDetailSerializer(instance).data
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        # get_serializer 返回 BaseSerializer, 运行时为 Serializer 子类
        self.perform_update(serializer)  # type: ignore[arg-type]
        after_data = EmployeeDetailSerializer(instance).data
        from apps.usermanagement.employee_audit_adapter import EmployeeAuditAdapter

        EmployeeAuditAdapter.log_update(
            instance,
            before_data,
            after_data,
            request.user.auth_username if hasattr(request.user, "auth_username") else None,
            str(request.user) if hasattr(request.user, "__str__") else None,
        )
        return success_response(data=serializer.data, message="更新成功")

    def partial_update(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """部分更新员工(含审计日志)"""
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """删除员工(含审计日志)"""
        instance = self.get_object()
        from apps.usermanagement.employee_audit_adapter import EmployeeAuditAdapter

        EmployeeAuditAdapter.log_delete(
            instance.employee_jobcode,
            instance.employee_name,
            request.user.auth_username if hasattr(request.user, "auth_username") else None,
            str(request.user) if hasattr(request.user, "__str__") else None,
        )
        self.perform_destroy(instance)
        return success_response(message="删除成功")

    def get_serializer_class(self) -> "type[Serializer[Any]]":
        """根据不同的操作选择不同的序列化器"""
        if self.action == "create":
            return EmployeeCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return EmployeeUpdateSerializer
        elif self.action == "retrieve":
            return EmployeeDetailSerializer
        return EmployeeSerializer

    # ---------- 自定义动作（只读查询 action 见 EmployeeQueryActionsMixin） ----------

    # 【BF-049 局部修复 · 员工域导出端点】Mixin 的 ``export_excel`` 声明了
    # ``parameters=EXPORT_PAGINATION_PARAMETERS``（limit / offset），而 ``keyword`` 是
    # 员工域特有语义（来自 ``get_export_queryset()`` 读 ``?keyword=``），直接加进
    # Mixin 共享片段会污染另外 10 个资产类导出端点的文档（BF-049 根因）。
    # 故在此**重声明同一 action** 并委托 Mixin 实现（不复制实现体，DR-1）：
    # 仅补 ``keyword`` 声明；FilterSet 能产出的 employee_status / department_code 与
    # SearchFilter / OrderingFilter 参数由 ``ForceFilterDiscoverySchema`` 找回。
    # **未动其余 10 个导出端点**：它们走 Mixin 默认 ``get_export_queryset()``，
    # 运行时不跑 ``filter_queryset``，本就**不消费**筛选参数，只声明 limit / offset
    # 是如实的——故 BF-049 为「部分修复」。
    # 两处 type: ignore 均为 django-stubs 把 ``@action`` 方法建模为描述符
    # （ViewSetAction）所致：重声明方法的签名被判与 supertype 不兼容，且
    # ``super().method()`` 被当作实例变量调用。与本类顶部 LoggingMixin 的
    # ``# type: ignore[misc]`` 同源，运行时行为正确。
    @extend_schema(
        **{
            **EXPORT_ACTION_SCHEMA,
            "parameters": [
                *EXPORT_PAGINATION_PARAMETERS,
                OpenApiParameter(
                    name="keyword",
                    type=OpenApiTypes.STR,
                    location=OpenApiParameter.QUERY,
                    description=keyword_param_description(),
                    required=False,
                ),
            ],
        }
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_excel(  # type: ignore[override]
        self, request: Any
    ) -> "HttpResponseBase | Response":
        """导出员工(统一格式)。实现见 :meth:`core.excel_export.ExportExcelMixin.export_excel`。"""
        return super().export_excel(request)  # type: ignore[call-arg,misc]

    @action(detail=False, methods=["post"], url_path="batch-create")
    def batch_create(self, request: "Request") -> "Response":
        """批量创建员工"""
        serializer = EmployeeBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = EmployeeService.batch_create_employee(serializer.validated_data["items"])

        # 【DR-1 收敛】响应组装复用 BatchResponseHelper(message 显式传入, 契约不变)
        return BatchResponseHelper.create_response(
            result,
            EmployeeDetailSerializer,
            message=f"批量创建完成,成功 {result['success_count']} 条,失败 {result['fail_count']} 条",
            request_items=serializer.initial_data.get("items"),
        )

    batch_delete_serializer = EmployeeBatchDeleteSerializer
    batch_delete_service = EmployeeService.batch_delete_employee
    batch_delete_passes_operator = False

    @extend_schema(
        summary="更改员工状态",
        # 直接读 request.data.get("status")，无运行时 Serializer，故基线缺
        # requestBody。取值域以 Employee.EMPLOYEE_STATUS_CHOICES 为唯一真值
        # （不从字面量硬编码，DR-1）；改枚举时本声明自动跟随。
        request=inline_serializer(
            name="EmployeeStatusChange",
            fields={
                "status": serializers.ChoiceField(
                    choices=Employee.EMPLOYEE_STATUS_CHOICES,
                    help_text="目标员工状态",
                ),
            },
        ),
    )
    @action(detail=True, methods=["post"])
    def change_status(self, request: "Request", pk: int | None = None) -> "Response":
        """更改员工状态(统一格式)"""
        employee = self.get_object()
        request_body = request.data
        new_status = request_body.get("status") if isinstance(request_body, dict) else None

        if not new_status:
            return error_response(message="请提供要更改的状态值")

        # 【AGENTS 规范 - P1-10】状态变更逻辑迁移到 EmployeeService.change_employee_status()
        employee = EmployeeService.change_employee_status(employee, new_status)

        serializer = EmployeeDetailSerializer(employee)
        return success_response(
            data={
                "message": f"员工状态已更改为: {dict(Employee.EMPLOYEE_STATUS_CHOICES)[new_status]}",
                "employee": serializer.data,
            }
        )

    # 【AGENTS 规范 - P3-44】启用 create() 方法,调用 EmployeeService.create_employee()
    # 实现工号唯一性校验,避免视图层直接 serializer.save() 跳过业务校验
    def create(self, request: "Request", *args: Any, **kwargs: Any) -> "Response":
        """
        创建员工

        【AGENTS 规范 - P3-44】通过 EmployeeService.create_employee() 创建,
        Service 层负责工号唯一性校验(抛出 ValidationError),
        视图层仅负责序列化验证和响应格式化。
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 【AGENTS 规范 - P3-44】调用 Service 层创建,包含工号唯一性校验
        employee = EmployeeService.create_employee(serializer.validated_data)

        return success_response(
            data=EmployeeDetailSerializer(employee).data,
            message="员工创建成功",
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="批量更新员工排序",
        # 请求体复用运行时 EmployeeBatchSortSerializer（不另立结构定义，DR-1）。
        # 必须显式声明 request：action 名是 `batch_sort`，该方法不在
        # get_serializer_class() 的分派表内，spectacular 会回退到
        # EmployeeSerializer（列表序列化器），产不出 items 包装层。
        #
        # 【BF-057 响应形状】本方法运行时直接返回 serializer.data 的裸数组
        # （success_response 包装），不经过 paginate_queryset，故 200 响应不是分页对象。
        #
        # 【为什么必须用 raw dict 而不是 EmployeeSerializer(many=True)】
        # 传序列化器实例时，drf-spectacular 的 :1486 会用 `_is_list_view(serializer)`
        # 判定——`many=True` 使其判 True，进而走 :1500 的分页包装分支，把裸数组
        # 重新包成 PaginatedEmployeeList（声明被覆盖）。传 raw dict 则命中
        # :1471-1475 的 `isinstance(serializer, dict)` 分支，该分支把 serializer
        # 置为 None，使 :1486 恒判 False，整条「数组+分页」推断分支一并跳过。
        # 副作用同样被跳过：补 many=True 会翻转 `_is_list_view()`，进而打开
        # get_filter_backends()，给本端点凭空加上 5 条运行时从不消费的筛选参数
        # （batch_sort 是 PUT，直接调 Selector，全程不跑 filter_queryset）——
        # 那正是 OS-5 双向红线所说的「文档超前于运行时」反向失真。
        #
        # 【耦合点】下方组件名与 EmployeeSerializer 绑定：若该序列化器的组件名变更
        # （ref_name / ENUM_NAME_OVERRIDES），此处是字面量、不会自动跟随，须同步修改。
        # 护栏：test_employee_openapi_contract.py::test_sort_response_is_bare_array
        responses={200: {"type": "array", "items": {"$ref": "#/components/schemas/Employee"}}},
        request=EmployeeBatchSortSerializer,
    )
    @action(detail=False, methods=["put"], url_path="sort")
    def batch_sort(self, request: "Request") -> "Response":
        """
        批量更新员工排序字段

        【AGENTS 规范 - P3-45】批量更新逻辑已迁移到 EmployeeSelector.batch_update_sort(),
        批量更新员工排序(前端传入列表,每个元素包含 employee_jobcode 和 sort_order)
        视图层仅负责调用 Selector 和返回成功响应。

        【修复】使用 EmployeeBatchSortSerializer 提供批量大小限制和重复校验
        """
        serializer = EmployeeBatchSortSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 【AGENTS 规范 - P3-45】调用 Selector 批量更新
        updated_employees = EmployeeSelector.batch_update_sort(serializer.validated_data["items"])
        # 返回更新后的员工数据
        response_serializer = self.get_serializer(updated_employees, many=True)
        return success_response(
            data=response_serializer.data, message="员工排序更新成功", status_code=status.HTTP_200_OK
        )
