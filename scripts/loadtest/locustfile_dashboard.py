"""
Locust 压测基线 — Dashboard 聚合（GET /api/v1/dashboard/overview/ 等）
场景：高频读取聚合指标，验证聚合查询性能基线
"""

import random
from pathlib import Path

from locust import HttpUser, between, task

TOKENS_PATH = Path(__file__).resolve().parent / "tokens.json"

import json
TOKENS = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else []


class DashboardUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        if not TOKENS:
            raise RuntimeError("tokens.json 不存在，请先运行 gen_tokens.py")
        idx = random.randint(0, len(TOKENS) - 1)
        self.token = TOKENS[idx]["access"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(3)
    def dashboard_overview(self):
        self.client.get("/api/v1/dashboard/overview/", name="dash_overview")

    @task(2)
    def dashboard_trend(self):
        self.client.get("/api/v1/dashboard/trend/", name="dash_trend")

    @task(1)
    def dashboard_department(self):
        self.client.get("/api/v1/dashboard/department_distribution/", name="dash_dept")

    @task(1)
    def dashboard_type(self):
        self.client.get("/api/v1/dashboard/type_distribution/", name="dash_type")
