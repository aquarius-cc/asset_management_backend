"""Asset 写路径旁路护栏(双器)

1. TestVersionedFieldsProjection — AssetUpdateSerializer 可写字段投影
   (field.source or 字段名)与 ASSET_VERSIONED_FIELDS 集合恒等。两侧任一漂移
   意味着「写字段面 ≠ 版本化判定面」: 要么改了字段不自增(丢失乐观锁保护),
   要么自增判定引用不存在的字段。version 是 CAS 令牌(write_only),不入投影。
2. TestQuerySetUpdateBypass — apps/ 生产代码禁止 QuerySet.update()/bulk_update()
   直写 Asset: 该旁路绕过 Asset.save() 的版本自增,使乐观锁静默失效。
   排除 tests/(夹具直写合法)与 migrations/(CT-6 禁改)。

已知静态盲区(刻意不拦): 变量派发的 QuerySet(如 management/commands/
seed_grouped_assets.py 的 model.objects.update(is_deleted=True))静态不可判;
其只写 is_deleted,语义等价分支4(不自增),不破坏版本不变量。
"""

import ast
from pathlib import Path

from apps.assetmanagement.models.asset import ASSET_VERSIONED_FIELDS
from apps.assetmanagement.serializers.asset_crud_serializers import AssetUpdateSerializer


APPS_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIRS = {"tests", "migrations", "__pycache__"}
TARGET_MANAGER_OWNERS = {"Asset"}


def _production_python_files() -> list[Path]:
    return sorted(
        path for path in APPS_ROOT.rglob("*.py") if not (set(path.relative_to(APPS_ROOT).parts) & EXCLUDED_DIRS)
    )


def _chain_targets_asset_manager(expr: ast.expr) -> bool:
    """沿接收端链下钻(穿透 Call),判定是否为 Asset.objects / Asset.all_objects 派发"""
    while True:
        if isinstance(expr, ast.Attribute):
            if expr.attr in {"objects", "all_objects"} and isinstance(expr.value, ast.Name):
                return expr.value.id in TARGET_MANAGER_OWNERS
            expr = expr.value
        elif isinstance(expr, ast.Call):
            expr = expr.func
        else:
            return False


def _find_queryset_write_bypasses(tree: ast.AST) -> list[int]:
    """返回违规调用的行号(空列表 = 干净)"""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"update", "bulk_update"} and _chain_targets_asset_manager(node.func):
                hits.append(node.lineno)
    return hits


class TestVersionedFieldsProjection:
    """序列化器写字段投影 == ASSET_VERSIONED_FIELDS(集合恒等护栏)"""

    def test_writable_projection_equals_versioned_fields(self):
        serializer = AssetUpdateSerializer()
        projection = {(field.source or name) for name, field in serializer.fields.items() if not field.read_only}
        projection.discard("version")  # CAS 令牌(write_only),非业务写字段
        assert projection == set(ASSET_VERSIONED_FIELDS)

    def test_version_is_cas_token_not_versioned_field(self):
        assert "version" not in ASSET_VERSIONED_FIELDS


class TestQuerySetUpdateBypass:
    """AST 旁路护栏: 禁 QuerySet.update/bulk_update 直写 Asset"""

    def test_no_direct_queryset_write_on_asset(self):
        violations = []
        for path in _production_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for lineno in _find_queryset_write_bypasses(tree):
                violations.append(f"{path.relative_to(APPS_ROOT)}:{lineno}")
        assert violations == [], f"Asset 写入必须走 Asset.save(版本自增),发现 QuerySet 直写旁路: {violations}"

    def test_guard_detects_update_bypass(self):
        """护栏自证: Asset.objects...update(...) 形态必须被检出"""
        tree = ast.parse("Asset.objects.filter(x=1).update(is_deleted=True)")
        assert _find_queryset_write_bypasses(tree) == [1]

    def test_guard_detects_bulk_update_bypass(self):
        tree = ast.parse("Asset.objects.bulk_update(objs, ['asset_name'])")
        assert _find_queryset_write_bypasses(tree) == [1]

    def test_guard_ignores_other_models_and_save(self):
        tree = ast.parse(
            "Contract.objects.filter(x=1).update(y=2)\n"
            "asset.save(update_fields=['asset_name'])\n"
            "data.update({'k': 'v'})"
        )
        assert _find_queryset_write_bypasses(tree) == []
