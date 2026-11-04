"""
pytest 全局配置
将 apps/ 加入 pythonpath，使 pytest 能按 app label 发现测试模块
"""

import sys
from pathlib import Path

import pytest
from drf_spectacular.generators import SchemaGenerator


# 将 apps/ 加入模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent / "apps"))


@pytest.fixture(scope="session")
def api_schema():
    """整份 OpenAPI schema，**全 session 只生成一次**。

    OP-09 批次 8 提交 3：自 apps/usermanagement/tests/conftest.py 上提至根 conftest。
    原因：``SchemaGenerator().get_schema()`` 会 introspect 全量视图，成本高；
    消费方（员工契约护栏 / security 引用护栏 / OP-09 信封护栏）需要看**全量
    operation**，重复生成纯属浪费（DR-1）。

    session 级安全前提：schema 生成不查库、不读模块级可变状态，且当前消费方
    都不改动 schema 相关 settings。若将来出现会改 ``SPECTACULAR_SETTINGS`` 的
    用例，需把本 fixture 降回 module 级。
    """
    return SchemaGenerator().get_schema(request=None, public=True)
