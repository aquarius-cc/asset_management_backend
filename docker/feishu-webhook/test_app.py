"""飞书适配器单元测试(零第三方依赖, 可直接纳入现有 pytest 流水线).

覆盖: 卡片字段映射(firing/resolved/critical/warning)、加签生成、
webhook 投递重试策略(429/5xx 退避, 其余 4xx 不重试)、HTTP 入口行为.
"""

import json
import time
import unittest
from contextlib import closing
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest import mock

import app as adapter


class BuildCardTests(unittest.TestCase):
    def test_critical_firing_card(self):
        card = adapter.build_card(
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate", "severity": "critical", "instance": "web:8000"},
                "annotations": {"description": "5xx > 5%"},
            }
        )
        self.assertEqual(card["header"]["template"], "red")
        self.assertIn("🔴", card["header"]["title"]["content"])
        text = json.dumps(card["elements"], ensure_ascii=False)
        self.assertIn("HighErrorRate", text)
        self.assertIn("firing", text)
        self.assertIn("5xx > 5%", text)

    def test_resolved_card_is_green(self):
        card = adapter.build_card({"status": "resolved", "labels": {"alertname": "ServiceDown"}, "annotations": {}})
        self.assertEqual(card["header"]["template"], "green")
        self.assertIn("🟢", card["header"]["title"]["content"])

    def test_warning_defaults(self):
        card = adapter.build_card({"labels": {}, "annotations": {}})
        self.assertEqual(card["header"]["template"], "orange")
        text = json.dumps(card["elements"])
        self.assertIn("unknown", text)


class SignTests(unittest.TestCase):
    def test_sign_without_secret_returns_empty(self):
        with mock.patch.object(adapter, "FEISHU_SECRET", ""):
            self.assertEqual(adapter.build_sign("123"), "")

    def test_sign_deterministic_and_base64(self):
        with mock.patch.object(adapter, "FEISHU_SECRET", "s3cret"):
            sign = adapter.build_sign("1700000000")
            again = adapter.build_sign("1700000000")
            self.assertEqual(sign, again)
            # 4 字节对齐的合法 base64
            import base64

            base64.b64decode(sign)


class SendRetryTests(unittest.TestCase):
    def setUp(self):
        # Request 构造函数会校验 URL, 空字符串会在 urlopen 之前就抛异常
        self._url_patcher = mock.patch.object(
            adapter, "FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/test"
        )
        self._url_patcher.start()
        self.addCleanup(self._url_patcher.stop)

    def _fake_urlopen_factory(self, outcomes):
        """outcomes: 每次调用返回/抛出的序列. 返回 mock 函数."""
        calls = {"n": 0}

        def fake_urlopen(request, timeout=None):
            idx = min(calls["n"], len(outcomes) - 1)
            outcome = outcomes[idx]
            calls["n"] += 1
            if isinstance(outcome, Exception):
                raise outcome

            class FakeResp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return json.dumps(outcome).encode()

            return FakeResp()

        return fake_urlopen, calls

    def test_success_first_try_no_sleep(self):
        fake, calls = self._fake_urlopen_factory([{"code": 0}])
        with mock.patch.object(adapter.urllib.request, "urlopen", fake), mock.patch.object(time, "sleep") as fake_sleep:
            ok, err = adapter.send_to_feishu({"header": {}})
            self.assertTrue(ok)
            self.assertEqual(err, "ok")
            fake_sleep.assert_not_called()
            self.assertEqual(calls["n"], 1)

    def test_429_then_success_retries_with_backoff(self):
        import urllib.error

        fake, _calls = self._fake_urlopen_factory(
            [
                urllib.error.HTTPError("u", 429, "rate", {}, None),
                {"code": 0},
            ]
        )
        sleeps = []
        with (
            mock.patch.object(adapter.urllib.request, "urlopen", fake),
            mock.patch.object(time, "sleep", lambda s: sleeps.append(s)),
        ):
            ok, _ = adapter.send_to_feishu({})
            self.assertTrue(ok)
            self.assertEqual(len(sleeps), 1)
            self.assertGreater(sleeps[0], 0)

    def test_client_error_400_no_retry(self):
        import urllib.error

        fake, calls = self._fake_urlopen_factory(
            [
                urllib.error.HTTPError("u", 400, "bad", {}, None),
                {"code": 0},
            ]
        )
        with mock.patch.object(adapter.urllib.request, "urlopen", fake), mock.patch.object(time, "sleep"):
            ok, err = adapter.send_to_feishu({})
            self.assertFalse(ok)
            self.assertEqual(err, "http 400")
            self.assertEqual(calls["n"], 1)

    def test_feishu_business_code_nonzero_retries(self):
        fake, calls = self._fake_urlopen_factory([{"code": 19024, "msg": "sign match fail"}, {"code": 0}])
        with mock.patch.object(adapter.urllib.request, "urlopen", fake), mock.patch.object(time, "sleep"):
            ok, _ = adapter.send_to_feishu({})
            self.assertTrue(ok)
            self.assertEqual(calls["n"], 2)

    def test_payload_carries_sign_when_secret_set(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode())
            captured["url"] = request.full_url

            class FakeResp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return b'{"code": 0}'

            return FakeResp()

        with mock.patch.object(adapter, "FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/x"):
            with mock.patch.object(adapter, "FEISHU_SECRET", "s3cret"):
                with mock.patch.object(adapter.urllib.request, "urlopen", fake_urlopen):
                    ok, _ = adapter.send_to_feishu({})
        self.assertTrue(ok)
        self.assertEqual(captured["url"], "https://open.feishu.cn/open-apis/bot/v2/hook/x")
        self.assertIn("timestamp", captured["body"])
        self.assertIn("sign", captured["body"])
        self.assertEqual(captured["body"]["msg_type"], "interactive")


