"""Content-Security-Policy 中间件（【MA-15】C6 三态重构）

- CSP_MODE = "enforce"      → Content-Security-Policy（默认，fail-closed）
- CSP_MODE = "report-only"  → Content-Security-Policy-Report-Only（观察期）
- CSP_MODE = "off"          → 不发头

其他变更（v2 锁定版）:
- 移除 'unsafe-eval'；connect-src 收敛 'self' + CSP_CONNECT_SRC_EXTRA 显式注入（wss 域名）
- 指令值统一 dict[str, list[str]]（nginx 单源对齐）；非法 CSP_MODE / DIRECTIVES 缺失即抛
  ImproperlyConfigured（fail-closed，禁止静默回退宽松策略）
- 头名判定移入 __call__（支持 override_settings 直接驱动实例，测试不假绿）
- /static/、/admin/ 跳过（admin 内联事件处理器会被 script-src 拦）
"""

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


logger = logging.getLogger(__name__)

_CSP_MODES = {"off", "report-only", "enforce"}


def _build_csp_header(directives: dict[str, list[str]]) -> str:
    """将 dict[str, list[str]] 指令构建为 CSP 头字符串（value 必须为列表，勿用字符串拼装）"""
    return "; ".join(f"{key} {' '.join(values)}" for key, values in directives.items())


class CspMiddleware:
    """CSP 三态中间件（旧名 ContentSecurityPolicyMiddleware，全后端唯一引用点 base.py MIDDLEWARE）"""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        # fail-closed: 配置错误在启动期即抛，不静默降级为宽松策略
        mode = getattr(settings, "CSP_MODE", "enforce")
        if mode not in _CSP_MODES:
            raise ImproperlyConfigured(f"Invalid CSP_MODE: {mode!r}（可选: off/report-only/enforce）")
        directives = getattr(settings, "CSP_DIRECTIVES", None)
        if not directives:
            raise ImproperlyConfigured("CSP_DIRECTIVES is not configured")
        self._csp_value = _build_csp_header(directives)

    def __call__(self, request: Any) -> Any:
        response = self.get_response(request)
        path = request.path
        # 静态文件和 admin 页面不添加 CSP（admin 内联事件处理器会被 script-src 拦）
        if path.startswith("/static/") or path.startswith("/admin/"):
            return response

        mode = getattr(settings, "CSP_MODE", "enforce")
        if mode not in _CSP_MODES:
            raise ImproperlyConfigured(f"Invalid CSP_MODE: {mode!r}（可选: off/report-only/enforce）")
        if mode == "off":
            return response
        header = "Content-Security-Policy-Report-Only" if mode == "report-only" else "Content-Security-Policy"
        response[header] = self._csp_value
        return response
