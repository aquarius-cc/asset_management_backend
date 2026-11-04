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

from typing import Any, cast

import pytest
from drf_spectacular.generators import SchemaGenerator

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
def api_schema() -> dict[str, Any]:
    """本地临时 fixture（OP-09 提交 1 先行使用）。

    T3.1 将统一上提至根 conftest.py（与 apps/usermanagement/tests/conftest.py 的
    session 级 fixture 同源合并），届时删除本定义避免重名。
    """
    return cast("dict[str, Any]", SchemaGenerator().get_schema(request=None, public=True))


def _operation_ids(schema: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for item in schema.get("paths", {}).values():
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete", "head", "options"} and isinstance(
                op, dict
            ):
                ids.add(str(op.get("operationId", "")))
    return ids


def test_phantom_crud_routes_removed(api_schema: dict[str, Any]) -> None:
    ids = _operation_ids(api_schema)
    leaked = PHANTOM_OPERATION_IDS & ids
    assert not leaked, f"幽灵 CRUD 路由仍存在于 schema：{sorted(leaked)}"

