"""
资产分组查询选择器

提供资产台账「分组展开表格」的分组聚合查询（汇总端点）。

分组键四元组 `[contract_code|null, asset_name, asset_specification|null, asset_brand|null]`
的字段路径在本模块仅此一处定义（`GROUP_KEY_FIELDS`），`GROUP_KEY_PATHS` 与 null 允许性
均由它派生；`group_key` 的 `json.loads` 解析（`parse_group_key`）同样只此一处，
不存在第二套组键语义（DR-1）。

RBAC 复用 `AssetSelector.apply_user_scope`（全项目唯一实现），不旁路、不新写部门过滤。

筛选链同样全部复用平铺端点的既有实现：精确走 `_apply_exact_filters`、模糊走 `_build_fuzzy_q`
（DR-3），故分组筛选与主列表筛选对同一输入必然给出同一命中集。本模块只负责**键集声明**
（`SUMMARY_FILTER_PATHS` 及其精确/模糊拆分）与分流，不实现任何字段映射。
"""

import json
from collections.abc import Iterable
from typing import Any, cast

from django.db.models import Count, F, Max, Min, Q, QuerySet

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors.asset_selector import (
    AssetSelector,
    _apply_exact_filters,
    _build_fuzzy_q,
)
from core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


CONTRACT_CODE_PATH = "asset_contract_recordcode__contract_code"

# 组键四元组 **(API 名, ORM 字段路径, 是否允许 null)** —— 分组键语义的**唯一声明**（DR-1）。
# 数组顺序即 `group_key` JSON 顺序；`GROUP_KEY_PATHS` 与 null 允许性均由本表派生，勿单独维护。
# null 允许性依据 `models/asset.py`：`asset_name`(:113) 非空，
# `asset_specification` / `asset_brand`(:121-126) 与合同 FK(:135-141) 均 null=True。
GROUP_KEY_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("contract_code", CONTRACT_CODE_PATH, True),
    ("asset_name", "asset_name", False),
    ("asset_specification", "asset_specification", True),
    ("asset_brand", "asset_brand", True),
)

# 分组键顺序 = group_key JSON 数组顺序（派生自 GROUP_KEY_FIELDS）
GROUP_KEY_PATHS: tuple[str, ...] = tuple(path for _label, path, _nullable in GROUP_KEY_FIELDS)

# 汇总端点**精确**筛选 query 键 -> 查询字段路径（B3）
SUMMARY_EXACT_FILTER_PATHS: dict[str, str] = {
    "asset_current_status": "asset_current_status",
    "asset_type_recordcode": "asset_type_recordcode",
    "asset_storage_recordcode": "asset_storage_recordcode",
    "contract_code": CONTRACT_CODE_PATH,
}

# `asset_type_category` 走精确链，但它的值不是字段路径而是 `AssetType.type_code`：
# `_apply_exact_filters` 会 pop 该键并展开为 `asset_type_recordcode__in`
# （分类下无类型时返回空集而非全表，见 asset_selector.py:56-68）。
# 故映射值仅作占位，真正生效的字段路径由 `_apply_exact_filters` 内部改写。
CATEGORY_FILTER_KEY = "asset_type_category"

# 汇总端点**模糊**筛选键（C 新增 5 个）。值原样交给 `_build_fuzzy_q`，**刻意不写映射表**：
# 该函数的 `FIELD_NAME_MAPPING`（asset_selector.py:16-21）已是全项目唯一的模糊字段映射实现，
# 此处再写一份即构成 DR-1 违规，且两份表必然漂移 —— 改一处忘另一处会让筛选静默打到别的字段上。
# 契约改为：这些键必须**原样**是 `_build_fuzzy_q` 认识的键（同名 Asset 字段，或其映射表内的别名）。
# 该契约由测试 `test_fuzzy_filter_keys_resolvable_by_shared_mapper` 钉住。
SUMMARY_FUZZY_FILTER_KEYS: tuple[str, ...] = (
    "asset_code",
    "asset_name",
    "asset_brand",
    "asset_specification",
    "asset_contract_name",
)

# 汇总端点全部筛选键的并集 —— 键集的**唯一清单**，供两个 Serializer / 两个 View / 测试三处对齐。
# 模糊键在此以恒等映射登记（`key -> key`），仅为让本表保持「键 -> 路径」的同构形状；
# 模糊链的真实路径解析权归 `_build_fuzzy_q`（见上）。
SUMMARY_FILTER_PATHS: dict[str, str] = {
    **SUMMARY_EXACT_FILTER_PATHS,
    CATEGORY_FILTER_KEY: CATEGORY_FILTER_KEY,
    **{key: key for key in SUMMARY_FUZZY_FILTER_KEYS},
}

