"""飞书告警适配器: Alertmanager v0.27 webhook -> 飞书群机器人交互卡片.

零第三方依赖(仅 Python 标准库), 由 docker/feishu-webhook/Dockerfile 打包.
配置全部经环境变量注入(AR-4), 外呼带显式超时与指数退避重试(AR-3).
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ==================== 配置(AR-4: 禁止硬编码, 全部经环境变量管理) ====================
FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET", "")
LISTEN_PORT = int(os.environ.get("ADAPTER_PORT", "9095"))
HTTP_TIMEOUT = float(os.environ.get("ADAPTER_TIMEOUT_SECONDS", "5"))
MAX_RETRIES = int(os.environ.get("ADAPTER_RETRY_MAX", "3"))
BACKOFF_BASE = float(os.environ.get("ADAPTER_BACKOFF_BASE_SECONDS", "1"))

# ==================== 日志(OC-2: 结构化 JSON; OC-3: 不记录凭据) ====================
logging.basicConfig(
    level=os.environ.get("ADAPTER_LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
)
log = logging.getLogger("feishu-webhook")


def build_sign(timestamp: str) -> str:
    """飞书自定义机器人加签.

    算法: HmacSHA256(key=f"{timestamp}\\n{secret}", msg=b"") 后 base64.
    """
    # AI_REVIEW_NEEDED: 上线前对照飞书官方文档复核加签算法与字段名(timestamp/sign)
    if not FEISHU_SECRET:
        return ""
    string_to_sign = f"{timestamp}\n{FEISHU_SECRET}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_card(alert: dict) -> dict:
    """将单条 Alertmanager alert 转换为飞书交互卡片."""
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    status = alert.get("status", "firing")
    severity = labels.get("severity", "warning")
    name = labels.get("alertname", "unknown")

    if status == "resolved":
        title = "🟢 告警恢复"
        template = "green"
    else:
        emoji = {"critical": "🔴", "warning": "🟡"}.get(severity, "🔔")
        title = f"{emoji} {severity} 告警"
        template = {"critical": "red", "warning": "orange"}.get(severity, "yellow")

    def field(label: str, value: str) -> dict:
        return {"is_short": True, "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"}}

    elements = [
        {
            "tag": "div",
            "fields": [
                field("告警名称", name),
                field("状态", status),
                field("级别", severity),
                field("实例", labels.get("instance", "-")),
            ],
        },
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md",
         "content": f"**描述**: {annotations.get('description', annotations.get('summary', '-'))}"}},
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": elements,
    }


def send_to_feishu(card: dict) -> tuple:
    """POST 卡片到飞书机器人. 返回 (ok, 错误说明).

    重试策略: 429 与 5xx 指数退避重试; 其余 4xx 直接失败(客户端错误重试无意义).
    """
    payload = {"msg_type": "interactive", "card": card}
    if FEISHU_SECRET:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = build_sign(timestamp)

    data = json.dumps(payload).encode("utf-8")
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                FEISHU_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                # 飞书业务码 0 = 成功; 非零(如签名错误/频控)按错误处理
                if body.get("code") == 0:
                    return True, "ok"
                last_error = f"feishu code={body.get('code')} msg={body.get('msg')}"
        except urllib.error.HTTPError as exc:
            last_error = f"http {exc.code}"
            if exc.code != 429 and exc.code < 500:
                break
        except Exception as exc:
            last_error = repr(exc)
        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
    return False, last_error


class AdapterHandler(BaseHTTPRequestHandler):
    """仅暴露 POST /alertmanager 与 GET /healthz."""

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/alertmanager":
            self._reply(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._reply(400, {"error": "invalid json"})
            return
        alerts = payload.get("alerts", [])
        results = [send_to_feishu(build_card(alert)) for alert in alerts]
        failed = [(idx, err) for idx, (ok, err) in enumerate(results) if not ok]
        if failed:
            # OC-2/OC-3: 结构化日志, 仅记录索引与错误, 不含卡片内容与凭据
            for idx, err in failed:
                log.error("deliver failed alert_index=%s error=%s", idx, err)
            self._reply(502, {"error": "delivery failed", "failed_indexes": [i for i, _ in failed]})
        else:
            log.info("delivered %s alert(s)", len(results))
            self._reply(200, {"delivered": len(results)})

    def log_message(self, fmt, *args):  # 屏蔽默认 stderr 访问日志, 统一走结构化 logger
        log.debug("access %s", fmt % args)


def main() -> None:
    if not FEISHU_WEBHOOK_URL:
        # 对齐后端生产配置强校验风格: 缺关键配置直接拒绝启动
        log.error("FEISHU_WEBHOOK_URL is required, refusing to start")
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), AdapterHandler)
    log.info("feishu adapter listening on port %s", LISTEN_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
