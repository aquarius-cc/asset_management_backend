"""OP-09 OpenAPI 信封全包后处理器（提交 2 · 方案 A）。

目标（量化四零）：
1) 2xx JSON 裸响应（无 {code,message,data} 信封）= 0
2) 二次信封（信封内再嵌信封/套娃）= 0
3) 非 JSON 响应（xlsx/png 等）被信封包裹 = 0
4) 名单外 2xx 无 body 被臆造性包裹 = 0（no-body 名单保持原状，P1 认证五案/P2 运行时批次另行显式收编）

机制：
- 以 SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"] 单点接线本模块 envelope_postprocessor。
- 判别谓词 _is_envelope：x-envelope 扩展标记（信封 builder 单点写入）或顶层
  code+message 属性或（解析 $ref 后仍成立）。分页信封 Paginated* 组件本体已是信封形态
  （core/pagination.py get_paginated_response_schema 生成），共用同一谓词。
- 真实 destroy（27 个幽灵路由清理后的 DELETE 端点，运行时信封 200）：
  schema 204 无 body → 200 + 信封 data=null（core/mixins.py destroy 及 15 处自定义覆盖实证）。
- 非 JSON 名单 / no-body 名单端点整体跳过（零新增失真；维持既有 204/媒体形态）。
"""

from __future__ import annotations

import re
from typing import Any


ENVELOPE_EXT_NAME = "x-envelope"
_JSON_REF = re.compile(r"^#/components/schemas/")
_COMPONENT_NAME = re.compile(r"^#/components/schemas/(?P<name>.+)$")

# NON_JSON 端点（OP-09 阶段 0 机械分类实测 15 条）：响应媒体为 xlsx/png 等，
# 信封谓词对 application/json 生效，这些端点根本不走 JSON 信封；名单显式防呆，
# 阻止未来形态漂移把它们误判包裹。
NON_ENVELOPE_OPERATIONS = frozenset(
    {
        "v1_assets_assets_export_retrieve",
        "v1_assets_broken_assets_export_retrieve",
        "v1_assets_contracts_export_retrieve",
        "v1_assets_damaged_assets_export_retrieve",
        "v1_assets_found_assets_export_retrieve",
        "v1_assets_harddisk_sn_export_retrieve",
        "v1_assets_lost_assets_export_retrieve",
        "v1_assets_operation_logs_export_retrieve",
        "v1_assets_out_assets_export_retrieve",
        "v1_assets_recycle_assets_export_retrieve",
        "v1_assets_repair_assets_export_retrieve",
        "v1_assets_waste_assets_export_retrieve",
        "v1_audit_logs_export_retrieve",
        "v1_unregisteredassets_unregistered_assets_export_retrieve",
        "v1_users_employees_export_retrieve",
    }
)

# NO_BODY 端点（OP-09 阶段 0 实测 21 条非 DELETE 无 body 2xx）：运行时未定态
# （auth 五案待 P1 显式收编；notifications/department/role 等待 P2 运行时批次逐个
# 直证后显式 schema 化）。本批次原则为零新增失真：一律跳过，不臆造 body，不包信封。
ENVELOPE_NO_BODY_OPERATIONS = frozenset(
    {
        "v1_assets_public_scan_retrieve",
        "repair_asset_batch_delete",
        "auth_login",
        "auth_logout",
        "my_permissions",
        "auth_register",
        "v1_auth_token_refresh_create",
        "v1_auth_token_verify_create",
        "v1_notifications_retrieve",
        "v1_notifications_read_all_create",
        "v1_notifications_unread_count_retrieve",
        "v1_notifications_read_create",
        "department_batch_sort",
        "department_tree",
        "department_children",
        "department_descendants",
        "department_employees_list",
        "department_move",
        "department_path",
        "role_permissions",
        "role_permissions_2",
    }
)

# 幽灵路由清理（提交 1）后按 protect-fallback 语境保留的原幽灵 ID 集合，
# 仅用于护栏断言（其 operation 不得出现在 schema），不参与信封逻辑。
OPERATION_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


def envelope_response(data_schema: dict[str, Any] | None) -> dict[str, Any]:
    """构造单点信封 schema；data_schema 为空时 data 置 nullable object（真实 destroy 200 体）。"""
    data: dict[str, Any]
    if data_schema is None:
        data = {"type": "object", "nullable": True}
    else:
        data = data_schema
    return {
        "type": "object",
        "properties": {
            "code": {"type": "integer", "example": 0},
            "message": {"type": "string", "example": "查询成功"},
            "data": data,
        },
        ENVELOPE_EXT_NAME: True,
    }


def _resolve_ref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any] | None:
    ref = schema.get("$ref", "")
    match = _COMPONENT_NAME.match(ref)
    if not match:
        return None
    target: Any = components.get(match.group("name"))
    return target if isinstance(target, dict) else None


def _schema_is_envelope(schema: Any, components: dict[str, Any], depth: int = 0) -> bool:
    """信封判定：x-envelope 标记 / 顶层 code+message 属性 / 可解析 $ref 逐层判定（限深防套娃循环）。"""
    if depth > 3:
        return False
    if not isinstance(schema, dict):
        return False
    if schema.get(ENVELOPE_EXT_NAME) is True:
        return True
    properties = schema.get("properties")
    if isinstance(properties, dict) and "code" in properties and "message" in properties:
        return True
    ref_target = _resolve_ref(schema, components) if schema.get("$ref") else None
    if ref_target is not None:
        return _schema_is_envelope(ref_target, components, depth + 1)
    return False


def _operation_pairs(paths: dict[str, Any]) -> Any:
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method in OPERATION_METHODS and isinstance(operation, dict):
                operation_id = str(operation.get("operationId", ""))
                yield operation_id, operation


def _response_codes_of(operation: dict[str, Any]) -> Any:
    for code, response in list(operation.get("responses", {}).items()):
        if not isinstance(response, dict):
            continue
        code_str = str(code)
        if code_str.isdigit() and 200 <= int(code_str) <= 299:
            yield code_str, response


def envelope_postprocessor(result: dict[str, Any], generator: Any, request: Any, public: bool) -> dict[str, Any]:
    """drf-spectacular POSTPROCESSING_HOOKS 接口（签名固定四参）。"""
    components: dict[str, Any] = (result.get("components") or {}).get("schemas") or {}
    paths: dict[str, Any] = result.get("paths", {})
    for operation_id, operation in _operation_pairs(paths):
        if operation_id in NON_ENVELOPE_OPERATIONS or operation_id in ENVELOPE_NO_BODY_OPERATIONS:
            continue
        responses = operation.setdefault("responses", {})
        for code_str, response in _response_codes_of(operation):
            content = response.get("content")
            media = content.get("application/json") if isinstance(content, dict) else None
            schema = media.get("schema") if isinstance(media, dict) else None
            if code_str == "204" and not content:
                # 真实 destroy：运行时信封 200（mixins.destroy / 15 处自定义覆盖）。
                responses.pop(code_str, None)
                responses["200"] = {
                    "description": "删除成功",
                    "content": {"application/json": {"schema": envelope_response(None)}},
                }
                continue
            if (
                code_str in ("200", "201")
                and media is not None
                and schema is not None
                and not _schema_is_envelope(schema, components)
            ):
                media["schema"] = envelope_response(schema)
    return result
