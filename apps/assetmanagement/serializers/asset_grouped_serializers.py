"""
资产分组汇总序列化器

输入是 `AssetGroupedSelector` 的分组聚合行（dict），**不是模型实例**，
故用普通 `Serializer` 而非 `ModelSerializer`。

字段口径与 `Project_Requirements/02-技术设计/04-API接口规范.md` §2.4b.1 保持一致：
本模块输出「分组键 4 项 + 数量 + 价格展示 + 编码 + `group_key`」，共 8 个字段。

`price_min` / `price_max` **刻意不出现在响应里**（B5）：`price_display` 由
`SerializerMethodField` 从聚合行直读派生，避免同一组价格出现「原始区间」与
「展示串」两种表达，让前端无法判断该以哪个为准。

⚠️ **`group_key` 的编码侧（B5）在此，解码侧（B4）在 Selector 的 `parse_group_key`**，
二者共用 `GROUP_KEY_PATHS` 的数组顺序 —— 顺序只有一处定义（`GROUP_KEY_FIELDS` 派生），
漂移会让往返静默错位（编码 [A,B,C,D] 解码成 [A,C,B,D] 仍能通过形状校验但过滤错组）。
"""

import json
from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.assetmanagement.selectors.asset_grouped_selector import (
    CONTRACT_CODE_PATH,
    GROUP_KEY_PATHS,
)


def format_price(low: Decimal | None, high: Decimal | None) -> str:
    """聚合价格区间 -> 展示串（`price_display` 唯一实现，DR-1）

    `min == max` -> `"4500.00"`；否则 `"4500.00~5000.00"`（`~` 分隔，两位小数，升序）。

    两位小数用 `:.2f` 而非 `str(Decimal)`：`decimal_places=2` 只约束**存储**精度，
    聚合表达式（`Min`/`Max`）的返回精度取决于 DB，若某天换库返回 `Decimal("4500")`，
    `str()` 会输出 `"4500"` 而契约要求 `"4500.00"`。`:.2f` 对 Decimal/float 均适用且显式。

    `None`（理论上不可达：`asset_purchase_price` 是 NOT NULL 列，且分组恒非空）
    仍返回空串而非抛错 —— 格式化异常会变成 500，比空值更难排查。
    """
    if low is None or high is None:
        return ""
    low_text = f"{low:.2f}"
    return low_text if low == high else f"{low_text}~{high:.2f}"


class AssetGroupSummarySerializer(serializers.Serializer):  # type: ignore[type-arg]
    """单个分组汇总行

    字段声明顺序 = 04 §2.4b.1 示例顺序（`group_key` 打头）。JSON 键序无语义意义，
    但与契约示例一致可让抓包比对与文档走查更直观。
    """

    group_key = serializers.SerializerMethodField()
    contract_code = serializers.CharField(source=CONTRACT_CODE_PATH, read_only=True, allow_null=True)
    asset_name = serializers.CharField(read_only=True)
    asset_specification = serializers.CharField(read_only=True, allow_null=True)
    asset_brand = serializers.CharField(read_only=True, allow_null=True)
    asset_count = serializers.IntegerField(read_only=True)
    price_display = serializers.SerializerMethodField()
    asset_codes = serializers.ListField(child=serializers.CharField(), read_only=True)

    def get_group_key(self, row: dict[str, Any]) -> str:
        """四元组 -> JSON 数组字符串（编码侧唯一实现）

        顺序直接取 `GROUP_KEY_PATHS`（B1 派生自 `GROUP_KEY_FIELDS` 的唯一顺序声明），
        故与 B4 解码侧不可能错位 —— 两处若各写一份字面量数组，漂移将静默发生。

        `ensure_ascii=False`：契约示例中中文为原文（`"笔记本电脑"`）而非 `\\uXXXX`。
        两种写法都能被 `json.loads` 解析，但保持与契约一致可避免前端日志/缓存键出现转义串。
        """
        return json.dumps([row[path] for path in GROUP_KEY_PATHS], ensure_ascii=False)

    def get_price_display(self, row: dict[str, Any]) -> str:
        """由聚合行的 `price_min` / `price_max` 派生展示串"""
        return format_price(row.get("price_min"), row.get("price_max"))


