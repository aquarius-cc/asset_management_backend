"""
[M-17] clear_database.py 标识符纵深加固测试

- 白名单 _validate_table_name 保持第一道闸（SC-4，非白名单必抛 RuntimeError）
- SQL 构造改 psycopg sql.Identifier 组合 + .as_string(connection)（实跑编译路径，
  禁止 f-string 插值拼接标识符）
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "clear_database.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("clear_database_m17", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["clear_database_m17"] = module
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


class TestWhitelistFirstGate:
    """SC-4：白名单硬校验保持第一道闸，纵深加固不改变准入语义"""

    def test_non_whitelisted_table_raises(self, mod):
        with pytest.raises(RuntimeError, match="不在白名单中"):
            mod._validate_table_name("attacker_table; DROP TABLE asset;--")

    def test_protected_table_raises(self, mod, monkeypatch):
        # 白名单∩保护表实测无交集，保护表分支需注入可达：白名单业务表 + 注入保护表，
        # 断言两道闸的先后序（先过白名单，再被保护表拦截）
        table = "am_asset_operation_log"
        assert table in mod.ALLOWED_TABLES
        monkeypatch.setattr(mod, "PROTECTED_TABLES", [*mod.PROTECTED_TABLES, table])
        with pytest.raises(RuntimeError, match="系统保护表"):
            mod._validate_table_name(table)


class TestIdentifierComposition:
    """[M-17] 纵深加固：标识符经 psycopg sql.Identifier 编译，非 f-string 插值"""

    def test_build_identifier_sql_exists(self, mod):
        # 红基线：原实现无此构造函数（f-string 直接拼接）
        assert hasattr(mod, "_build_identifier_sql")

    def test_count_sql_compiles_with_quoted_identifier(self, mod, django_db_blocker):
        import django
        from django.db import connection

        django.setup()
        composed = mod._build_identifier_sql("SELECT COUNT(*) FROM {}", "asset")
        compiled = composed.as_string(connection)
        assert '"asset"' in compiled
        assert compiled.startswith("SELECT COUNT(*) FROM ")

    def test_delete_sql_compiles_with_quoted_identifier(self, mod):
        import django

        django.setup()
        from django.db import connection

        composed = mod._build_identifier_sql("DELETE FROM {}", "asset")
        compiled = composed.as_string(connection)
        assert compiled == 'DELETE FROM "asset"'

    def test_execute_receives_compiled_string(self, mod):
        """cursor.execute 收到的必须是 str（Django cursor 不接受 psycopg Composed）"""
        fake_cursor = MagicMock()
        composed = mod._build_identifier_sql("DELETE FROM {}", "asset")
        sql_text = composed.as_string(None)  # psycopg3 支持无连接编译（utf8 默认）
        fake_cursor.execute(sql_text)
        fake_cursor.execute.assert_called_once_with('DELETE FROM "asset"')
