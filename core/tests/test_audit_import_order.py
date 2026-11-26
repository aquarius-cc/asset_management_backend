"""M-LAY-04: audit 模块级不得依赖 services 包。"""

import ast
from pathlib import Path


AUDIT = Path(__file__).resolve().parents[2] / "apps" / "assetmanagement" / "audit.py"
PREFIX = "apps.assetmanagement.services"


def test_audit_has_no_module_level_services_import():
    tree = ast.parse(AUDIT.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(PREFIX):
            offenders.append(node.module)
        elif isinstance(node, ast.Import):
            offenders.extend(alias.name for alias in node.names if alias.name.startswith(PREFIX))
    assert offenders == []