# 明细端点（B4）可透传的非组键筛选 = 汇总筛选去掉 contract_code（合同已在 group_key 内表达）
PASS_THROUGH_FILTER_PATHS: dict[str, str] = {
    key: path for key, path in SUMMARY_FILTER_PATHS.items() if key != "contract_code"
}


NO_CONTRACT_KEY = "no_contract"


class GroupKeyError(ValueError):
    """`group_key` 非法（由 View 层转 400）"""


def parse_group_key(raw: str) -> tuple[Any, ...]:
    """`group_key` JSON 字符串 -> 组键四元组（解码侧唯一实现，DR-1）

    与 B5 编码侧 `json.dumps([contract_code, asset_name, asset_specification, asset_brand])`
    的数组顺序严格对应（均由 `GROUP_KEY_FIELDS` 派生）。

    **为什么必须是 JSON 数组而不是分隔符拼接（R-1）**：null 在 query param 中不可表达，
    且品牌/型号含 `,` `~` `"` 是合法的 —— 分隔符方案会静默错切或撞值。JSON 数组往返无损。

    抛 `GroupKeyError` 而非静默容错：非法 group_key 若被当作「不过滤」，
    会退化成返回整个筛选集（明细数远大于汇总数），错答方向是「多给数据」，比 400 危险。
    """
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GroupKeyError("group_key 不是合法 JSON 字符串") from exc
    if not isinstance(decoded, list):
        raise GroupKeyError(f"group_key 必须是 JSON 数组，收到 {type(decoded).__name__}")
    if len(decoded) != len(GROUP_KEY_FIELDS):
        raise GroupKeyError(f"group_key 必须是长度 {len(GROUP_KEY_FIELDS)} 的 JSON 数组，收到 {len(decoded)} 项")

    for index, (value, (label, _path, nullable)) in enumerate(zip(decoded, GROUP_KEY_FIELDS, strict=True)):
        if value is None and nullable:
            continue
        expected = "字符串或 null" if nullable else "字符串（不允许 null）"
        if not isinstance(value, str):
            raise GroupKeyError(f"group_key 第 {index} 项（{label}）必须是{expected}，收到 {type(value).__name__}")
    return tuple(decoded)


def _resolve_no_contract(filters: dict[str, Any]) -> bool:
    """归一化后的 `no_contract` 取值（唯一布尔判定点，DR-1）

    本函数**只认真 bool**，不解析查询字符串。理由：查询串的字面量词表只有一个权威来源
    —— `AssetGroupQuerySerializer` 的 DRF `BooleanField`（接受 true/t/yes/y/on/1 及其否向
    对应项，且对无法识别的值抛 400 响亮失败）。若在此处再写一份字符串词表，就会出现第二套
    真值语义（DR-1 禁止），且两者必然漂移：经 HTTP 时 `no_contract=yes` 会被本函数静默当作
    「未传」而**多返回数据**——静默错答比 400 更危险。

    生产链路上该值恒为 bool：view 的 `_parse_filters` 只输出 `validated_data`，而
    `no_contract` 声明了 `default=False`，DRF 对缺省字段填 `get_default()`，故键必存在且为 bool。
    """
    raw = filters.get(NO_CONTRACT_KEY)
    if raw is None:  # 键缺省 = 不筛选（`list_group_summaries` 的 `filters` 默认空字典）
        return False
    if not isinstance(raw, bool):
        raise TypeError(
            f"{NO_CONTRACT_KEY} 必须是已归一化的 bool，收到 {type(raw).__name__}；"
            "字符串解析是 Serializer 的职责（AssetGroupQuerySerializer），Selector 不解析"
        )
    return raw


def _apply_summary_filters(queryset: QuerySet[Asset], filters: dict[str, Any]) -> QuerySet[Asset]:
    """叠加汇总端点全部筛选（B3 精确四键 + C 新增 6 键）

    复用既有 `_apply_exact_filters`（asset_selector.py:38）与 `_build_fuzzy_q`
    （asset_selector.py:16）而非自写过滤链（DR-3）—— 分类展开、类型双尝试、模糊字段映射
    三处口径全部沿用主列表端点，故分组筛选与平铺筛选对同一输入给出同一命中集。

    ⚠️ `_apply_exact_filters` 会 pop 入参，故两个中间字典均为就地构造的新字典，
    `filters` 本体不被修改，调用方（如 `build_children_queryset`）可继续复用。

    ⚠️ `filters` 的值必须是**已归一化**的 Python 类型（bool / str），查询串字面量不得直接传入：
    归一化唯一入口是 `AssetGroupQuerySerializer` / `AssetGroupChildrenQuerySerializer`。
    违规的 `no_contract` 值由 `_resolve_no_contract` 抛 `TypeError`。
    """
    queryset = _apply_exact_filters(queryset, _exact_filter_args(filters))
    fuzzy_q = _build_fuzzy_q(_fuzzy_filter_args(filters))
    if fuzzy_q is not None:
        queryset = queryset.filter(fuzzy_q)
    if _resolve_no_contract(filters):
        queryset = queryset.filter(**{f"{CONTRACT_CODE_PATH}__isnull": True})
    return queryset


