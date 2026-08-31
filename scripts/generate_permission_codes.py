#!/usr/bin/env python3
"""
M-6 权限码常量生成器
从 init_production_data.py 的 MODULES_CONFIG 读取权限定义，
生成前端 permissionCodes.ts 和后端 permission_constants.py。

用法：
  python scripts/generate_permission_codes.py --check   # CI 模式：仅校验不写入
  python scripts/generate_permission_codes.py           # 生成并写入
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BE_DIR = ROOT
FE_DIR = ROOT.parent / "vue-assetmanagement"

# ── 读取 MODULES_CONFIG ──────────────────────────────────────────────────
INIT_CMD = BE_DIR / "apps" / "usermanagement" / "management" / "commands" / "init_production_data.py"


def _parse_modules_config() -> dict:
    """AST 解析 init_production_data.py 中的 MODULES_CONFIG 字典。"""
    tree = ast.parse(INIT_CMD.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MODULES_CONFIG":
                    return ast.literal_eval(node.value)
    raise RuntimeError("MODULES_CONFIG not found in init_production_data.py")


# ── 读取额外常量（来自 migration 0017） ─────────────────────────────────
EXTRA_CODES = {"system_config:manage"}


def build_code_set(modules: dict) -> set[str]:
    """从 MODULES_CONFIG 构建完整权限码集合。"""
    codes = set()
    for module, cfg in modules.items():
        for action in cfg["actions"]:
            codes.add(f"{module}:{action}")
    codes.update(EXTRA_CODES)
    return codes


# ── 生成前端 TypeScript ─────────────────────────────────────────────────
def _code_to_const_name(code: str) -> str:
    """'asset:read' → 'ASSET_READ'。"""
    module, action = code.split(":")
    return f"{module.upper()}_{action.upper()}"


FE_HEADER = """\
export const PERMISSION_CODES = {
  // 由 scripts/generate_permission_codes.py 自动生成，勿手动编辑
"""
FE_FOOTER = """\
} as const;
"""


def generate_fe_ts(codes: set[str]) -> str:
    lines = [FE_HEADER.rstrip()]
    for code in sorted(codes):
        const_name = _code_to_const_name(code)
        lines.append(f"  {const_name}: '{code}',")
    lines.append(FE_FOOTER.rstrip())
    return "\n".join(lines) + "\n"


# ── 生成后端 Python 常量 ────────────────────────────────────────────────
BE_HEADER = '''\
"""权限码常量（由 scripts/generate_permission_codes.py 自动生成，勿手动编辑）。"""
from __future__ import annotations

PERMISSION_CODES: dict[str, str] = {
'''
BE_FOOTER = """\
}
"""


def generate_be_py(codes: set[str]) -> str:
    lines = [BE_HEADER.rstrip()]
    for code in sorted(codes):
        const_name = _code_to_const_name(code)
        lines.append(f'    "{const_name}": "{code}",')
    lines.append(BE_FOOTER.rstrip())
    return "\n".join(lines) + "\n"


# ── 校验 ────────────────────────────────────────────────────────────────
def _extract_existing_codes(ts_path: Path) -> set[str]:
    """从已有 permissionCodes.ts 中提取权限码值。"""
    text = ts_path.read_text(encoding="utf-8")
    return set(re.findall(r"'([a-z_]+:[a-z_]+)'", text))


def check_fe(modules: dict) -> bool:
    """校验前端文件是否与 MODULES_CONFIG 一致。"""
    expected = build_code_set(modules)
    ts_path = FE_DIR / "src" / "constants" / "permissionCodes.ts"
    if not ts_path.exists():
        print(f"[M-6] FAIL: {ts_path} not found")
        return False
    actual = _extract_existing_codes(ts_path)
    missing = expected - actual
    extra = actual - expected
    ok = True
    if missing:
        print(f"[M-6] FAIL: missing in FE: {sorted(missing)}")
        ok = False
    if extra:
        print(f"[M-6] WARN: extra in FE (not in MODULES_CONFIG): {sorted(extra)}")
    if ok:
        print("[M-6] PASS: FE permissionCodes.ts is in sync")
    return ok


def check_be(modules: dict) -> bool:
    """校验后端常量文件是否与 MODULES_CONFIG 一致。"""
    expected = build_code_set(modules)
    be_path = BE_DIR / "constants" / "permission_constants.py"
    if not be_path.exists():
        print(f"[M-6] FAIL: {be_path} not found — run once without --check to create")
        return False
    text = be_path.read_text(encoding="utf-8")
    actual = set(re.findall(r'"([a-z_]+:[a-z_]+)"', text))
    missing = expected - actual
    extra = actual - expected
    ok = True
    if missing:
        print(f"[M-6] FAIL: missing in BE: {sorted(missing)}")
        ok = False
    if extra:
        print(f"[M-6] WARN: extra in BE: {sorted(extra)}")
    if ok:
        print("[M-6] PASS: BE permission_constants.py is in sync")
    return ok


# ── 主入口 ──────────────────────────────────────────────────────────────
def main() -> int:
    check_only = "--check" in sys.argv
    modules = _parse_modules_config()
    codes = build_code_set(modules)

    if check_only:
        fe_ok = check_fe(modules)
        be_ok = check_be(modules)
        return 0 if (fe_ok and be_ok) else 1

    # 写入前端
    fe_path = FE_DIR / "src" / "constants" / "permissionCodes.ts"
    fe_content = generate_fe_ts(codes)
    fe_path.write_text(fe_content, encoding="utf-8")
    print(f"[M-6] 写入 {fe_path} ({len(codes)} codes)")

    # 写入后端
    be_dir = BE_DIR / "constants"
    be_dir.mkdir(exist_ok=True)
    be_path = be_dir / "permission_constants.py"
    be_content = generate_be_py(codes)
    be_path.write_text(be_content, encoding="utf-8")
    print(f"[M-6] 写入 {be_path} ({len(codes)} codes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
