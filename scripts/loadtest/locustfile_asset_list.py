"""
Locust 压测基线 — 资产列表（GET /api/v1/assets/）
"""

import json
import random
from pathlib import Path

from locust import HttpUser, between, task


TOKENS_PATH = Path(__file__).resolve().parent / "tokens.json"
TOKENS = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else []


class AssetListUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        if not TOKENS:
            raise RuntimeError("tokens.json 不存在，请先运行 gen_tokens.py")
        # 每个 vuser 分配一个 token
        idx = random.randint(0, len(TOKENS) - 1)
        self.token = TOKENS[idx]["access"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(3)
    def list_assets(self):
        params = {
            "page": random.randint(1, 100),
            "page_size": 20,
        }
        # 随机过滤条件
        if random.random() < 0.5:
            params["search"] = random.choice(["AST", "PC", "PRJ", "ASSET"])
        self.client.get("/api/v1/assets/", params=params, name="list_assets")

    @task(1)
    def list_assets_with_status(self):
        self.client.get(
            "/api/v1/assets/",
            params={"current_status": "in_use", "page_size": 20},
            name="list_assets_in_use",
        )