def _exact_filter_args(filters: dict[str, Any]) -> dict[str, Any]:
    """精确链入参：四个精确键 + 分类键（后者需保留 API 名供 `_apply_exact_filters` pop）

    空串与 `None` 视为未传（口径同 B3），避免 `?asset_brand=` 把整表过滤成空集。
    """
    args = {
        path: filters[key] for key, path in SUMMARY_EXACT_FILTER_PATHS.items() if filters.get(key) not in (None, "")
    }
    category = filters.get(CATEGORY_FILTER_KEY)
    if category not in (None, ""):
        # 键名而非路径：`_apply_exact_filters` 按 API 名 pop 后改写为 `asset_type_recordcode__in`
        args[CATEGORY_FILTER_KEY] = category
    return args


def _fuzzy_filter_args(filters: dict[str, Any]) -> dict[str, str]:
    """模糊链入参：键集 = `SUMMARY_FUZZY_FILTER_KEYS`，值为 str 且已归一化

    值在此**不做任何映射**（键即 `_build_fuzzy_q` 的键），映射由该函数内的
    `FIELD_NAME_MAPPING` 唯一负责（DR-1）。
    """
    return {key: filters[key] for key in SUMMARY_FUZZY_FILTER_KEYS if filters.get(key) not in (None, "")}


def _scoped_queryset(*, user: Any, filters: dict[str, Any], base: QuerySet[Asset] | None = None) -> QuerySet[Asset]:
    """筛选 + RBAC 行级隔离后的未聚合资产集

    `build_summary_queryset` 与 `attach_asset_codes`（及 B4 的 `build_children_queryset`）
    的唯一基集来源（DR-1），保证三者作用于完全同一批资产 ——
    这是契约不变量 I-1（明细数 ≡ 汇总数）的前提。

    `base` 供明细端点传入带预加载的查询集（`AssetDetailSerializer` 需要 `select_related`）；
    筛选与权限仍只在此施加一次，避免「汇总一套、明细一套」的漂移。
    构造 QuerySet 不产生 SQL，故被分别调用无查询代价。
    """
    queryset = _apply_summary_filters(Asset.objects.all() if base is None else base, filters)
    return AssetSelector.apply_user_scope(queryset, user)


def _row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """聚合行 -> 组键四元组"""
    return tuple(row[path] for path in GROUP_KEY_PATHS)


def _build_group_q(group_values: Iterable[Any]) -> Q:
    """组键四元组 -> null-safe 精确 Q（R-1 落点）

    `None` 必须走 `__isnull=True`：`=None` 在 SQL 中永不命中，会静默返回空集。
    """
    q = Q()
    for path, value in zip(GROUP_KEY_PATHS, group_values, strict=True):
        if value is None:
            q &= Q(**{f"{path}__isnull": True})
        else:
            q &= Q(**{path: value})
    return q


def _aggregate_rows(queryset: QuerySet[Asset]) -> QuerySet[Any]:
    """分组聚合并按决策 13 排序

    合同 nulls-last 用 `F(path).asc(nulls_last=True)` 在 SQL 侧完成（Django 4.1+）,
    排序也留在 SQL 侧, 以便分页由数据库 LIMIT/OFFSET 承担（不在 Python 侧二次排序, 避免两套排序实现）。

    注: 不可用 `F(f"{path}__isnull")` —— F() 表达式不解析 lookup, Django 会把 `isnull`
    当作 Contract 的字段名去找并抛 FieldError。
    """
    return cast(
        "QuerySet[Any]",
        queryset.values(*GROUP_KEY_PATHS)
        .annotate(
            asset_count=Count("id"),
            price_min=Min("asset_purchase_price"),
            price_max=Max("asset_purchase_price"),
        )
        .order_by("-asset_count", F(CONTRACT_CODE_PATH).asc(nulls_last=True), *GROUP_KEY_PATHS),
    )