class HttpEndpointTests(unittest.TestCase):
    """起真实本地 server 验证 HTTP 入口.

    【M-31 确定性夹具】类级共享 server+mock 是历史波动源: 跨用例的端口复用、
    mock 状态泄漏、线程未断言退出共同构成时序裂纹。改为方法级 setUp/tearDown——
    每用例独立端口(0) server、局部 mock(addCleanup 恢复)、shutdown→server_close→
    join(5) 并断言线程退出;_post 用 contextlib.closing 保证连接必然释放。
    """

    def setUp(self):
        import threading

        self._original_send = adapter.send_to_feishu
        self.mock_send = mock.MagicMock(return_value=(True, "ok"))
        adapter.send_to_feishu = self.mock_send
        self.addCleanup(self._restore_send)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), adapter.AdapterHandler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive(), "server 线程未在 5s 内退出(夹具泄漏)")

    def _restore_send(self):
        adapter.send_to_feishu = self._original_send

    def _post(self, path, body=None):
        """POST 并返回 (status, json)。body=None 表示发空 body(404 用例语义)。"""
        with closing(HTTPConnection("127.0.0.1", self.port, timeout=5)) as conn:
            payload = None if body is None else json.dumps(body)
            conn.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            return resp.status, data

    def test_alertmanager_endpoint_delivers_each_alert(self):
        status, data = self._post(
            "/alertmanager",
            {
                "status": "firing",
                "alerts": [{"labels": {"alertname": "A"}}, {"labels": {"alertname": "B"}}],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["delivered"], 2)
        self.assertEqual(self.mock_send.call_count, 2)

    def test_invalid_json_returns_400(self):
        with closing(HTTPConnection("127.0.0.1", self.port, timeout=5)) as conn:
            conn.request("POST", "/alertmanager", body="not-json")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 400)

    def test_unknown_path_404(self):
        status, _ = self._post("/other")
        self.assertEqual(status, 404)

    def test_delivery_failure_maps_to_502(self):
        self.mock_send.return_value = (False, "http 500")
        status, data = self._post("/alertmanager", {"alerts": [{"labels": {}}]})
        self.assertEqual(status, 502)
        self.assertEqual(data["failed_indexes"], [0])


if __name__ == "__main__":
    unittest.main()
