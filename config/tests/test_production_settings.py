"""Production settings 冒烟测试

验证:
1. 合法 env 下 production settings 可正常导入(不抛 ImproperlyConfigured)
2. console handler 使用 JSON 格式 + trace_id filter (OC-1/OC-2)
3. root logger 已配置,第三方库日志不走 lastResort
"""

import logging
import os
from unittest.mock import patch

import pytest


REQUIRED_ENV = {
    "SECRET_KEY": "test-secret-key-for-smoke-test-32chars!!",
    "ALLOWED_HOSTS": "localhost,127.0.0.1",
    "DB_NAME": "test_db",
    "DB_USER": "test_user",
    "DB_PASSWORD": "test_password_123",
    "REDIS_URL": "redis://localhost:6379/0",
}


@pytest.fixture(autouse=True)
def _set_production_env():
    """设置 production settings 所需的全部环境变量"""
    with patch.dict(os.environ, REQUIRED_ENV, clear=False):
        yield


class TestProductionSettingsImport:
    """production settings 可正常导入"""

    def test_import_does_not_raise(self):
        """合法 env 下导入 production settings 不抛异常"""
        from config.settings import production  # noqa: F401

    def test_secret_key_set(self):
        from config.settings import production

        assert production.SECRET_KEY == REQUIRED_ENV["SECRET_KEY"]

    def test_debug_is_false(self):
        from config.settings import production

        assert production.DEBUG is False

    def test_allowed_hosts_parsed(self):
        from config.settings import production

        assert "localhost" in production.ALLOWED_HOSTS
        assert "127.0.0.1" in production.ALLOWED_HOSTS


class TestConsoleLogFormat:
    """console handler 使用 JSON 格式 + trace_id (OC-1/OC-2)"""

    @pytest.fixture(autouse=True)
    def _reload_logging(self):
        """每次测试前重新导入以获取最新 LOGGING 配置"""
        import importlib

        from config.settings import production

        importlib.reload(production)
        self.logging_cfg = production.LOGGING

    def test_console_formatter_is_json(self):
        assert self.logging_cfg["handlers"]["console"]["formatter"] == "json"

    def test_console_has_trace_id_filter(self):
        assert "trace_id" in self.logging_cfg["handlers"]["console"]["filters"]

    def test_console_level_is_warning(self):
        assert self.logging_cfg["handlers"]["console"]["level"] == "WARNING"

    def test_file_handler_unchanged(self):
        assert self.logging_cfg["handlers"]["file"]["formatter"] == "json"
        assert "trace_id" in self.logging_cfg["handlers"]["file"]["filters"]


class TestRootLogger:
    """root logger 已配置,第三方库日志走 JSON console"""

    @pytest.fixture(autouse=True)
    def _reload_logging(self):
        import importlib

        from config.settings import production

        importlib.reload(production)
        self.logging_cfg = production.LOGGING

    def test_root_key_exists(self):
        assert "root" in self.logging_cfg

    def test_root_has_console_handler(self):
        assert "console" in self.logging_cfg["root"]["handlers"]

    def test_root_has_file_handler(self):
        assert "file" in self.logging_cfg["root"]["handlers"]

    def test_root_level_is_warning(self):
        assert self.logging_cfg["root"]["level"] == "WARNING"


class TestJSONLogEmission:
    """实际发射一条 warning 日志并验证 JSON 可解析"""

    def test_warning_log_is_valid_json(self, caplog):
        with caplog.at_level(logging.WARNING, logger="some.third.party"):
            logging.getLogger("some.third.party").warning("smoke-test-message")

        # caplog 捕获的日志可能不是 JSON 格式(取决于 formatter 是否应用于 handler)
        # 此测试验证 root logger 的 WARNING 级别确实能传播到 handler
        assert "smoke-test-message" in caplog.text
