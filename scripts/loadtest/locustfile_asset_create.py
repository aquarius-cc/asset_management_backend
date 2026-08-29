"""
Locust 压测基线 — 资产创建（POST /api/v1/assets/）
场景：写入路径，验证 DB 写入 + 外键校验 + 事务性能
注意：仅在预发独立 DB 使用 loadtest_user_*；每次写入生成唯一 asset_code，避免唯一约束冲突
"""

import random
import uuid
from pathlib import Path

from locust import HttpUser, between, task

TOKENS_PATH = Path(__file__).resolve().parent / "tokens.json"
import json
TOKENS = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else []


class AssetCreateUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        if not TOKENS:
            raise RuntimeError("tokens.json 不存在，请先运行 gen_tokens.py")
        idx = random.randint(0, len(TOKENS) - 1)
        self.token = TOKENS[idx]["access"]
        self.client.headers["Authorization"] = f"Bearer {self.token}"

    @task(2)
    def create_asset(self):
        payload = {
            "asset_code": f"LT-{uuid.uuid4().hex[:8].upper()}",
            "asset_name": f"压测资产-{random.randint(1000, 9999)}",
            "asset_purchase_price": "1000.00",
            "asset_purchase_number": 1,
            "asset_unit": "台",
            "asset_brand": "压测品牌",
            "asset_specification": "压测规格",
            "asset_purchase_date": "2025-01-01",
            "asset_warranty_period": 3,
            "asset_type_recordcode": "ASSET_TYPE_001",  # 预发环境存在的类型码
            "current_status": "in_store",
        }
        self.client.post(
            "/api/v1/assets/",
            json=payload,
            name="asset_create",
        )
