"""StructuredJSONFormatter extra 字段白名单回归（B1/OC-2）。"""

import json
import logging

from core.json_formatter import StructuredJSONFormatter


def _record(**extras):
    record = logging.LogRecord(
        name="frontend.error",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="frontend log received",
        args=(),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


class TestExtraWhitelist:
    def test_whitelisted_extra_fields_are_emitted(self):
        record = _record(
            client_trace_id="trace-abc",
            client_time="2026-11-16T10:00:00+08:00",
            frontend_module="AssetDetail",
            release="v1.2.3",
            env="production",
            route="/assets/",
            frontend_context={"route": "/assets/", "status": "failed"},
            error_type="TypeError",
            error_message="x is undefined",
            internal_secret="s3cr3t",
        )
        payload = json.loads(StructuredJSONFormatter().format(record))

        assert payload["client_trace_id"] == "trace-abc"
        assert payload["client_time"] == "2026-11-16T10:00:00+08:00"
        assert payload["frontend_module"] == "AssetDetail"
        assert payload["release"] == "v1.2.3"
        assert payload["env"] == "production"
        assert payload["route"] == "/assets/"
        assert payload["frontend_context"] == {"route": "/assets/", "status": "failed"}
        assert payload["error_type"] == "TypeError"
        assert payload["error_message"] == "x is undefined"
        assert "internal_secret" not in payload
        assert "s3cr3t" not in json.dumps(payload, ensure_ascii=False)

    def test_unknown_extra_fields_are_dropped(self):
        record = _record(password="s3cr3t", request_body="cookie=abc")
        payload = json.loads(StructuredJSONFormatter().format(record))

        assert "password" not in payload
        assert "request_body" not in payload
        assert "s3cr3t" not in json.dumps(payload, ensure_ascii=False)

    def test_no_extra_keeps_base_shape(self):
        record = _record()
        payload = json.loads(StructuredJSONFormatter().format(record))

        assert {"time", "level", "logger", "module", "message"} <= payload.keys()
        assert {"client_trace_id", "frontend_context", "error_message"}.isdisjoint(payload.keys())
