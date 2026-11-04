"""OpenAPI 信封契约护栏（OP-09，批次 8）。

锚定面：
- 幽灵路由反向锁：dashboard/permissions 两 ViewSet 的标准 CRUD 幽灵路由经方案 A 清理
  （dashboard 5 条 404、permissions 3 条 405），其 operation 不得再出现在 schema。
- 信封全包：2xx JSON 响应必须为 {code,message,data} 信封或分页信封 $ref。
- D1：真实 destroy 运行时均为信封 200（core/mixins.py 及 15 处自定义覆盖实证），
  schema 不得残留 204 无 body。
- 反向：non_json（xlsx/png 等）与非信封名单不得被包裹（零新增失真）。
"""

from __future__ import annotations

from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

from core.envelope_schema import (
    ENVELOPE_NO_BODY_OPERATIONS,
    NON_ENVELOPE_OPERATIONS,
    OPERATION_METHODS,
    _schema_is_envelope,
)


PHANTOM_OPERATION_IDS = frozenset(
    {
        "v1_dashboard_list",
        "v1_dashboard_create",
        "v1_dashboard_retrieve",
        "v1_dashboard_update",
        "v1_dashboard_destroy",
        "v1_users_permissions_create",
        "v1_users_permissions_update",
        "v1_users_permissions_destroy",
    }
)


@pytest.fixture(scope="session")
def api_schema():
    """本地临时 fixture（OP-09 提交 1 先行使用）。

    T3.1 将统一上提至根 conftest.py（与 apps/usermanagement/tests/conftest.py 的
    session 级 fixture 同源合并），届时删除本定义避免重名。保持与该 conftest 一致
    的无注解形态（fixture 内 untyped 调用不进 strict 推断面，mypy no-untyped-call
    不会被触发；上提时跟随同源实现）。
    """
    return SchemaGenerator().get_schema(request=None, public=True)


def _operation_ids(schema: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for item in schema.get("paths", {}).values():
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete", "head", "options"} and isinstance(op, dict):
                ids.add(str(op.get("operationId", "")))
    return ids


def test_phantom_crud_routes_removed(api_schema: dict[str, Any]) -> None:
    ids = _operation_ids(api_schema)
    leaked = PHANTOM_OPERATION_IDS & ids
    assert not leaked, f"幽灵 CRUD 路由仍存在于 schema：{sorted(leaked)}"


def _iter_operations(schema: dict[str, Any]) -> Any:
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method in OPERATION_METHODS and isinstance(op, dict):
                yield method, op


def _components(schema: dict[str, Any]) -> dict[str, Any]:
    return (schema.get("components") or {}).get("schemas") or {}


def test_bare_2xx_json_enveloped(api_schema: dict[str, Any]) -> None:
    components = _components(api_schema)
    for method, op in _iter_operations(api_schema):
        oid = str(op.get("operationId", ""))
        if oid in NON_ENVELOPE_OPERATIONS or oid in ENVELOPE_NO_BODY_OPERATIONS:
            continue
        responses = op.get("responses", {})
        for code_str, response in responses.items():
            if not code_str.isdigit() or not 200 <= int(code_str) <= 299:
                continue
            content = response.get("content")
            if not content:
                continue
            media = content.get("application/json")
            if media is None:
                continue  # 非 JSON 媒体（如 qr-code image/png）不在信封覆盖面
            assert _schema_is_envelope(media.get("schema"), components), f"{oid} [{method}] {code_str} 响应未信封化"


def test_no_nested_envelope(api_schema: dict[str, Any]) -> None:
    for method, op in _iter_operations(api_schema):
        oid = str(op.get("operationId", ""))
        for code_str, response in (op.get("responses", {})).items():
            if not code_str.isdigit() or not 200 <= int(code_str) <= 299:
                continue
            content = response.get("content") or {}
            media = content.get("application/json") or {}
            schema = media.get("schema") or {}
            props = (schema.get("properties") or {}).get("data") or {}
            inner = props.get("properties") or {}
            assert not ("code" in inner and "message" in inner), f"{oid} [{method}] {code_str} 信封内嵌信封（二次包裹）"


def test_non_json_operations_untouched(api_schema: dict[str, Any]) -> None:
    by_oid = {str(op.get("operationId", "")): op for _, op in _iter_operations(api_schema)}
    for oid in NON_ENVELOPE_OPERATIONS:
        assert oid in by_oid, f"NON_ENVELOPE 名单端点 {oid} 不在 schema"
        op = by_oid[oid]
        for code_str, response in op.get("responses", {}).items():
            if not code_str.isdigit() or not 200 <= int(code_str) <= 299:
                continue
            content = response.get("content") or {}
            assert "application/json" not in content, f"{oid} 名单端点出现 JSON 响应（名单失准）"
            media_schema = None
            for media in content.values():
                if isinstance(media, dict):
                    media_schema = media.get("schema")
                    break
            assert not _schema_is_envelope(media_schema, _components(api_schema)), (
                f"{oid} 非信封名单端点被包裹"
            )


def test_no_body_operations_preserved(api_schema: dict[str, Any]) -> None:
    by_oid = {str(op.get("operationId", "")): op for _, op in _iter_operations(api_schema)}
    for oid in ENVELOPE_NO_BODY_OPERATIONS:
        assert oid in by_oid, f"ENVELOPE_NO_BODY 名单端点 {oid} 不在 schema"
        op = by_oid[oid]
        responses = op.get("responses", {})
        two_xx = {
            code: resp for code, resp in responses.items() if str(code).isdigit() and 200 <= int(str(code)) <= 299
        }
        assert all(not resp.get("content") for resp in two_xx.values()), (
            f"{oid} no-body 名单端点出现响应体（ upkeep 名单失准）"
        )


def test_real_destroy_d1_enveloped(api_schema: dict[str, Any]) -> None:
    """D1：除幽灵外的 DELETE 端点运行时均为信封 200（mixins/自定义覆盖实证）。"""
    components = _components(api_schema)
    destroy_ids: set[str] = set()
    for method, op in _iter_operations(api_schema):
        oid = str(op.get("operationId", ""))
        if method != "delete":
            continue
        responses = op.get("responses", {})
        assert "204" not in responses, f"{oid} 仍残留 204 无 body（D1 收编未达）"
        response = responses.get("200") or {}
        media = (response.get("content") or {}).get("application/json") or {}
        assert _schema_is_envelope(media.get("schema"), components), f"{oid} DELETE 200 响应未信封化"
        destroy_ids.add(oid)
    assert len(destroy_ids) >= 19, f"DELETE 信封端点数异常：{len(destroy_ids)}"


def test_x_envelope_marker_single_point(api_schema: dict[str, Any]) -> None:
    """x-envelope 仅由 envelope_response（信封 builder 单点）写入，非名单端点之外不应悬浮。"""
    ext_values: list[Any] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "x-envelope":
                    ext_values.append(value)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(api_schema)
    assert ext_values and all(v is True for v in ext_values), "x-envelope 出现真值之外的标记形态"


def test_operation_lists_counts(api_schema: dict[str, Any]) -> None:
    by_oid = {str(op.get("operationId", "")) for _, op in _iter_operations(api_schema)}
    assert len(NON_ENVELOPE_OPERATIONS) == 15
    assert len(ENVELOPE_NO_BODY_OPERATIONS) == 21
    assert len(by_oid) == 265
    assert NON_ENVELOPE_OPERATIONS & ENVELOPE_NO_BODY_OPERATIONS == set()
    assert PHANTOM_OPERATION_IDS & by_oid == set()
