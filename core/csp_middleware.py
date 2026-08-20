"""
Content-Security-Policy 中间件

为所有响应添加 CSP 头,防止 XSS、数据注入等攻击。
开发环境使用 Report-Only 模式(仅报告不阻断),生产环境强制执行。

【配置方式】
通过 settings.CSP_DIRECTIVES 字典配置各指令,或使用环境变量覆盖。
"""


import logging

from django.conf import settings


logger = logging.getLogger(__name__)

# 默认 CSP 策略(宽松但有效,兼容 Vue.js + Element Plus)
_DEFAULT_CSP = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "connect-src": "'self' ws: wss:",
    "font-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
}


def _build_csp_header(directives: dict[str, str]) -> str:
    """将指令字典构建为 CSP 头字符串"""
    return "; ".join(f"{k} {v}" for k, v in directives.items())


class ContentSecurityPolicyMiddleware:
    """
    CSP 中间件

    - 开发环境(DEBUG=True): 设置 Content-Security-Policy-Report-Only(仅报告)
    - 生产环境(DEBUG=False): 设置 Content-Security-Policy(强制执行)
    - 通过 settings.CSP_DIRECTIVES 自定义策略
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._csp_header = "Content-Security-Policy-Report-Only" if settings.DEBUG else "Content-Security-Policy"
        directives = getattr(settings, "CSP_DIRECTIVES", _DEFAULT_CSP)
        self._csp_value = _build_csp_header(directives)

    def __call__(self, request):
        response = self.get_response(request)
        # 静态文件和 admin 页面不添加 CSP(由 Django 自行处理)
        path = request.path
        if path.startswith("/static/") or path.startswith("/admin/"):
            return response
        response[self._csp_header] = self._csp_value
        return response