class AssetGroupQuerySerializer(serializers.Serializer):  # type: ignore[type-arg]
    """汇总端点 query 参数校验

    仅校验形状与取值合法性，不做业务过滤 —— 过滤统一在 Selector 层（DR-3）。
    `no_contract` 与 `contract_code` 互斥：无合同哨兵组与指定合同组不可能同时成立，
    同传属客户端自相矛盾，直接 400 而非静默取其一。

    C 批新增 5 个模糊键 + 1 个分类键，与 `AssetGroupChildrenQuerySerializer` **完全一致**。
    键集一致性由 `test_pass_through_filters_match_summary_endpoint` 钉住；此处刻意逐字声明
    而非从 `SUMMARY_FILTER_PATHS` 动态注入（理由同 `AssetGroupChildrenQuerySerializer`）。
    """

    asset_current_status = serializers.CharField(required=False, allow_blank=True)
    asset_type_recordcode = serializers.CharField(required=False, allow_blank=True)
    asset_storage_recordcode = serializers.CharField(required=False, allow_blank=True)
    contract_code = serializers.CharField(required=False, allow_blank=True)
    no_contract = serializers.BooleanField(required=False, default=False)
    # --- C 批新增 6 键：模糊 5 + 分类 1（Selector 的 SUMMARY_FUZZY_FILTER_KEYS / CATEGORY_FILTER_KEY）---
    asset_code = serializers.CharField(required=False, allow_blank=True)
    asset_name = serializers.CharField(required=False, allow_blank=True)
    asset_brand = serializers.CharField(required=False, allow_blank=True)
    asset_specification = serializers.CharField(required=False, allow_blank=True)
    asset_contract_name = serializers.CharField(required=False, allow_blank=True)
    asset_type_category = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """拒绝 no_contract 与 contract_code 同传"""
        if attrs.get("no_contract") and attrs.get("contract_code"):
            raise serializers.ValidationError("no_contract 与 contract_code 不能同时传参")
        return attrs


class AssetGroupChildrenQuerySerializer(serializers.Serializer):  # type: ignore[type-arg]
    """明细端点 query 参数校验（B4）

    只接受 `group_key` 与**非组键**筛选。**刻意不声明** `contract_code` / `no_contract`
    —— R-1 已取消这两个参数：合同由 `group_key` 首元素表达，null 亦无损；
    保留它们会引入第二个合同口径，前端一旦误传即与 `group_key` 矛盾。

    非组键筛选必须与汇总端点**完全一致**且由前端原样透传，否则汇总数与明细数漂移（I-1）。
    键集一致性由 `test_pass_through_filters_match_summary_endpoint` 钉住 —— 这里刻意
    逐字声明而非从 `PASS_THROUGH_FILTER_PATHS` 动态注入：动态字段会让 OpenAPI 与 mypy
    失去静态可见性，而「声明式 schema」本不构成 DR-1 意义上的业务规则重复
    （真正的业务规则 —— 键到字段路径的映射 —— 唯一实现在 Selector 的
    `PASS_THROUGH_FILTER_PATHS`，见 `asset_grouped_selector.py`）。
    """

    group_key = serializers.CharField()
    asset_current_status = serializers.CharField(required=False, allow_blank=True)
    asset_type_recordcode = serializers.CharField(required=False, allow_blank=True)
    asset_storage_recordcode = serializers.CharField(required=False, allow_blank=True)
    # --- C 批新增 6 键：与汇总端点逐字一致（顺序亦同，键集断言不依赖顺序但可读性依赖）---
    asset_code = serializers.CharField(required=False, allow_blank=True)
    asset_name = serializers.CharField(required=False, allow_blank=True)
    asset_brand = serializers.CharField(required=False, allow_blank=True)
    asset_specification = serializers.CharField(required=False, allow_blank=True)
    asset_contract_name = serializers.CharField(required=False, allow_blank=True)
    asset_type_category = serializers.CharField(required=False, allow_blank=True)
