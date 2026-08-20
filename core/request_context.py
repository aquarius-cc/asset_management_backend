"""
请求上下文中间件

通过 thread-local 存储当前请求信息,供 Service 层获取 ip_address、trace_id 等上下文。
用于审计日志记录操作来源 IP,以及请求链路追踪。

【使用方式】
- 中间件自动存储 request、ip_address、trace_id 到 thread-local
- Service 层通过 get_current_ip() 获取当前请求 IP
- Service 层通过 get_current_trace_id() 获取当前请求的 trace_id
"""

import threading
import uuid


_thread_locals = threading.local()


def get_current_ip() -> str | None:
    """获取当前请求的 IP 地址"""
    return getattr(_thread_locals, "ip_address", None)


def get_current_trace_id() -> str | None:
    """获取当前请求的 trace_id(OC-1 落地)"""
    return getattr(_thread_locals, "trace_id", None)


def get_current_request():
    """获取当前请求对象"""
    return getattr(_thread_locals, "request", None)


class RequestContextMiddleware:
    """
    请求上下文中间件

    将 request、ip_address、trace_id 存储到 thread-local,
    供 Service 层通过 get_current_ip()、get_current_trace_id() 获取。

    【OC-1 落地】每个请求生成全局唯一 trace_id,并在整个调用链透传。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 生成或获取 trace_id(OC-1 落地)
        trace_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        _thread_locals.trace_id = trace_id

        # 存储请求信息到 thread-local
        _thread_locals.request = request
        _thread_locals.ip_address = self._get_client_ip(request)

        # 将 trace_id 添加到响应头
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = trace_id
        finally:
            # 清理 thread-local,防止内存泄漏
            _thread_locals.request = None
            _thread_locals.ip_address = None
            _thread_locals.trace_id = None

        return response

    @staticmethod
    def _get_client_ip(request) -> str | None:
        """
        从 request 中提取客户端 IP

        信任边界:必须部署在可信反向代理(Nginx/ALB)之后,
        代理负责覆写/追加 X-Forwarded-For。
        无代理直连时回退到 REMOTE_ADDR。
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