def _attach_asset_codes(queryset: QuerySet[Asset], rows: list[dict[str, Any]]) -> None:
    """就地补当前页各组的 asset_codes（第二次窄查询）

    以 `Q(pk__in=[])` 作 OR 种子（恒假），保证 rows 为空时不产生全表查询。
    """
    if not rows:
        return
    scope: Q = Q(pk__in=[])
    for row in rows:
        scope |= _build_group_q(_row_key(row))
    buckets: dict[tuple[Any, ...], list[str]] = {}
    pairs = queryset.filter(scope).values_list(*GROUP_KEY_PATHS, "asset_code").order_by()
    for values in pairs:
        *head, code = values
        buckets.setdefault(tuple(head), []).append(code)
    for row in rows:
        row["asset_codes"] = buckets.get(_row_key(row), [])


class AssetGroupedSelector:
    """资产分组聚合查询选择器"""

    @staticmethod
    def build_summary_queryset(*, user: Any, filters: dict[str, Any] | None = None) -> QuerySet[Any]:
        """返回**未切片**的分组聚合 QuerySet，交给 DRF 分页器做 count + LIMIT/OFFSET

        刻意不在此层分页：分页必须在 `asset_codes` 补齐之前发生，否则要把每组明细
        全量载入内存。视图侧顺序为
        `paginate_queryset` → `_post_paginate_hook`(补 asset_codes) → 序列化。
        """
        return _aggregate_rows(_scoped_queryset(user=user, filters=filters or {}))

    @staticmethod
    def attach_asset_codes(*, user: Any, filters: dict[str, Any] | None, rows: list[dict[str, Any]]) -> None:
        """就地补给定汇总行（通常是已切页的当页行）的 asset_codes

        与 `build_summary_queryset` 复用同一 `_scoped_queryset`，故补出的编码
        必然落在该页所属的筛选与权限范围内。
        """
        _attach_asset_codes(_scoped_queryset(user=user, filters=filters or {}), rows)

    @staticmethod
    def list_group_summaries(
        *,
        user: Any,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[int, list[dict[str, Any]]]:
        """返回 (分组总数, 当前页汇总行)

        行字段 = 4 个分组键路径 + asset_count + price_min + price_max + asset_codes。
        `group_key` 与 `price_display` 由 B5 序列化器生成，本层不重复实现（DR-1）。

        面向测试与非 DRF 调用方；DRF 端点走
        `build_summary_queryset` + `attach_asset_codes` 两段式，以复用分页器。
        """
        size = min(max(page_size, 1), MAX_PAGE_SIZE)
        current = max(page, 1)
        base = _scoped_queryset(user=user, filters=filters or {})
        rows_qs = _aggregate_rows(base)
        total = rows_qs.count()
        rows = list(rows_qs[(current - 1) * size : current * size])
        _attach_asset_codes(base, rows)
        return total, rows

    @staticmethod
    def build_children_queryset(*, user: Any, group_key: str, filters: dict[str, Any] | None = None) -> QuerySet[Asset]:
        """返回指定组的**未切片**明细资产 QuerySet，交给 DRF 分页器做 count + LIMIT/OFFSET

        B4 明细端点。**契约不变量 I-1 的实现落点**：与汇总端点复用同一个
        `_scoped_queryset`（同筛选集、同权限范围）再 AND 同一个 `_build_group_q`，
        故 `count` 必然 === 对应组的 `asset_count`。

        `filters` 只应含 `PASS_THROUGH_FILTER_PATHS` 的非组键筛选；
        若调用方误传 `contract_code` / `no_contract`，它们仍会经 `_apply_summary_filters`
        生效并与 `group_key` 做交集 —— 两者矛盾时结果为空集而非错答，故本层不做剔除，
        改由 `AssetGroupChildrenQuerySerializer` 不声明这两个参数来杜绝（DR-3）。
        """
        values = parse_group_key(group_key)
        queryset = _scoped_queryset(
            user=user,
            filters=filters or {},
            base=AssetSelector.get_assets_with_all_relations(),
        )
        # 组内合同/名称/规格/品牌同质（GROUP_KEY_FIELDS 派生的四元组即分组键）。
        # asset_code 在查询范围内唯一（unique_asset_code_not_deleted，condition is_deleted=False，
        # 且 SoftDeleteManager 默认排除软删行），作组内分页的稳定排序键：
        # 无稳定序时 LIMIT/OFFSET 翻页会重复或漏掉行（组内翻页必然发生，故必须显式排序）。
        # 业务有序（编码升序）替代无业务序的 recordcode（UUID 派生），BF-082 需求 1。
        return queryset.filter(_build_group_q(values)).order_by("asset_code")
