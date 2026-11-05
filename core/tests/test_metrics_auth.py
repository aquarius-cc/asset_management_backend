"""[P3-10] /metrics/ 端点 Bearer 鉴权 5 分支测试(默认关闭 = 既有行为)。

矩阵:
- 空配置(未设 METRICS_TOKEN) → 200 放行(Prometheus 内部抓取既有行为)
- 配置后: 正确 Bearer → 200; 错误 token / 缺头 / 方案错 → 401(不区分原因)
"""

import pytest
from django.test import override_settings


TEST_TOKEN = "test-metrics-token-0123456789"
METRICS_URL = "/metrics/"


@pytest.mark.django_db
class TestMetricsBearerAuth:
    def test_empty_token_passes(self, client):
        """空配置 = 放行(既有行为, 默认关闭)"""
        assert client.get(METRICS_URL).status_code == 200

    @override_settings(METRICS_TOKEN=TEST_TOKEN)
    def test_valid_bearer_200(self, client):
        resp = client.get(METRICS_URL, HTTP_AUTHORIZATION=f"Bearer {TEST_TOKEN}")
        assert resp.status_code == 200

    @override_settings(METRICS_TOKEN=TEST_TOKEN)
    def test_wrong_token_401(self, client):
        assert client.get(METRICS_URL, HTTP_AUTHORIZATION="Bearer wrong-token").status_code == 401

    @override_settings(METRICS_TOKEN=TEST_TOKEN)
    def test_missing_header_401(self, client):
        assert client.get(METRICS_URL).status_code == 401

    @override_settings(METRICS_TOKEN=TEST_TOKEN)
    def test_malformed_scheme_401(self, client):
        """非 Bearer 方案统一拒绝(与缺头/错 token 同型 401, 防探测)"""
        assert client.get(METRICS_URL, HTTP_AUTHORIZATION=f"Basic {TEST_TOKEN}").status_code == 401
