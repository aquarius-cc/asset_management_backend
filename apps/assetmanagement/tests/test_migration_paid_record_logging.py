"""【MA-17】0010 数据迁移 print 吞错改 logger 回归。

直接调用 migrate_paid_record_forward(apps, schema_editor),apps 以 MagicMock 伪造:
- 构造一条 save 抛错的失败行 → 断言 logger.error 被调用且 error_count=1
- 构造一条已 JSON 化的跳过行 → 断言 error_count 不误增
"""

import importlib
import json
import logging
from unittest.mock import MagicMock


# 迁移模块名以数字开头,无法静态 import,经 importlib 导入
_migration = importlib.import_module("apps.assetmanagement.migrations.0010_migrate_paid_record_to_json")
migrate_paid_record_forward = _migration.migrate_paid_record_forward
MODULE = _migration.__name__


def _make_mock_apps(contracts):
    mock_apps = MagicMock()
    Contract = MagicMock()
    Contract.objects.filter.return_value.exclude.return_value = contracts
    mock_apps.get_model.return_value = Contract
    return mock_apps


def test_failed_row_logged_and_counted(caplog):
    failing = MagicMock()
    failing.contract_code = "C-FAIL"
    failing.paid_record = "2024-01-15 10:00:00: 付款 100 元"
    failing.save = MagicMock(side_effect=Exception("boom"))

    ok_json = MagicMock()
    ok_json.contract_code = "C-OK"
    ok_json.paid_record = json.dumps({"payments": [], "total_paid": 0})

    with caplog.at_level(logging.INFO):
        migrate_paid_record_forward(_make_mock_apps([failing, ok_json]), MagicMock())

    # caplog 的 record.message 仅在格式化后才有值,断言用 getMessage()
    assert any("迁移合同C-FAIL失败" in r.getMessage() for r in caplog.records)
    assert any("失败1条" in r.getMessage() for r in caplog.records)


def test_skip_row_counted_as_skipped(caplog):
    ok_json = MagicMock()
    ok_json.contract_code = "C-OK"
    ok_json.paid_record = json.dumps({"payments": [{"id": "u"}], "total_paid": 0})

    with caplog.at_level(logging.INFO):
        migrate_paid_record_forward(_make_mock_apps([ok_json]), MagicMock())

    assert any("跳过1条" in r.message for r in caplog.records)
    assert not any("失败" in r.message and "失败0条" not in r.message for r in caplog.records)
